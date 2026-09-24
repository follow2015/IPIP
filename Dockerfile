# ═══════════════════════════════════════════════════════════════════════════
# IPIP 单镜像（多角色）—— 评估/开发环境专用，不替换生产 systemd
#
# 改动前必读（每条都有代码依据，不是风格偏好）：
#  1. 一份 Dockerfile 产出一个镜像，所有角色共用；差异只在 entrypoint 的角色参数。
#  2. 三段构建：frontend-builder → python-builder → runtime（构建工具不进最终镜像）。
#  3. runtime 必须含 frontend-new/dist：app/__init__.py 的 static_folder 指向
#     ../frontend-new/dist，Flask 自己伺服静态文件，项目没有独立前端服务器。
#  4. WORKDIR / 拷贝目标固定在 /app：config.py:_assert_deploy_location() 会拒绝在
#     /root 下启动（RuntimeError）。不要改成 /root/app。
#  5. TZ=UTC：extensions.py 的连接事件把 MySQL 会话时区固定为 +00:00，容器同走 UTC，
#     否则容器日志时间与库内时间会差 8 小时。
#  6. 不装 requirements-laya.txt —— 该文件不存在（曾出现在设计文档论述中，已核实为误述）。
#     将来若新增可选重依赖，在此镜像基础上另加一层，不要塞进基础镜像。
#  7. Python 依赖装在 **/opt/venv**，不是 `pip install --prefix=/install`：`--prefix` 装的包
#     对**下一条 pip 不可见**，会让 `-r requirements.txt` 重装 CUDA 版 torch 覆盖 CPU 版
#     （逐条依据见段 2 注释）。这不是风格偏好，改回 prefix 就等于白装。
#  8. **RAG 模型必须内置**：embedding.py / reranker.py 都强制 HF_HUB_OFFLINE=1，模型不在
#     本地就是加载失败（不是"降级"）⇒ runtime 段在业务代码**之前**单独一层预置两个模型
#     （≈91MB + ≈1060MB，落进 $HF_HOME = /app/instance/huggingface）。
#     三条硬约束见段 3 的模型层注释（必须 --no-official、不能挂 cache mount、别覆盖 OFFLINE）。
#  9. /app/docs 必须**存在**（可为空）：AI_DOCS_ROOT 默认指向它，而 docs_dir_validation
#     会做 isdir 检查 —— 目录不在时连入库根目录 "." 都被拒。但**不内置语料**：部署仓
#     docs/ 是运维手册（含内网信息），不进制品（§5.1）。
# ═══════════════════════════════════════════════════════════════════════════

# ── 段 1：前端构建 ───────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable

WORKDIR /build
# 先只拷 manifest，把依赖层缓存吃满（改业务代码不必重装依赖）
COPY frontend-new/package.json frontend-new/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/pnpm/store pnpm install --frozen-lockfile

COPY frontend-new/ ./
# "build": "tsc -b && vite build" → 产出 /build/dist
RUN pnpm build


# ── 段 2：Python 依赖（gcc 等构建工具只留在这层）──────────────────────────
FROM python:3.14-slim AS python-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# bcrypt / cryptography / psutil / pandas 等在缺 wheel 的平台需要本地编译
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# ⚠️ 必须用 **venv** 隔离，不能写 `pip install --prefix=/install`（2026-09-24 实测 + pip 源码核对）：
#   `--prefix` 装的包，**下一条同前缀的 pip 看不见** —— 解析器与 check_if_exists 只看
#   `get_default_environment()`（= `sys.path`）；`prefix_path` 在 pip 包里**只被
#   `_internal/commands/install.py` 引用**，且仅用于"装后汇总"。
#   ⇒ 写成 prefix 时，下面的 `-r requirements.txt` 会**重新从 PyPI 解析 torch**
#     （CUDA 构建 + nvidia-* 数 GB）并**覆盖**刚装好的 CPU 版 —— 省体积的目的完全落空，
#     而且**构建照样成功、不报错**。
#   对照实验（离线可复现）：同前缀先装 A、再装依赖 A 的 B ⇒ `--dry-run --report` 仍列 **A+B**；
#     在 venv 里同样两步 ⇒ report **只列 B**。（与 scripts/install.sh 的 `$VENV_PY -m pip` 同纪律）
# ⚠️ torch 必须先从 CPU 专用源单独装：PyPI 上 linux 的默认 torch wheel 是 CUDA 构建
#   （连带 nvidia-cudnn 等数 GB 依赖），评估镜像用不上、体积翻数倍。
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt ./
# sentence-transformers 会声明 torch 依赖，而 venv 里已有 CPU 版 ⇒ pip 判定"已满足"、
# 不会重复拉 CUDA 版。**这正是必须用 venv 而不是 --prefix 的原因。**
RUN pip install -r requirements.txt


