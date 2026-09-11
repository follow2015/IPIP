#!/usr/bin/env bash
# ============================================================
# install.sh - ipip 一键安装脚本
# ------------------------------------------------------------
# 功能：
#   0. 固定安装目标：无论从哪个目录执行本脚本，应用一律同步并安装到
#      /opt/ipip（/root、/home 下与 ProtectHome=true 加固互斥，禁止部署）
#   1. 版本基线检查 + 系统依赖
#      基线取本机 dev 实测版本：Python 3.14.7 / Node v26.7.0 / pnpm 10.34.5 /
#      MySQL 8.4+ / Redis 8.0+
#      处理策略：Python、Node、pnpm 低于基线 → 硬失败（已被实测证实会中断
#      安装或运行）；MySQL、Redis 低于基线 → 告警不阻断（本机不可测得，
#      且低版本已实测可用）。做严格分级的目的是：把"悄无声息的环境偏差"
#      变成安装阶段可见的决策点，而不是留到运行时才炸。
#   2. 创建 Python venv 并安装 requirements.txt
#      · 默认安装 **CPU 版 torch**（约 190MB，无 CUDA 依赖）
#      · --gpu 安装 CUDA 版（体积约 2.6-3.5GB，耗时长，见下方用法说明）
#   3. 前端依赖安装 + 构建（pnpm install && pnpm build → frontend-new/dist/）
#   4. 初始化 .env（若不存在则从 .env.example 拷贝，并自动生成
#      SECRET_KEY / JWT_SECRET_KEY / SWITCH_SECRET_KEY 随机密钥）
#   5. 创建数据库并导入 schema + 种子
#   6. 配置监控维护 cron（02:00 预建分区 / 03:00 归档清理）
#   7. 下载 RAG 本地模型到 **HF 标准缓存**（$HF_HOME/hub/models--BAAI--*/snapshots/main/）
#      embedding（bge-small-zh-v1.5）≈92MB + reranker（bge-reranker-base）≈1100MB，
#      默认走 ModelScope 镜像（实测约 5.7MB/s，hf-mirror 仅约 1MB/s）。
#      写入 HF 缓存而非项目目录，是为了与本地开发环境（~/.cache/huggingface）保持
#      同一套解析机制 —— 代码与 .env 都不需要改动。
#      与代码的 HF_HUB_OFFLINE=1 策略配套：模型未预置则 RAG 检索不可用
#      （reranker 缺失会降级为 RRF 排序，不影响基本检索）。
#   8. 【可选】systemd 进程托管（--with-units）：调用 deploy/systemd/install-units.sh
#      渲染并安装 9 个 unit。默认**不做**——接管进程属生产变更且需要 root。
#
# 用法:
#   bash scripts/install.sh                    # 完整安装（默认 CPU 版 torch，推荐）
#   bash scripts/install.sh --gpu              # 安装 CUDA 版 torch（需 NVIDIA GPU；耗时长）
#   bash scripts/install.sh --gpu-fast         # CUDA 版 + 多镜像分散并行预取大包（更快）
#   bash scripts/install.sh --cpu              # 显式指定 CPU 版（等同默认）
#   bash scripts/install.sh --skip-models      # 跳过本地模型下载（不需要 RAG 时用）
#   bash scripts/install.sh --skip-frontend    # 跳过前端构建（假设 frontend-new/dist 已存在）
#   bash scripts/install.sh --skip-db          # 跳过数据库初始化
#   bash scripts/install.sh --skip-seed        # 跳过种子导入
#   bash scripts/install.sh --with-units       # 额外安装 systemd 进程托管 unit（需 root）
#   bash scripts/install.sh --help
#
# torch 版本选择说明（重要）：
#   CPU 版：torch ≈190MB，来自 https://download.pytorch.org/whl/cpu
#           （实测 wheel 下载约 2.8MB/s；注意不要用"首页响应时间"判断该源——
#            首页慢不代表文件下载慢，这是本项目的实测教训）
#   GPU 版：torch ≈554MB，另拖入 nvidia-cudnn/cublas/cusparse/nccl/cusparselt、
#           triton 等 CUDA 依赖，合计 2.6-3.5GB。
#           ⚠️ 预计耗时 30-60 分钟，网络较慢时**可能超过 1 小时**。
#           无 NVIDIA GPU 的服务器请一律使用默认 CPU 版，否则纯属浪费带宽与时间。
#           大包可按包名分散到不同镜像并行下载（--gpu-fast），也可不加该参数
#           走默认单源安装。
#
# 幂等：可重复执行，已存在的步骤会跳过
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# 安装目标固定为 /opt/ipip：deploy/systemd 单元模板启用 ProtectHome=true，
# 该档位使 /root、/home、/run/user 对服务进程**完全不可见**——项目放这两处
# 服务必然起不来（systemd 203/EXEC 反复重启）。因此无论本脚本从哪个目录执行，
# 应用一律先同步到 /opt/ipip 再做后续安装（.env/instance/logs 重装时保留）。
PROJECT_ROOT="/opt/ipip"

# 颜色输出
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INSTALL]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()  { err "$*"; exit 1; }

# ── 安装进度反馈 & pip 源自动选择 ───────────────────────────────
# 背景：pip install 是全流程最慢的一步，过去用 -q 完全静默，运维无法判断
# "在装"还是"卡死"。此处提供三件事：
#   ① 步骤计时——每个长步骤打印起止与耗时；
#   ② pip 实时输出——去掉 -q 并强制 PYTHONUNBUFFERED，日志重定向时也能 tail -f 看到滚动；
#   ③ 源自动切换——官方慢到阈值以上即切清华镜像，安装失败再自动重试一次。

# 判据必须是**真实下载吞吐**，不能是 curl 首页响应时间，也不能是"小包能否装完"：
#   - 官方源首页 0.98s 可用，但大文件下载可能只有几百 KB/s（首页延迟与吞吐无关）；
#   - numpy(16MB) 这类小文件官方 CDN 也能 30~60s 装完，"装完=可用"会误判，
#     导致 torch(≈554MB+依赖链) 全程走官方源——实测仅几百 KB/s，而清华源可到 4MB/s。
# 故用 pip download --no-cache-dir 实测下载 numpy 的吞吐，低于阈值即切镜像；
# 两个源都测，取吞吐高者。--no-cache-dir 防止缓存命中造成"秒回=快"的假象。
PIP_INSTALL_TIMEOUT="${PIP_INSTALL_TIMEOUT:-120}"   # 单源探测上限（秒）
PIP_MIN_SPEED_KBPS="${PIP_MIN_SPEED_KBPS:-1024}"    # 可接受吞吐下限（KB/s，1024=1MB/s）
PIP_INDEX_OFFICIAL="https://pypi.org/simple"
# 兜底源用中科大 USTC：清华/阿里镜像对长时间大文件下载限速（实测教训），
# USTC 无此策略。不再把清华作为 pip 兜底。
PIP_INDEX_FALLBACK="https://mirrors.ustc.edu.cn/pypi/web/simple"
PIP_INDEX_ARG=""   # 空=官方源；非空=携带 -i <url>
# 探测包取项目自身依赖之一，中等体积（numpy 约 16MB wheel）：太小反映不出
# 大文件（torch ≈554MB）场景的真实吞吐，太大又拖慢探测本身。
PIP_PROBE_PACKAGE="${PIP_PROBE_PACKAGE:-numpy}"

