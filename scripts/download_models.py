# -*- coding: utf-8 -*-
"""下载 RAG 所需的两个本地模型（离线部署预置）。

用法:
    python scripts/download_models.py                     # 全部（官方优先，失败自动回退镜像）
    python scripts/download_models.py --only embedding     # 只下 embedding（≈92MB）
    python scripts/download_models.py --mirror hf          # 回退镜像改用 hf-mirror.com
    python scripts/download_models.py --no-official        # 跳过官方探测，直接走镜像
    python scripts/download_models.py --dest dir --output instance/models   # 落到显式目录

下载策略（按优先级）：
    1. huggingface.co 官方 snapshot_download → 生成**标准 HF 缓存**（blobs + 真实
       commit hash + etag metadata），与本地开发环境完全一致，适合境外/可访问
       HF 的部署；5 秒无响应即判定不可达并回退（避免长时间静默挂起）。
    2. 回退 ModelScope（默认，实测约 5.7MB/s）/ hf-mirror（约 1MB/s），按 HF 缓存
       布局写入 snapshots/main —— 实测 hf_hub_download 与 snapshot_download 均能
       正常命中，因此加载侧无需任何代码改动。
    两条路径均做 size + sha256 校验（ModelScope 的文件列表 API 提供 sha256）。

背景与必要性：
- app/services/ai/rag/embedding.py 与 reranker.py 都设置了 HF_HUB_OFFLINE=1 /
  TRANSFORMERS_OFFLINE=1（避免 transformers 5.x 在无网环境加载时卡死），
  因此**模型必须先落到本地**，否则运行期加载必然失败。
- huggingface.co 在国内多数机房不可达；实测 hf-mirror.com 约 1.0MB/s，
  而 ModelScope（魔搭）约 5.7MB/s，故默认走 ModelScope。

模型：
- BAAI/bge-small-zh-v1.5  ≈ 91MB   （embedding，必需）
- BAAI/bge-reranker-base  ≈ 1060MB （cross-encoder 精排，模型缺失时代码自动降级为
                                     RRF 排序，可用 --only embedding 跳过）
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "instance" / "models"

MODELS = {
    "bge-small-zh-v1.5": {
        "modelscope": "BAAI/bge-small-zh-v1.5",
        "hf": "BAAI/bge-small-zh-v1.5",
        "desc": "RAG embedding（必需，≈91MB）",
        "role": "embedding",
    },
    "bge-reranker-base": {
        "modelscope": "BAAI/bge-reranker-base",
        "hf": "BAAI/bge-reranker-base",
        "desc": "RAG cross-encoder 精排（可选，≈1060MB；缺失时自动降级）",
        "role": "reranker",
    },
}

HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
MODELSCOPE_ENDPOINT = os.getenv("MODELSCOPE_ENDPOINT", "https://www.modelscope.cn")


def log(msg: str) -> None:
    """打印带时间戳的进度信息（长下载过程需要可见反馈）。"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _get_json(url: str, timeout: int = 30) -> dict:
    """GET 并解析 JSON；失败抛异常由调用方决定是否回退镜像。"""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_modelscope_files(repo: str) -> list:
    """列出 ModelScope 仓库下的全部文件（扁平清单）。

    用 `Recursive=true` 一次拿全（含 1_Pooling/config.json 这类子目录内文件）。
    踩坑记录：**子目录参数是 `Root=` 而不是 `Path=`**——用 Path 会直接 404，
    且若按目录递归（遇到 type=tree 就再查一次），整个下载会以 404 失败。

    Args:
        repo: 形如 BAAI/bge-small-zh-v1.5。

    Returns:
        [{"path": 相对路径, "size": 字节数}, ...]
    """
    url = (f"{MODELSCOPE_ENDPOINT}/api/v1/models/{repo}/repo/files?"
           + urllib.parse.urlencode({"Revision": "master", "Recursive": "true"}))
    data = _get_json(url)
    out = []
    for item in (data.get("Data") or {}).get("Files", []):
        if item.get("Type") != "blob":
            continue
        p = item.get("Path") or ""
        if p:
            out.append({
                "path": p,
                "size": int(item.get("Size") or 0),
                "sha256": (item.get("Sha256") or "").lower(),
            })
    return out