# ── 段 3：运行时 ─────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC \
    # HF_HOME 必须与 install.sh:872 的口径一致（生产是 $PROJECT_ROOT/instance/huggingface，
    # 且会写进 /etc/ipip/ipip.env 供服务进程读）⇒ 容器内对应 /app/instance/huggingface，
    # 模型层就落在这里。**不要**让它落到默认的 ~/.cache/huggingface（= /root/.cache/...）。
    HF_HOME=/app/instance/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# curl 供 compose 里的 healthcheck 使用；tzdata 供 TZ=UTC 生效
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo "$TZ" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# venv 整目录拷进 runtime：两段 base 相同 ⇒ venv 的 home（/usr/local）在 runtime 同样存在，
# 符号链接可用；gcc/编译期头文件留在 python-builder，不进最终镜像。
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=frontend-builder /build/dist /app/frontend-new/dist

# 让 runtime 的 `python` / `pip` / `flask` 都解析到 venv（entrypoint 与 compose 的
# healthcheck 调的都是裸命令名，依赖这一行）
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app

# ── 模型层（RAG 离线依赖，必须内置）──────────────────────────────────────────
# 只 COPY 这一个脚本：模型层 ≈1.15GB，而业务代码天天变 ⇒ 必须让业务改动**不击穿**
# 这一层缓存，否则每次 CI 都重下 1GB+。
COPY scripts/download_models.py ./scripts/
# ⚠️ 三条约束，每条都有依据。写成别的形式要么体积翻倍、要么**镜像里根本没有模型**：
#  ① 必须带 --no-official。脚本的"官方优先"路径是裸 `snapshot_download(repo_id=...)`
#     —— **不带 ignore_patterns** ⇒ 会把 onnx/ 与 pytorch_model.bin 一并下
#     （bge-reranker-base 这三个副本各 ≈1GB）⇒ 模型层 3GB+ 而不是 1.15GB。
#     --no-official 走镜像 API 路径，那里的 filter_weight_files() 才是生效的。
#  ② **不能**写成 `RUN --mount=type=cache,target=/app/instance/huggingface ...`：
#     BuildKit 的 cache mount 内容**不写进镜像层** ⇒ 构建"成功"、容器里却没有模型。
#     （这是最容易顺手写错的地方：上面 pip 那行用 cache 是对的，这行用 cache 就等于白下。）
#  ③ 不要为它覆盖 HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE。镜像下载路径走
#     urllib/requests，不受这两个变量影响；覆盖成 0 反而让"官方优先"路径有机会生效，
#     于是命中 ① 那个坑（多了 2GB，且不报错）。
# 失败会让构建直接红（脚本 sys.exit 非 0），这是有意的 fail-fast：模型缺失不该悄悄过。
RUN python scripts/download_models.py --no-official

# ── 业务代码（改动只击穿这一层）───────────────────────────────────────────
# 与 deploy/systemd/*.service 的 WorkingDirectory=${PROJECT_ROOT} 对齐
COPY config.py extensions.py wsgi.py run.py ./
COPY run_monitor_service.py run_trapd_service.py ./
COPY app/ ./app/
COPY realtime_gateway/ ./realtime_gateway/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/

COPY deploy/docker/entrypoint.sh /usr/local/bin/ipip-entrypoint.sh

# instance/ 与 logs/ 被 .dockerignore 排除，这里显式建出来（app 与 install.sh 都假设它们存在）。
# /app/docs 是 AI_DOCS_ROOT 的默认值（config.py:195 按 config.py 所在目录拼 "docs"），
# 而入库校验会对目标做 isdir 检查 ⇒ 目录不存在时**连入库根目录 "." 都被拒**，RAG 等于废掉。
# 所以目录必须有；但**不放语料**（部署仓 docs/ 是运维手册，含内网信息，不进制品）。
RUN chmod +x /usr/local/bin/ipip-entrypoint.sh \
    && mkdir -p /app/instance /app/logs /app/docs \
    && printf 'AI_DOCS_ROOT 指向本目录：RAG 语料请挂载到这里。\n镜像内不内置语料（部署仓 docs/ 是运维手册，含内网信息，不进制品）。\n在 compose 里给 web/monitor/celery 加：  volumes: ["./你的语料:/app/docs:ro"]\n' \
         > /app/docs/README.md

# 角色内部端口：web=5000 / gateway=8000（宿主侧映射交给 compose）
EXPOSE 5000 8000

# ⚠️ 这里刻意**不写 HEALTHCHECK**：本镜像是多角色的，celery/monitor 角色不监听 HTTP，
#    统一的 HTTP 健康检查会把它们永久标成 unhealthy。健康检查放到 compose 里按服务声明。
ENTRYPOINT ["/usr/local/bin/ipip-entrypoint.sh"]
CMD ["web"]