# 实测某源的下载吞吐（KB/s）。用 pip download 只下载不安装。
# 0 字节（源不可达/立即失败）时输出空并返回非 0；超时被杀的部分下载
# 也算有效样本（字节数/总耗时=真实窗口吞吐）。
#   - 用 bash 后台进程 + watchdog 定时 kill 计时，不依赖 GNU timeout
#     （macOS 无此命令，且缺它时探测会无限挂起）；
#   - 耗时用 python time.monotonic() 取浮点秒：date +%s 秒级精度下"1 秒内
#     完成"会把速率放大上千倍（实测出过 2662MB/s 的荒谬值）。
probe_speed_kbps() {
  local index="$1" dir start elapsed bytes
  dir="$(mktemp -d)"
  start=$("$VENV_PY" -c 'import time; print(time.monotonic())')
  "$VENV_PY" -m pip download \
    --no-cache-dir --no-deps --disable-pip-version-check -q \
    -d "$dir" -i "$index" "$PIP_PROBE_PACKAGE" >/dev/null 2>&1 &
  local pid=$!
  ( sleep "$PIP_INSTALL_TIMEOUT" 2>/dev/null; kill "$pid" 2>/dev/null ) &
  local watchdog=$!
  wait "$pid" 2>/dev/null
  kill "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
  elapsed=$("$VENV_PY" -c "import time; print(max(0.01, time.monotonic() - $start))")
  bytes=$(du -sk "$dir" 2>/dev/null | cut -f1)
  rm -rf "$dir"
  [ -n "$bytes" ] && [ "$bytes" -gt 0 ] || return 1
  echo "$bytes" "$elapsed" | awk '{ printf "%d", $1 / $2 }'   # du -sk 已是 KB
}

human_speed() {  # KB/s → 人类可读
  awk -v k="$1" 'BEGIN{ if (k>=1024) printf "%.1fMB/s", k/1024; else printf "%dKB/s", k }'
}

select_pip_index() {
  # 支持强制指定源（跳过探测）：PIP_INDEX_URL=<url> bash scripts/install.sh
  if [ -n "${PIP_INDEX_URL:-}" ]; then
    PIP_INDEX_ARG="-i $PIP_INDEX_URL"
    log "使用 PIP_INDEX_URL 强制指定的 pip 源: $PIP_INDEX_URL"
    return 0
  fi
  local official_kbps tuna_kbps
  log "实测 pip 下载吞吐（探测包 ${PIP_PROBE_PACKAGE}，上限 ${PIP_INSTALL_TIMEOUT}s/源）..."
  official_kbps=$(probe_speed_kbps "$PIP_INDEX_OFFICIAL")
  log "  官方源 pypi.org：$(human_speed "${official_kbps:-0}")"
  if [ -n "$official_kbps" ] && [ "$official_kbps" -ge "$PIP_MIN_SPEED_KBPS" ]; then
    log "官方源吞吐达标（≥ $(human_speed "$PIP_MIN_SPEED_KBPS")），沿用官方源"
    return 0
  fi
  warn "官方源吞吐不足/不可用，实测中科大源..."
  fallback_kbps=$(probe_speed_kbps "$PIP_INDEX_FALLBACK")
  log "  中科大源：$(human_speed "${fallback_kbps:-0}")"
  if [ -z "$fallback_kbps" ]; then
    warn "两个源均不可用，仍沿用官方源继续（后续安装可能很慢或失败）"
    return 0
  fi
  PIP_INDEX_ARG="-i $PIP_INDEX_FALLBACK"
  if [ -z "$official_kbps" ] || [ "$fallback_kbps" -ge "$official_kbps" ]; then
    log "切换中科大源（${fallback_kbps}KB/s），后续依赖均走 ${PIP_INDEX_FALLBACK}"
  else
    warn "中科大源反而更慢，沿用官方源（${official_kbps}KB/s）"
    PIP_INDEX_ARG=""
  fi
}

# ── Node 源自动选择（同样以真实下载为判据）─────────────────────
NPM_REGISTRY_OFFICIAL="https://registry.npmjs.org"
NPM_REGISTRY_MIRROR="https://registry.npmmirror.com"
NPM_REGISTRY=""
NODE_PROBE_TIMEOUT="${NODE_PROBE_TIMEOUT:-120}"
NODE_PROBE_PACKAGE="debug"   # 极小且无依赖，专门用作网络速度试金石

select_npm_registry() {
  # 幂等：同一轮安装中只实测一次（第 1 步装 pnpm 与第 3 步构建都会用到）
  if [ -n "$NPM_REGISTRY" ]; then return 0; fi
  local probe_dir
  probe_dir="$(mktemp -d)"
  log "实测 npm registry 下载速度：安装 ${NODE_PROBE_PACKAGE}（上限 ${NODE_PROBE_TIMEOUT}s）..."
  if timeout "$NODE_PROBE_TIMEOUT" npm install --prefix "$probe_dir" \
       --registry "$NPM_REGISTRY_OFFICIAL" --no-audit --no-fund \
       --loglevel=error "$NODE_PROBE_PACKAGE" >/dev/null 2>&1; then
    NPM_REGISTRY="$NPM_REGISTRY_OFFICIAL"
    log "npm 官方 registry 可用"
  else
    warn "npm 官方 registry 过慢/超时 —— 切换 ${NPM_REGISTRY_MIRROR}"
    NPM_REGISTRY="$NPM_REGISTRY_MIRROR"
  fi
  rm -rf "$probe_dir"
}

# pnpm 安装：不要依赖 corepack
# 理由：corepack 会从 registry 拉 pnpm 版本签名并用内置公钥校验，在部分
# node/corepack 组合下失败（Node 20.18.1 实测报 "Cannot find matching keyid"）。
# 更重要的是它会留下**可执行但一跑就崩**的 shim，导致 command -v pnpm 误判为已安装。
ensure_pnpm() {
  local want="${1:-${PNPM_VERSION:-10.34.5}}"
  local have=""
  # 判据必须是真跑一次 pnpm：corepack 会留下"可执行但一跑就崩"的 shim，
  # command -v pnpm 会误判为已安装。
  if command -v pnpm >/dev/null 2>&1; then have="$(pnpm --version 2>/dev/null || true)"; fi
  if [ -n "$have" ] && ver_ge "$have" "$want"; then
    log "pnpm: $have ✓ (>= $want)"
    return 0
  fi
  if [ -n "$have" ]; then
    warn "pnpm 版本过低（$have < ${want}），将升级到 $want"
  else
    warn "pnpm 不可用（缺失，或 corepack shim 签名校验失败），改用 npm 全局安装 pnpm@${want}"
  fi
  local PNPM_VERSION="$want"
  # 清掉 corepack 残留 shim，否则 npm install -g 会因同名文件冲突直接拒绝安装
  local pnpm_path
  pnpm_path="$(command -v pnpm 2>/dev/null || true)"
  if [ -n "$pnpm_path" ] && [ -f "$pnpm_path" ]; then
    warn "移除冲突/损坏的 corepack shim: $pnpm_path"
    rm -f "$pnpm_path" "$(dirname "$pnpm_path")/pnpx" 2>/dev/null || true
  fi
  select_npm_registry
  npm install -g "pnpm@${PNPM_VERSION}" --registry "$NPM_REGISTRY" --no-audit --no-fund \
    || die "pnpm 安装失败，请手动执行: npm i -g pnpm@${PNPM_VERSION}"
  log "pnpm: $(pnpm --version)"
}