def list_hf_files(repo: str) -> list:
    """列出 hf-mirror 仓库下的文件（HF API 直接返回扁平清单）。"""
    data = _get_json(f"{HF_ENDPOINT}/api/models/{repo}")
    return [
        {"path": f["rfilename"], "size": int(f.get("size") or 0)}
        for f in data.get("siblings", [])
    ]


def filter_weight_files(files: list) -> list:
    """过滤掉用不上的大文件，避免白下几个 GB。

    规则：
    1. 跳过 onnx（`onnx/model.onnx` 等）：sentence-transformers 的
       SentenceTransformer/CrossEncoder 走 PyTorch 后端，不读 onnx。
       —— 实测 bge-reranker-base 的 onnx 与 safetensors 各 1GB，全下要 3GB+。
    2. 权重格式二选一：存在 model.safetensors 时跳过 pytorch_model.bin
       （两者内容等价，safetensors 加载更快且更安全）。

    Args:
        files: list_modelscope_files / list_hf_files 的返回值。

    Returns:
        过滤后的文件列表。
    """
    names = {f["path"] for f in files}
    out = []
    for f in files:
        p = f["path"]
        if p.endswith(".onnx") or p.startswith("onnx/"):
            continue
        if p == "pytorch_model.bin" and "model.safetensors" in names:
            continue
        out.append(f)
    return out