# C++ 编译工具链：必须在安装 Python 依赖之前就绪
# 为什么是硬要求：chroma-hnswlib（chromadb 的依赖）在 PyPI 上**只有 sdist**，
# 必须本地编译。缺 g++ 时 pip 报 "Failed to build chroma-hnswlib"，而 pip 的
# 安装是**原子性**的——一个包构建失败会导致整个 requirements 都不安装
# （实测 venv 只剩 8 个基础包，直到第 5 步连不上数据库才暴露，排查成本极高）。
ensure_build_toolchain() {
  if command -v g++ >/dev/null 2>&1; then
    log "C++ 编译器: $(g++ --version | head -1) ✓"
    return 0
  fi
  warn "未找到 g++：chroma-hnswlib 等包只有源码分发，必须本地编译"
  local apt_cmd="" yum_cmd=""
  command -v apt-get >/dev/null 2>&1 && apt_cmd="apt-get"
  command -v dnf >/dev/null 2>&1 && yum_cmd="dnf"
  command -v yum >/dev/null 2>&1 && yum_cmd="${yum_cmd:-yum}"
  if [ -n "$apt_cmd" ] && { [ "$(id -u)" -eq 0 ] || command -v sudo >/dev/null 2>&1; }; then
    [ "$(id -u)" -eq 0 ] || apt_cmd="sudo $apt_cmd"
    log "安装编译工具链 build-essential + cmake（约 1-2 分钟）..."
    DEBIAN_FRONTEND=noninteractive $apt_cmd update -qq
    DEBIAN_FRONTEND=noninteractive $apt_cmd install -y build-essential cmake python3-dev \
      || die "编译工具链安装失败，请手动执行：apt-get install -y build-essential cmake python3-dev"
  elif [ -n "$yum_cmd" ]; then
    log "安装编译工具链 Development Tools + cmake ..."
    $yum_cmd groupinstall -y "Development Tools" && $yum_cmd install -y cmake python3-devel \
      || die "编译工具链安装失败，请手动执行：yum groupinstall -y 'Development Tools'"
  else
    die "缺少 C++ 编译器且未找到受支持的包管理器。请安装后重跑：
      · Debian/Ubuntu : apt-get install -y build-essential cmake python3-dev
      · CentOS/RHEL   : yum groupinstall -y 'Development Tools' && yum install -y cmake python3-devel"
  fi
  command -v g++ >/dev/null 2>&1 \
    || die "g++ 安装后仍不可用，无法编译 chroma-hnswlib，安装中止"
  log "C++ 编译器已就绪"
}

run_timed() {
  # 执行一条命令并汇报耗时，避免长步骤看起来像卡死
  local name="$1"; shift
  local started=${SECONDS}
  log "▶ $name ..."
  # ⚠️ 不能在 if 之后再取 $?：那时拿到的是 if 语句自身的状态（常为 0），会把失败
  # 伪造成成功，导致后续步骤带着半成品环境继续跑（实测踩到：pip 安装失败却
  # 一路推进到第 5 步才炸，报错点离根因很远）。
  local rc=0
  "$@" || rc=$?
  if [ "$rc" -eq 0 ]; then
    log "✔ $name 完成（耗时 $((SECONDS - started))s）"
  else
    err "✘ $name 失败（退出码 ${rc}，耗时 $((SECONDS - started))s）"
  fi
  return ${rc}
}

# 参数解析
# 用 while+shift 而非 for：新增的 --units-user/--units-group/--units-script 需要
# 取值，for 循环无法消费下一个参数（会把值当成未知参数直接 die）。
SKIP_FRONTEND=0
SKIP_DB=0
SKIP_SEED=0
SKIP_MODELS=0
TORCH_FLAVOR="cpu"      # cpu（默认）| gpu
CUDA_MULTI_MIRROR=0     # 1=用多镜像分散并行预取 CUDA 大包（--gpu-fast）
WITH_UNITS=0            # 1=安装完成后渲染并安装 systemd unit（T2.1）
UNITS_USER=""           # 空=由 install-units.sh 决定默认账号（ipip）
UNITS_GROUP=""
UNITS_SCRIPT=""         # 空=按仓库布局自动探测
while [ $# -gt 0 ]; do
  case "$1" in
    # flag 形式
    --skip-frontend) SKIP_FRONTEND=1; shift ;;
    --skip-db)       SKIP_DB=1; shift ;;
    --skip-seed)     SKIP_SEED=1; shift ;;
    --skip-models)   SKIP_MODELS=1; shift ;;
    --cpu)           TORCH_FLAVOR="cpu"; shift ;;
    --gpu)           TORCH_FLAVOR="gpu"; shift ;;
    --gpu-fast)      TORCH_FLAVOR="gpu"; CUDA_MULTI_MIRROR=1; shift ;;
    --with-units)    WITH_UNITS=1; shift ;;
    # 取值形式（同时支持 "--k v" 与 "--k=v"）
    # 缺值时给出与前文一致的 [ERROR] 提示，而不是 bash 默认的 "line N: 2: ..."
    --units-user)
      [ $# -ge 2 ] || die "--units-user 需要一个账号名（如 --units-user root）"
      UNITS_USER="$2"; shift 2 ;;
    --units-group)
      [ $# -ge 2 ] || die "--units-group 需要一个组名（如 --units-group root）"
      UNITS_GROUP="$2"; shift 2 ;;
    --units-script)
      [ $# -ge 2 ] || die "--units-script 需要一个路径"
      UNITS_SCRIPT="$2"; shift 2 ;;
    --units-user=*)   UNITS_USER="${1#*=}"; shift ;;
    --units-group=*)  UNITS_GROUP="${1#*=}"; shift ;;
    --units-script=*) UNITS_SCRIPT="${1#*=}"; shift ;;
    --help|-h)
      sed -n '2,55p' "$0"
      cat <<'HELP'

systemd 进程托管（可选，需 root）:
  --with-units            安装完成后渲染并安装 systemd unit
  --units-user NAME       服务运行账号（默认 ipip；项目在 /root 下应为 root）
  --units-group NAME      服务运行组（默认同 --units-user）
  --units-script PATH     指定 install-units.sh 路径
                          （默认探测 <repo>/deploy/systemd/install-units.sh）
HELP
      exit 0
      ;;
    *) die "未知参数: $1（用 --help 查看用法）" ;;
  esac
done

# ── 0. 代码副本同步到固定安装目录 ──────────────────────────────
# 重装/升级时 .env、instance/（运行时数据）、logs/ 不被覆盖；.venv 由第 2 步
# 在安装目录内新建。--delete 让安装目录与代码副本严格一致（陈旧文件不留存）。
if [ "$SOURCE_ROOT" != "$PROJECT_ROOT" ]; then
  log "同步代码副本: $SOURCE_ROOT → $PROJECT_ROOT"
  mkdir -p "$PROJECT_ROOT"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude ".venv/" --exclude ".git/" --exclude ".env" \
      --exclude "instance/" --exclude "logs/" --exclude "__pycache__/" \
      --exclude "node_modules/" \
      "$SOURCE_ROOT/" "$PROJECT_ROOT/" \
      || die "代码同步到 $PROJECT_ROOT 失败（rsync）"
  else
    tar -C "$SOURCE_ROOT" \
      --exclude="./.venv" --exclude="./.git" --exclude="./.env" \
      --exclude="./instance" --exclude="./logs" --exclude="__pycache__" \
      --exclude="./node_modules" -cf - . | tar -C "$PROJECT_ROOT" -xf - \
      || die "代码同步到 $PROJECT_ROOT 失败（tar 回退路径）"
  fi
else
  log "副本已位于安装目录 $PROJECT_ROOT，跳过同步"
fi
cd "$PROJECT_ROOT"

log "项目根目录: $PROJECT_ROOT"

# ── 1. 系统依赖与版本基线检查 ──────────────────────────────
log "=== [1/7] 检查系统依赖与版本基线 ==="

# ══ 版本基线＝本机 dev 环境实测版本 ═══════════════════════════
# 低于基线＝未经完整验证的环境。分级处理：
#   硬失败(DIE)：已被实测证实会导致安装或运行中断的项
#   告警(WARN) ：本机无法直接测得，或已实测可运行的项（仅提示偏差）
PYTHON_MIN="3.14"      # 本机 3.14.7
NODE_MIN="26.7"        # 本机 v26.7.0
PNPM_MIN="10.34.5"     # frontend-new/package.json 的 packageManager
MYSQL_MIN="8.4"        # 安装文档标称版本
REDIS_MIN="8.0"        # 本机 Redis server 8.10.1

# 版本比较：ver_ge <当前> <最低>，满足返回 0
ver_ge() {
  awk -v cur="$1" -v min="$2" '
    BEGIN{ n=split(cur,a,"."); m=split(min,b,".")
           for(i=1;i<=m;i++){ if(a[i]+0>b[i]+0) exit 0; if(a[i]+0<b[i]+0) exit 1 }
           exit 0 }'
}

# Python：必须 >= 3.14，**不允许降级**
# 理由：realtime_gateway 使用 asyncio.AsyncGenerator，该属性在 Python 3.14 才存在；
# 旧脚本"找不到 3.14 就降级继续"会把必然崩溃压缩成一行 WARN，部署完成后才发现
# gateway 起不来，排查成本极高。
PY_BIN=""
for c in python3.14 python3.13 python3.12 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v="$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0.0)"
    if ver_ge "$v" "$PYTHON_MIN"; then PY_BIN="$c"; break; fi
  fi
done
if [ -z "$PY_BIN" ]; then
  die "未找到 Python >= ${PYTHON_MIN}（当前系统最高 $(python3 --version 2>/dev/null || echo 未知)）。
  这是硬性要求：realtime_gateway 的 asyncio.AsyncGenerator 在更低版本不存在，启动即崩。
  安装方式（任选其一）：
    · uv（推荐）: curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.14
    · PPA      : sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt-get install -y python3.14 python3.14-venv
    · 官方源    : https://www.python.org/downloads/"
fi
log "Python: $PY_BIN ($("$PY_BIN" --version 2>&1)) ✓ (>= $PYTHON_MIN)"

# Node（前端构建必需）
if [ "$SKIP_FRONTEND" -eq 0 ]; then
  if ! command -v node >/dev/null 2>&1; then
    die "未找到 node。前端构建需要 Node >= ${NODE_MIN}，请先安装：https://nodejs.org/"
  fi
  # 判据取本机 dev 基线，而非"主版本 >= 20"：vite 8 / rolldown 的 engines 为
  # ^20.19.0 || >=22.12.0，Node 20.18.x 能通过粗放的主版本检查，但 pnpm 会
  # **静默跳过**不满足 engines 的可选原生依赖(@rolldown/binding-linux-x64-gnu)，
  # 到构建阶段才报 Cannot find native binding —— 报错点离根因很远，极难排查。
  cur_node="$(node -v 2>/dev/null | sed 's/^v//')"
  if ! ver_ge "${cur_node:-0.0}" "$NODE_MIN"; then
    die "Node 版本过低：当前 v${cur_node}，基线要求 >= ${NODE_MIN}（本机 dev = v26.7.0）。
  升级方式（任选其一）：
    · nvm    : nvm install 26 && nvm use 26
    · 二进制 : https://nodejs.org/dist/latest-v26.x/ 下载 linux-x64 包解压到 /usr/local
    · NodeSource: https://github.com/nodesource/distributions"
  fi
  log "Node: $(node --version) ✓ (>= $NODE_MIN)"

  # pnpm：低于基线版本则自动安装/升级
  ensure_pnpm "$PNPM_MIN"
fi

# MySQL（WARN 级：8.0.x 已实测可完成部署，但不等于 dev 基线，仅记录偏差）
MYSQL_CLIENT=""
for c in mysql mysql8; do
  if command -v "$c" >/dev/null 2>&1; then MYSQL_CLIENT="$c"; break; fi
done
if [ -n "$MYSQL_CLIENT" ]; then
  mysql_ver="$("$MYSQL_CLIENT" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)"
  if ver_ge "${mysql_ver:-0.0}" "$MYSQL_MIN"; then
    log "MySQL: ${mysql_ver} ✓ (>= $MYSQL_MIN)"
  else
    warn "MySQL ${mysql_ver:-未知} 低于基线 ${MYSQL_MIN}。8.0.x 已实测可跑通部署，但属于「未验证组合」，
      生产环境建议对齐，避免 payroll/json 相关 SQL 行为差异。"
  fi
else
  warn "未找到 mysql 客户端，将使用 PyMySQL 导入 SQL（功能等价）"
fi

# Redis（WARN 级：本机 dev 为 8.10.1）
if command -v redis-server >/dev/null 2>&1; then
  redis_ver="$(redis-server --version 2>/dev/null | grep -oE 'v=[0-9]+\.[0-9]+(\.[0-9]+)?' | cut -d= -f2)"
elif command -v redis-cli >/dev/null 2>&1; then
  redis_ver="$(redis-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)"
else
  warn "未找到 redis-server / redis-cli。Redis 为缓存与 Celery broker，必须另行安装并启动。"
  redis_ver=""
fi
if [ -n "${redis_ver:-}" ]; then
  if ver_ge "$redis_ver" "$REDIS_MIN"; then
    log "Redis: ${redis_ver} ✓ (>= $REDIS_MIN)"
  else
    warn "Redis ${redis_ver} 低于 dev 基线 ${REDIS_MIN}（本机 8.10.1）。基础功能可用，但属「未验证组合」。"
  fi
fi

# C++ 编译工具链必须在装 Python 依赖之前就绪（chroma-hnswlib 只有 sdist，需本地编译）
ensure_build_toolchain

# ── 2. Python 虚拟环境 ─────────────────────────────────────
log "=== [2/7] 创建 Python venv 并安装依赖 ==="
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "创建 venv: $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
else
  log "venv 已存在，跳过创建"
fi
VENV_PY="$VENV_DIR/bin/python"

# 选择 pip 源（官方慢则自动切清华）
select_pip_index
# 日志被重定向到文件时 pip 输出会被缓冲，导致 tail -f 看不到滚动进度；
# PYTHONUNBUFFERED=1 让其行缓冲实时落盘。
export PYTHONUNBUFFERED=1

# ⚠️ 为什么用 script 包一层（而不是直接调用 pip）：
# pip 检测到输出不是终端(TTY)时会**不渲染进度条**。依赖树里的 torch ≈554MB，
# 下载期间日志一行不动，运维极易误判为"卡死"而反复重启安装——而 pip
# **不支持断点续传**，每次重来都要从 0 下载这 554MB，于是陷入死循环。
# script -qec 提供伪终端，让进度实时可见（tail -f 也能看到滚动）。
pip_tty() {
  script -qec "$VENV_PY -m pip install $*" /dev/null
}

# ── CUDA 大包「多镜像分散 + 多连接分段」预取（仅 --gpu-fast）─────
# 背景：pip 单连接下载 500MB 级大包既慢（实测 200-900KB/s 且逐渐衰减）又
# **不支持断点续传**；同一文件用 curl 多连接分段实测可达 4.8MB/s。故按包名把
# 大包分散到不同镜像，包内再分段并行下载，最后本地离线安装。
# 不加 --gpu-fast 则不做预取，直接走 pip 默认安装（简单但慢，可能超 1 小时）。
CUDA_MIRROR_POOL=(
  "https://mirrors.ustc.edu.cn/pypi/web"
  "https://pypi.org"
  "https://mirrors.cloud.tencent.com/pypi"
)
PIP_WHEEL_CACHE="${PIP_WHEEL_CACHE:-/tmp/ipip-wheels}"
CUDA_SEGMENTS="${CUDA_SEGMENTS:-8}"