def file_sha256(path: Path) -> str:
    """分块计算文件 sha256（避免大文件占内存）。

    Args:
        path: 文件路径。

    Returns:
        小写十六进制摘要。
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path, size: int = 0, sha256: str = "") -> None:
    """流式下载单个文件，并做大小 + sha256 校验；已存在且校验通过则跳过。

    校验的必要性：只比对文件大小无法发现"大小相同但内容损坏"的情况
    （网络截断/中间设备改写），而模型权重损坏会在加载期以难以定位的
    异常暴露。ModelScope 的文件列表 API 提供 sha256，故此处强制校验。

    Args:
        url: 直链。
        dest: 目标路径（父目录自动创建）。
        size: 期望大小（字节），0 表示不校验。
        sha256: 期望 sha256（小写十六进制），空串表示源未提供、跳过该项校验。

    Raises:
        ValueError: 下载完成但校验不通过（文件已删除，便于重跑重下）。
    """
    if dest.exists():
        ok_size = (not size) or dest.stat().st_size == size
        ok_hash = (not sha256) or file_sha256(dest) == sha256.lower()
        if ok_size and ok_hash:
            log(f"  跳过（已存在且校验通过）: {dest.name}")
            return
        log(f"  已存在但校验不符，重新下载: {dest.name}")
        dest.unlink()

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "ipip-deploy/1.0"})
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if size > 20 * 1024 * 1024 and done % (5 * 1024 * 1024) < 256 * 1024:
                pct = done * 100 / size if size else 0
                log(f"    {dest.name}: {done/1048576:.1f}MB / {size/1048576:.1f}MB ({pct:.0f}%)")
    elapsed = max(0.1, time.monotonic() - start)
    tmp.replace(dest)

    if size and dest.stat().st_size != size:
        got = dest.stat().st_size
        dest.unlink(missing_ok=True)
        raise ValueError(f"{dest.name} 大小不符（期望 {size}，实际 {got}）")
    if sha256 and file_sha256(dest) != sha256.lower():
        dest.unlink(missing_ok=True)
        raise ValueError(f"{dest.name} sha256 校验失败（文件已删除，重跑将重新下载）")

    speed = (dest.stat().st_size / 1048576) / elapsed
    log(f"  完成: {dest.name}（{dest.stat().st_size/1048576:.1f}MB, {speed:.1f}MB/s）")


def hf_reachable(timeout: int = 5) -> bool:
    """快速探测 huggingface.co 是否可达。

    为什么要先探测而不是直接 snapshot_download：国内机房对 huggingface.co
    多为"连接超时"而非立即拒绝，直接调用会静默挂起数十秒（每个模型各一次）。
    探测把等待压到 5 秒内，不通就立刻回退镜像。

    Args:
        timeout: 探测超时（秒）。

    Returns:
        是否有响应（收到 4xx/5xx 也算可达——网络通即可）。
    """
    try:
        urllib.request.urlopen("https://huggingface.co", timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001
        return False


def try_hf_official(repo: str) -> bool:
    """优先走 huggingface_hub 官方下载，生成**标准 HF 缓存**。

    标准缓存 = blobs/<etag> + snapshots/<真实 commit hash> + refs/main + etag
    metadata，与本地开发环境（~/.cache/huggingface）完全一致，便于后续
    revision 切换与缓存管理。适用于境外/可访问 huggingface.co 的部署；
    不可达或失败时返回 False，由调用方回退到镜像下载（ModelScope）。

    Args:
        repo: HF repo id（如 BAAI/bge-small-zh-v1.5）。

    Returns:
        是否成功。
    """
    log(f"== 优先尝试官方源: {repo}")
    if not hf_reachable():
        log("  huggingface.co 不可达（5s 无响应）→ 回退镜像下载")
        return False
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        log("  未安装 huggingface_hub → 回退镜像下载")
        return False
    try:
        path = snapshot_download(repo_id=repo)
        log(f"  ✔ 官方下载完成（标准缓存）: {path}")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"  官方下载失败（{type(e).__name__}: {str(e)[:100]}）→ 回退镜像下载")
        return False


def hf_cache_snapshot_dir(repo: str) -> Path:
    """返回 HF 标准缓存布局下的 snapshots/main 目录并确保骨架存在。

    位置：`$HF_HOME/hub/models--<owner>--<name>/snapshots/main/`
    同时写 `refs/main`（离线加载时 transformers 靠它解析修订点）。

    HF 官方布局还会把文件放 blobs/<sha256> 再在 snapshots 下建符号链接，
    但**实测直接在 snapshots 下放真实文件即可被离线加载**（transformers 按
    路径读取），故省略 blobs 层，降低实现复杂度。

    Args:
        repo: 形如 BAAI/bge-small-zh-v1.5（用 HF 侧 repo id，与 .env 配置一致）。

    Returns:
        snapshots/main 目录。
    """
    hf_home = Path(os.getenv("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
    base = hf_home / "hub" / ("models--" + repo.replace("/", "--"))
    (base / "refs").mkdir(parents=True, exist_ok=True)
    (base / "refs" / "main").write_text("main")
    snap = base / "snapshots" / "main"
    snap.mkdir(parents=True, exist_ok=True)
    return snap


def fetch_model(key: str, spec: dict, dest_dir: Path, mirror: str) -> bool:
    """下载单个模型的全部文件到 dest_dir。

    Args:
        key: 模型短名（仅用于日志）。
        spec: MODELS 中的配置。
        dest_dir: 目标目录（HF 缓存 snapshots 目录，或显式输出目录/<key>）。
        mirror: modelscope | hf。

    Returns:
        是否成功。
    """
    log(f"== {key}  {spec['desc']}  → {dest_dir}")
    try:
        if mirror == "modelscope":
            repo = spec["modelscope"]
            files = filter_weight_files(list_modelscope_files(repo))
            for f in files:
                url = (f"{MODELSCOPE_ENDPOINT}/api/v1/models/{repo}/repo?"
                       + urllib.parse.urlencode({"Revision": "master", "FilePath": f["path"]}))
                download_file(url, dest_dir / f["path"], f["size"], f.get("sha256", ""))
        else:
            repo = spec["hf"]
            files = filter_weight_files(list_hf_files(repo))
            for f in files:
                url = f"{HF_ENDPOINT}/{repo}/resolve/main/{f['path']}"
                download_file(url, dest_dir / f["path"], f["size"])
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        log(f"  ❌ {key} 下载失败（mirror={mirror}）: {e}")
        return False
    log(f"✔ {key} 就绪: {dest_dir}")
    return True


def main() -> None:
    """命令行入口：解析参数并逐个下载模型。"""
    parser = argparse.ArgumentParser(description="下载 RAG 本地模型（离线部署预置）")
    parser.add_argument("--dest", choices=["hf-cache", "dir"], default="hf-cache",
                        help="模型落地位置：hf-cache（默认）= HF 标准缓存布局 "
                             "($HF_HOME/hub/models--BAAI--<name>/snapshots/main/)，"
                             "与本地开发环境一致，代码与 .env 都不用改；"
                             "dir = 显式目录（需自行把 RAG_*_MODEL 指向该路径）")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help=f"--dest dir 时的输出根目录（默认 {DEFAULT_OUTPUT}）")
    parser.add_argument("--mirror", choices=["modelscope", "hf"], default="modelscope",
                        help="回退镜像：modelscope（默认，实测约 5.7MB/s）或 hf（hf-mirror.com，约 1MB/s）")
    parser.add_argument("--no-official", action="store_true",
                        help="跳过 huggingface.co 官方尝试，直接用镜像下载"
                             "（国内环境可省掉每个模型 5s 的探测等待）")
    parser.add_argument("--only", choices=["embedding", "reranker", "all"], default="all",
                        help="只下载指定角色：embedding（91MB）/ reranker（1060MB）/ all")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    targets = [
        (k, v) for k, v in MODELS.items()
        if args.only == "all" or v["role"] == args.only
    ]
    if not targets:
        sys.exit(f"❌ --only {args.only} 未匹配到任何模型")

    dest_desc = ("HF 标准缓存（$HF_HOME/hub/models--<owner>--<name>/snapshots/main/）"
                 if args.dest == "hf-cache" else str(output))
    order_desc = ("镜像优先（--no-official，跳过官方探测）" if args.no_official
                  else "官方优先，5s 内不可达则自动回退镜像")
    log(f"落地位置: {dest_desc}")
    log(f"下载顺序: {order_desc}；回退镜像: {args.mirror}")
    log(f"待下载: {', '.join(k for k, _ in targets)}")

    def dest_of(key: str, spec: dict) -> Path:
        """按 --dest 解析落地目录（hf-cache 用 HF 侧 repo id 命名缓存目录）。"""
        if args.dest == "hf-cache":
            return hf_cache_snapshot_dir(spec["hf"])
        return output / key

    failed = []
    for key, spec in targets:
        if not args.no_official and try_hf_official(spec["hf"]):
            continue
        if not fetch_model(key, spec, dest_of(key, spec), args.mirror):
            failed.append(key)

    if failed:
        other = "hf" if args.mirror == "modelscope" else "modelscope"
        log(f"⚠️ 以下模型在 {args.mirror} 失败，改用 {other} 重试: {', '.join(failed)}")
        retry = []
        for key in failed:
            spec = MODELS[key]
            if not fetch_model(key, spec, dest_of(key, spec), other):
                retry.append(key)
        failed = retry

    if failed:
        sys.exit(f"❌ 以下模型未能下载: {', '.join(failed)}。可手动重跑本脚本或改用 --mirror 指定源")

    log("✅ 全部模型下载完成")
    log("模型已按 HF 标准缓存布局写入，代码与 .env 无需任何改动即可离线加载。")


if __name__ == "__main__":
    main()