prefetch_one_wheel() {
  # $1=包名 $2=wheel 文件名 $3=镜像基址
  local pkg="$1" fn="$2" mirror="$3" out="$PIP_WHEEL_CACHE/$2"
  local u="" full="" total="" seg n="$CUDA_SEGMENTS" i s e fin
  [ -f "$out" ] && { log "  已缓存 $pkg"; return 0; }
  u=$(curl -s -m 20 "$mirror/simple/$pkg/" | grep -oE "href=\"[^\"]*$fn[^\"]*\"" | head -1 | sed 's/href="//;s/"$//')
  if [ -z "$u" ]; then warn "  $pkg 在 ${mirror#https://} 未找到，跳过"; return 1; fi
  case "$u" in
    http*) full="$u" ;;
    ../*)  full="$mirror/${u#../../}" ;;
    *)     full="$mirror/$u" ;;
  esac
  total=$(curl -sIL -m 20 "$full" | grep -i content-length | tail -1 | tr -dc 0-9)
  if [ -z "$total" ] || [ "$total" -le 0 ]; then warn "  $pkg 无法获取大小，跳过"; return 1; fi
  seg=$(( (total + n - 1) / n ))
  log "  预取 ${pkg}（$((total/1048576))MB，源 ${mirror#https://}，${n} 连接并行）..."
  for i in $(seq 0 $((n-1))); do
    s=$((i*seg)); e=$((s+seg-1))
    [ "$e" -ge "$total" ] && e=$((total-1))
    [ "$s" -gt "$e" ] && continue
    curl -sL --retry 10 --retry-all-errors -r "$s-$e" -o "$out.part$i" "$full" >/dev/null 2>&1 &
  done
  wait
  cat "$out".part* > "$out" 2>/dev/null; rm -f "$out".part*
  fin=$(stat -c%s "$out" 2>/dev/null || echo 0)
  if [ "$fin" -eq "$total" ]; then
    log "  ✔ $pkg 完成"
  else
    warn "  ✘ $pkg 大小不符（$fin/${total}），丢弃重来"
    rm -f "$out"; return 1
  fi
}

prefetch_cuda_multi_mirror() {
  local report="$PIP_WHEEL_CACHE/cuda-report.json" list="$PIP_WHEEL_CACHE/jobs.tsv"
  local ok=0 fail=0 pkg fn mirror w
  mkdir -p "$PIP_WHEEL_CACHE"
  log "生成依赖清单（pip --dry-run，只解析不下载）..."
  "$VENV_PY" -m pip install --dry-run --ignore-installed --report "$report" \
    -r "$PROJECT_ROOT/requirements.txt" $PIP_INDEX_ARG >/dev/null 2>&1 || return 1
  "$VENV_PY" - "$report" "$list" "${CUDA_MIRROR_POOL[@]}" <<'PYEOF'
import json, sys
report, out, *mirrors = sys.argv[1:]
d = json.load(open(report))
rows = []
for it in d.get("install", []):
    url = (it.get("download_info") or {}).get("url", "")
    if not url.endswith(".whl"):
        continue
    fn = url.rsplit("/", 1)[-1].split("#")[0]
    # 只挑 CUDA/triton 这类超大包，其余交给 pip 正常安装
    if not fn.startswith(("nvidia_", "nvidia-", "triton-")):
        continue
    rows.append((fn.split("-")[0].replace("_", "-"), fn))
with open(out, "w") as f:
    for i, (pkg, fn) in enumerate(rows):
        f.write(f"{pkg}\t{fn}\t{mirrors[i % len(mirrors)]}\n")
print(f"待预取 {len(rows)} 个 CUDA/triton 大包，按包名分散到 {len(mirrors)} 个镜像",
      file=sys.stderr)
PYEOF
  while IFS=$'\t' read -r pkg fn mirror; do
    [ -z "$pkg" ] && continue
    if prefetch_one_wheel "$pkg" "$fn" "$mirror"; then ok=$((ok+1)); else fail=$((fail+1)); fi
  done < "$list"
  log "预取结束：成功 $ok 个，失败 $fail 个"
  if [ "$ok" -gt 0 ]; then
    # 用**文件路径**离线安装，而不是 --find-links：后者只是候选源，pip 仍会优先
    # 去 index 下载（实测踩过，白等一次全量下载）。--no-deps 让依赖由后续
    # requirements 安装补齐。
    local wheels=()
    for w in "$PIP_WHEEL_CACHE"/*.whl; do [ -e "$w" ] && wheels+=("$w"); done
    if [ "${#wheels[@]}" -gt 0 ]; then
      run_timed "离线安装已预取的 CUDA 包" pip_tty "${wheels[*]} --no-deps" \
        || warn "离线安装部分失败，将由后续 requirements 安装补齐"
    fi
  fi
  [ "$fail" -eq 0 ]
}

# ── torch 版本选择（CPU 默认 / GPU 需显式 --gpu）──────────────
if [ "$TORCH_FLAVOR" = "cpu" ]; then
  # CPU 版仅 torch 本体 ≈190MB，无 CUDA 依赖。
  # ⚠️ 该源的"首页响应时间"不能当作速度判据：实测首页仅 57KB/s，但 wheel 真实
  # 下载可达 2.8MB/s。判断源快慢必须测真实文件（本项目反复踩过的坑）。
  cur_torch="$("$VENV_PY" -c "import importlib.metadata as m; print(m.version('torch'))" 2>/dev/null || true)"
  need_cpu=1
  case "$cur_torch" in
    *+cpu*) log "已安装 CPU 版 torch（${cur_torch}），跳过"; need_cpu=0 ;;
  esac
  if [ "$need_cpu" -eq 1 ]; then
    if [ -n "$cur_torch" ]; then
      warn "当前 torch=$cur_torch 不是 CPU 版（无 +cpu 标记），将替换为 CPU 版"
      # --force-reinstall 是必需的：已装同版本号但非 +cpu 时，pip 会判定
      # "Requirement already satisfied" 而**直接跳过**（实测踩到：安装仅耗时 2s、
      # 版本号与 nvidia 依赖都原封不动）。--no-deps 避免连带重装依赖。
    fi
    log "torch 版本：CPU（默认，≈190MB）"
    run_timed "安装 CPU 版 torch" pip_tty \
      "torch --index-url https://download.pytorch.org/whl/cpu --extra-index-url $PIP_INDEX_FALLBACK --force-reinstall --no-deps --progress-bar on --timeout 60 --retries 5" \
      || die "CPU 版 torch 安装失败。可手动执行：
      $VENV_PY -m pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cpu"
    # 从 CUDA 版切换过来时，此前的 nvidia-* 包会残留（对 CPU 版无用，白占数 GB）
    if "$VENV_PY" -m pip list 2>/dev/null | grep -qi "^nvidia-"; then
      warn "检测到残留的 CUDA 依赖包（nvidia-*，对 CPU 版 torch 无用），可执行以下命令清理："
      warn "  $VENV_PY -m pip uninstall -y \$($VENV_PY -m pip list --format=freeze | grep -i '^nvidia-' | cut -d= -f1 | tr '\\n' ' ')"
    fi
  fi
else
  warn "════════════════════════════════════════════════════════════"
  warn "已选择 GPU (CUDA) 版本 torch"
  warn "  · 体积：torch 554MB + nvidia-cudnn/cublas/cusparse/nccl/cusparselt"
  warn "           + triton 等，合计约 2.6-3.5 GB"
  warn "  · 耗时：预计 30-60 分钟，网络较慢时【可能超过 1 小时】"
  warn "  · 前提：服务器需有 NVIDIA GPU；若无 GPU，这些依赖完全用不上，"
  warn "           强烈建议改用默认 CPU 版（直接 bash scripts/install.sh）"
  warn "  · 加速：加 --gpu-fast 可把大包分散到多镜像并行下载"
  warn "════════════════════════════════════════════════════════════"
  if [ "$CUDA_MULTI_MIRROR" -eq 1 ]; then
    prefetch_cuda_multi_mirror || warn "分散预取未完全成功，未覆盖部分回退 pip 默认安装"
  fi
  log "torch 版本：GPU（CUDA）"
fi

run_timed "升级 pip" script -qec "$VENV_PY -m pip install --upgrade pip wheel setuptools $PIP_INDEX_ARG --timeout 30 --retries 3" /dev/null

# 大文件易受网络抖动影响，单次连接超时放宽到 60s；失败则自动换备用镜像重试一次。
# 若两次都失败，多半是 requirements.txt 内部版本冲突（非网络问题）。
if run_timed "安装 requirements.txt" pip_tty \
      "-r $PROJECT_ROOT/requirements.txt $PIP_INDEX_ARG --progress-bar on --timeout 60 --retries 5"; then
  :
else
  warn "依赖安装失败，尝试改用中科大镜像重试一次..."
  run_timed "安装 requirements.txt（中科大镜像重试）" pip_tty \
      "-r $PROJECT_ROOT/requirements.txt -i $PIP_INDEX_FALLBACK --progress-bar on --timeout 60 --retries 5" \
    || die "依赖安装失败。若报错为 ResolutionImpossible/版本冲突，属 requirements.txt 内部矛盾（非网络问题）；若卡在大包下载，可加 --gpu-fast 或设置 PIP_INDEX_URL 指定更快镜像。"
fi
log "Python 依赖安装完成"

# ── 3. 前端构建 ────────────────────────────────────────────
log "=== [3/7] 前端构建 ==="
FRONTEND_DIR="$PROJECT_ROOT/frontend-new"
if [ "$SKIP_FRONTEND" -eq 1 ]; then
  if [ -d "$FRONTEND_DIR/dist" ] && [ -f "$FRONTEND_DIR/dist/index.html" ]; then
    log "跳过前端构建（--skip-frontend），使用已有 dist/"
  else
    die "frontend-new/dist 不存在，不能跳过前端构建。请去掉 --skip-frontend。"
  fi
else
  if [ ! -f "$FRONTEND_DIR/package.json" ]; then
    die "frontend-new/package.json 不存在"
  fi
  cd "$FRONTEND_DIR"
  select_npm_registry
  log "安装前端依赖 (pnpm install)..."
  # 实测教训：小包探测能过不代表大依赖树能撑住——官方 registry 在完整安装时
  # 掉到 24 KiB/s 并丢失 rolldown 原生 binding 包导致构建失败。故首次尝试
  # 失败后，一律用 npmmirror 重试一次再判定失败。
  install_frontend_deps() {
    pnpm install --frozen-lockfile --registry "$NPM_REGISTRY" 2>/dev/null \
      || pnpm install --registry "$NPM_REGISTRY"
  }
  if ! install_frontend_deps; then
    warn "前端依赖安装失败，改用 ${NPM_REGISTRY_MIRROR} 重试一次..."
    NPM_REGISTRY="$NPM_REGISTRY_MIRROR"
    install_frontend_deps \
      || die "前端依赖安装失败（官方与 npmmirror 均失败），请检查网络后手动执行 pnpm install"
  fi
  log "构建前端 (pnpm build)..."
  pnpm build
  cd "$PROJECT_ROOT"
  if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
    die "前端构建失败，frontend-new/dist/index.html 未生成"
  fi
  log "前端构建完成: frontend-new/dist/ ($(du -sh "$FRONTEND_DIR/dist" | cut -f1))"
fi

# ── 4. .env 初始化 ─────────────────────────────────────────
log "=== [4/7] 初始化 .env ==="
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  warn ".env 已从 .env.example 创建。请编辑 $PROJECT_ROOT/.env 填写实际数据库/Redis 密码后重新运行本脚本。"
  warn "（若已配置好 .env，可忽略此提示，脚本将继续执行）"
else
  log ".env 已存在，跳过创建"
fi

# 安全密钥自动注入：SECRET_KEY / JWT_SECRET_KEY / SWITCH_SECRET_KEY 凡缺失（含整行
# 不存在、空值、或仍是 change-me 占位符）一律生成 64 位随机 hex，杜绝弱默认密钥
# 上线（生产配置对占位符会直接拒绝启动，此处提前修复，避免部署者漏填）。
# SWITCH_SECRET_KEY 是设备凭据加密密钥，FLASK_ENV=production 时**强制非空**，
# 缺失会让服务启动即崩（实测：monitor 因此被 systemd 反复拉起后进入 failed）。
"$VENV_PY" - <<PYEOF
import re, secrets
from pathlib import Path

p = Path("$PROJECT_ROOT/.env")
lines = p.read_text().splitlines()
generated = []
targets = {"SECRET_KEY", "JWT_SECRET_KEY", "SWITCH_SECRET_KEY"}
present = set()
for i, line in enumerate(lines):
    m = re.match(r"^([A-Z_]+)=(.*)$", line)
    if not m or m.group(1) not in targets:
        continue
    present.add(m.group(1))
    val = m.group(2).strip()
    if val == "" or val.lower().startswith("change-me"):
        lines[i] = f"{m.group(1)}={secrets.token_hex(32)}"
        generated.append(m.group(1))
# ⚠️ 必须补齐「整行缺失」的键：.env 通常是从**旧版** .env.example 拷贝而来，
# 后续在模板里新增的密钥键在其中根本不存在。只遍历已有行的写法会永远补不上它
# （实测踩到：.env.example 已加 SWITCH_SECRET_KEY，装机后 .env 里始终没有该键，
#   直到 FLASK_ENV=production 启动时才以崩溃形式暴露）。
for key in sorted(targets - present):
    lines.append(f"{key}={secrets.token_hex(32)}")
    generated.append(key + "(新增)")
if generated:
    p.write_text("\n".join(lines) + "\n")
    print("    已自动生成随机密钥: " + ", ".join(generated))
else:
    print("    SECRET_KEY / JWT_SECRET_KEY / SWITCH_SECRET_KEY 已配置，跳过")
PYEOF
# ⚠️ 不能用 `set -a; . .env`：.env 不是 shell 脚本。值里含 $ / 反引号 / 空格时，
# source 会真的去执行它们 —— 实测踩到：随机生成的 MySQL 密码含 '$'（9ai$aoGx…），
# source 时被当作变量展开，set -u 下报 "aoGxEm3Y: unbound variable" 直接中断安装。
# 改用 python-dotenv 解析 + shlex.quote 转义后再 eval（与 scripts/dev-start.sh 同一做法）。
load_env_file() {
  local env_path="$1" exports
  [ -f "$env_path" ] || return 0
  exports="$("$VENV_PY" -c '
import shlex, sys
from dotenv import dotenv_values
for k, v in dotenv_values(sys.argv[1]).items():
    if v is not None and k:
        print("export %s=%s" % (k, shlex.quote(v)))
' "$env_path" 2>/dev/null)" || exports=""
  [ -n "$exports" ] && eval "$exports"
  return 0
}
load_env_file "$PROJECT_ROOT/.env"

# ── 5. 数据库初始化 ────────────────────────────────────────
if [ "$SKIP_DB" -eq 1 ]; then
  log "=== [5/7] 跳过数据库初始化 (--skip-db) ==="
else
  log "=== [5/7] 数据库初始化 ==="
  DB_HOST="${MYSQL_HOST:-localhost}"
  DB_PORT="${MYSQL_PORT:-3306}"
  DB_USER="${MYSQL_USER:-root}"
  DB_NAME="${MYSQL_DATABASE:-ip_manager}"
  export MYSQL_PWD="${MYSQL_PASSWORD:-}"

  log "预检 MySQL 连通性 ($DB_HOST:$DB_PORT)..."
  "$VENV_PY" - << PYEOF || die "MySQL 连接失败，请检查 .env 中 MYSQL_* 配置"
import pymysql, os
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                       init_command="SET time_zone='+00:00'",
                    password=os.getenv("MYSQL_PASSWORD",""), charset="utf8mb4")
c.close()
print("    MySQL 连接 OK")
PYEOF

  log "创建数据库 ${DB_NAME}（若不存在）..."
  "$VENV_PY" - << PYEOF
import pymysql, os
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                       init_command="SET time_zone='+00:00'",
                    password=os.getenv("MYSQL_PASSWORD",""), charset="utf8mb4", autocommit=True)
cur = c.cursor()
cur.execute("CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
c.close()
print("    数据库 $DB_NAME 就绪")
PYEOF

  # 全新安装的权威 DDL 源是迁移基线（0000_baseline.sql，生产库真实导出，
  # 含分区表与 15 个触发器）。快照已包含 0000_baseline.covers 清单中
  # 各迁移的效果，导入后按清单 stamp 版本即可与升级过的库保持一致。
  SCHEMA_FILE="$PROJECT_ROOT/migrations/versions/0000_baseline.sql"
  COVERS_FILE="$PROJECT_ROOT/migrations/versions/0000_baseline.covers"
  if [ -f "$SCHEMA_FILE" ]; then
    log "导入 $(basename "$SCHEMA_FILE")..."
    if [ -n "$MYSQL_CLIENT" ]; then
      # mysql CLI 原生支持 DELIMITER 指令
      # --init-command：固定会话时区为 UTC，使导入期间的 NOW()/CURRENT_TIMESTAMP
      # 与应用运行时的 UTC 口径一致（见 extensions.py 连接事件）
      "$MYSQL_CLIENT" --init-command="SET time_zone='+00:00'" -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB_NAME" < "$SCHEMA_FILE"
    else
      # 无 mysql 客户端时走 PyMySQL；触发器体含分号，必须用 DELIMITER 感知的切分器
      "$VENV_PY" "$PROJECT_ROOT/scripts/import_sql.py" "$SCHEMA_FILE"
    fi
    log "schema 导入完成"

    # 版本登记：按 covers 清单把"已体现进基线快照"的迁移版本 stamp 进
    # schema_migrations。之后 `flask db-upgrade` 只 apply 清单之外的增量
    # 迁移，新库逐版本升级到与生产库一致。
    # 纪律：重导 baseline 时必须同步更新 covers 清单（覆盖到链头就列到链头）。
    if [ -f "$COVERS_FILE" ]; then
      COVERED="$(grep -Ev '^[[:space:]]*(#|$)' "$COVERS_FILE" | tr -d ' \r' | paste -sd, -)"
    else
      warn "未找到 covers 清单，回退只 stamp 0000"
      COVERED="0000"
    fi
    "$VENV_PY" - << PYEOF || die "schema_migrations 版本登记失败"
import pymysql, os
covered = "${COVERED}".split(",")
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                       init_command="SET time_zone='+00:00'",
                    database="$DB_NAME", password=os.getenv("MYSQL_PASSWORD",""),
                    charset="utf8mb4", autocommit=True)
cur = c.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(16) NOT NULL PRIMARY KEY,
    description VARCHAR(255) NOT NULL DEFAULT '',
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
for v in covered:
    cur.execute(
        "INSERT IGNORE INTO schema_migrations (version, description)"
        " VALUES (%s, 'baseline')", (v,))
c.close()
print("    版本登记完成: baseline covers =", ",".join(covered))
PYEOF
  else
    warn "未找到任何 schema 文件，跳过（假设数据库已建表）"
  fi
fi

# ── 6. 种子数据 ────────────────────────────────────────────
ADMIN_PWD=""          # 非空 = 本次新建管理员时生成的随机密码，收尾要显示并留档
if [ "$SKIP_SEED" -eq 1 ]; then
  log "=== [6/7] 跳过种子导入 (--skip-seed) ==="
else
  log "=== [6/7] 导入种子数据 ==="
  # 为什么要 tee：seed_users.py 在创建管理员时会随机生成密码并只输出一次。
  # 那行输出若不落盘，密码就再也找不回来（实测踩到：只在当时的终端滚过一次）。
  # 这里同时写临时文件用于捕获，安装收尾再统一显示并写入 .credentials。
  SEED_LOG="$(mktemp)"
  bash "$PROJECT_ROOT/migrations/seed_all.sh" 2>&1 | tee "$SEED_LOG"
  ADMIN_PWD="$(grep -oE "初始密码: .*" "$SEED_LOG" | tail -1 | sed 's/^初始密码: //' || true)"
  if [ -n "$ADMIN_PWD" ]; then
    {
      printf '\n[%s] install.sh 自动创建管理员\n' "$(date '+%Y-%m-%d %H:%M:%S')"
      printf '  username = %s\n' "${SEED_ADMIN_USERNAME:-admin}"
      printf '  password = %s\n' "$ADMIN_PWD"
    } >> "$PROJECT_ROOT/.credentials"
    chmod 600 "$PROJECT_ROOT/.credentials" 2>/dev/null || true
  fi
  rm -f "$SEED_LOG"
fi

# ── 7. 监控维护 cron ────────────────────────────────────────
log "=== [7/7] 配置监控维护 cron ==="
# 为什么必须有（生产教训 2026-09-07）：device_monitor_probe_events 与
# device_metric_timeseries 两张表按日分区，且都带 p_future(MAXVALUE) 兜底分区。
# 无人每天预建分区时，新数据全部落进 p_future（实测 30 天积压 12.6 万行），
# 按天 DROP PARTITION 的清理与分区裁剪随之全部失效 —— 表会无限膨胀。
# 预建必须走 REORGANIZE（有 MAXVALUE 兜底时 ADD PARTITION 会报 1481），
# CLI 已实现，但**必须有人调度**才会执行，故此处落地为默认 cron。
CRON_TAG="ipip-monitor-maintenance"
mkdir -p "$PROJECT_ROOT/logs" || warn "无法创建 logs 目录（不影响安装主体，但 cron 日志会写失败）"
if command -v crontab >/dev/null 2>&1; then
  # 幂等：先剔除旧的同类条目（按行尾标记识别），再整体重建，重跑 install.sh 不会重复叠加
  EXISTING="$(crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true)"
  {
    [ -n "$EXISTING" ] && printf '%s\n' "$EXISTING"
    printf '# %s（由 scripts/install.sh 写入，重跑本脚本会整体重建，勿手工编辑）\n' "$CRON_TAG"
    printf '0 2 * * * cd %s && ./.venv/bin/flask --app wsgi:app monitor-manage-partitions >> %s/logs/monitor-partitions.log 2>&1 # %s\n' \
      "$PROJECT_ROOT" "$PROJECT_ROOT" "$CRON_TAG"
    printf '0 3 * * * cd %s && ./.venv/bin/flask --app wsgi:app monitor-archive >> %s/logs/monitor-archive.log 2>&1 # %s\n' \
      "$PROJECT_ROOT" "$PROJECT_ROOT" "$CRON_TAG"
  } | crontab -
  log "cron 已写入：02:00 预建分区 / 03:00 归档清理（日志 logs/monitor-*.log）"
else
  warn "未找到 crontab，跳过监控维护 cron。请自行添加两条定时任务："
  warn "  0 2 * * * cd $PROJECT_ROOT && ./.venv/bin/flask --app wsgi:app monitor-manage-partitions"
  warn "  0 3 * * * cd $PROJECT_ROOT && ./.venv/bin/flask --app wsgi:app monitor-archive"
fi

# ── 8. RAG 本地模型 ─────────────────────────────────────────
# 为什么必须预置：app/services/ai/rag/{embedding,reranker}.py 都强制
# HF_HUB_OFFLINE=1（避免 transformers 5.x 在无网环境加载时卡死），模型不在本地
# 就会加载失败——embedding 失败则 RAG 检索整体不可用，reranker 失败则降级为 RRF。
# 国内机房访问 huggingface.co 基本不可达，脚本默认走 ModelScope（实测约 5.7MB/s）。
# 模型缓存位置（对 --skip-models 同样生效：运行期读取的就是这个目录）：
export HF_HOME="${HF_HOME:-$PROJECT_ROOT/instance/huggingface}"
log "HF 模型缓存: $HF_HOME"
# ⚠️ 同步运行时环境文件：服务进程的 HF_HOME 来自 /etc/ipip/ipip.env
# （EnvironmentFile）。该文件由 install-units.sh 首次渲染、之后「已存在不覆盖」，
# 换目录重装时必残留旧路径 → 服务读不到模型、RAG 静默失效（实测踩到：
# /root 迁往 /opt 后仍指旧路径）。这里只校正这一行，不碰运维其它自定义值。
ENV_FILE="${ENV_FILE:-/etc/ipip/ipip.env}"
if [ -f "$ENV_FILE" ]; then
  if grep -q "^HF_HOME=" "$ENV_FILE"; then
    OLD_HF="$(grep "^HF_HOME=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
    if [ "$OLD_HF" != "$HF_HOME" ]; then
      sed -i "s|^HF_HOME=.*|HF_HOME=$HF_HOME|" "$ENV_FILE" \
        && log "已校正 $ENV_FILE 的 HF_HOME: $OLD_HF → $HF_HOME"
    fi
  else
    echo "HF_HOME=$HF_HOME" >> "$ENV_FILE" \
      && log "已追加 $ENV_FILE 的 HF_HOME=$HF_HOME"
  fi
fi
if [ "$SKIP_MODELS" -eq 1 ]; then
  warn "已跳过本地模型下载（--skip-models）：RAG 向量检索将不可用，"
  warn "  需要时执行：$VENV_PY scripts/download_models.py"
else
  log "=== [8] 下载 RAG 本地模型（embedding≈92MB + reranker≈1100MB）==="
  # 默认写入 HF 标准缓存（$HF_HOME/hub/models--BAAI--*/snapshots/main/），
  # 与本地开发环境同一套解析机制 → 代码与 .env 均无需改动。
  # 下载体积较大但属必需步骤；失败只告警不中止安装，但会把影响范围说清楚。
  run_timed "下载 RAG 本地模型" "$VENV_PY" "$PROJECT_ROOT/scripts/download_models.py" \
    || warn "模型下载失败 → RAG 功能不可用。可稍后单独重跑（支持断点续传）：
      $VENV_PY scripts/download_models.py                    # 全部（写入 HF 缓存）
      $VENV_PY scripts/download_models.py --only embedding    # 只下必需的 92MB"
fi

# ── 9. 【可选】systemd 进程托管（T2.1）──────────────────────
# 与 install-units.sh 的分工：本脚本装「应用」，它装「进程托管」。
# 刻意默认关闭：接管进程属生产变更且需要 root，不应由安装脚本默默代做。
UNITS_INSTALLED=0
if [ "$WITH_UNITS" -eq 1 ]; then
  log "=== [可选] 安装 systemd 进程托管 unit ==="
  # 默认按仓库布局探测：deploy/ 与 ipip-deploy/ 是兄弟目录，该相对位置在源码仓
  # （ipip/ipip-deploy + ipip/deploy）与部署机（/root/ipip-deploy + /root/deploy）
  # 下都成立，因此无需额外配置。
  UNITS_SCRIPT="${UNITS_SCRIPT:-$SCRIPT_DIR/../../deploy/systemd/install-units.sh}"
  if [ ! -f "$UNITS_SCRIPT" ]; then
    warn "未找到 unit 安装脚本: $UNITS_SCRIPT"
    warn "  用 --units-script <路径> 指定，或按 deploy/systemd/README.md 手工安装。"
  else
    units_args=(--project-root "$PROJECT_ROOT")
    [ -n "$UNITS_USER" ]  && units_args+=(--user "$UNITS_USER")
    [ -n "$UNITS_GROUP" ] && units_args+=(--group "$UNITS_GROUP")
    if bash "$UNITS_SCRIPT" "${units_args[@]}"; then
      UNITS_INSTALLED=1
      log "unit 安装完成（脚本不会自动启用服务，请按上面的提示逐个 enable）"
    else
      # 应用本体已就绪，托管失败不应把整次安装判为失败
      warn "systemd unit 安装失败 —— 应用已可用，可稍后手工重试："
      warn "  sudo bash $UNITS_SCRIPT ${units_args[*]}"
    fi
  fi
else
  log "=== [可选] 跳过 systemd 进程托管（加 --with-units 启用）==="
fi

# ── 10. 凭据汇总 ───────────────────────────────────────────
# 部署最怕「装完了却不知道账号密码」：admin 是随机密码，MySQL/Redis 密码散落在
# .env 里，事后翻文件既慢又容易看错环境（本机 .env 与服务器 .env 长得一样）。
# 此处统一展示一次，并指向留档文件与重置入口。
log "=== 凭据汇总（请立即保存）==="
if [ -n "$ADMIN_PWD" ]; then
  log "本次新建管理员 '${SEED_ADMIN_USERNAME:-admin}' 的密码: $ADMIN_PWD"
fi
if [ -f "$PROJECT_ROOT/scripts/credentials.py" ]; then
  "$VENV_PY" "$PROJECT_ROOT/scripts/credentials.py" show \
    || warn "凭据清单展示失败，可稍后手工执行：$VENV_PY scripts/credentials.py show"
else
  warn "未找到 scripts/credentials.py，跳过凭据清单展示"
fi
log "重置入口: $VENV_PY scripts/credentials.py reset-admin   # 重置管理员密码"
log "          sudo $VENV_PY scripts/credentials.py reset-mysql  # 重置 MySQL 密码（并同步 .env）"
log "留档文件: $PROJECT_ROOT/.credentials（权限 600，含历次生成的明文凭据）"

log "============================================================"
log "安装完成 ✅"
if [ "$UNITS_INSTALLED" -eq 1 ]; then
  log "下一步:"
  log "  1) 按 install-units.sh 输出的清单逐个 enable 并验证"
  log "  2) systemctl enable ipip.target        # 开机自启聚合"
  log "  3) curl -fsS http://127.0.0.1:${FLASK_PORT:-5000}/api/health/check"
else
  log "下一步: 编辑 .env 确认配置后，执行 bash scripts/start.sh 启动系统"
  log "  需要 systemd 托管进程时：重跑本脚本并加 --with-units"
fi
log "============================================================"
