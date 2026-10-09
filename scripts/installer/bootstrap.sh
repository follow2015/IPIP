#!/usr/bin/env bash
# ============================================================
# bootstrap.sh - ipip 安装器引导（前置守卫 + Python 3.14 获取 + exec 编排器）
# ------------------------------------------------------------
# 旧 scripts/install.sh（3189 行全功能脚本）已于 2026-10-04 删除（原样归档在
# 本机 docs/ops/archive/install.sh，仅供参考、不入库、不可执行），安装改为
# 两层，本脚本是**第一层**（分层设计见 docs/ops/2026-10-03-安装器分层边界.md §4）：
#
#   bash scripts/installer/bootstrap.sh [安装器参数...]
#        └─ ① 系统支持性判定（零 Python 依赖 —— CentOS 7 只有 2.7.5，
#              任何含 f-string 的 Python 都会在解析期崩，用户看到的会是一段
#              traceback 而不是"系统不受支持"）
#           ② /tmp noexec 拦截（noexec 下 pip 构建必炸，报错指向
#              chroma-hnswlib/numpy，与真因相距极远）
#           ③ 把 Python 3.14 弄出来（deadsnakes PPA / uv / 源码编译）
#           ④ sqlite3 版本检查（独立判据，见下方"教训"）
#           ⑤ exec python3.14 -m installer "$@"   ← 第二层，真正干活
#
# 为什么要两层：第二层（installer）全部 .py 用 3.14 语法，要求"先有一个
# 能跑的 3.14 才能知道这机器不该装"是本末倒置；而第①②④是纯判据，
# shell 就能做，还必须在动任何东西之前完成。
#
# 用法（参数与旧 install.sh 完全兼容，原样透传给编排器）：
#   bash scripts/installer/bootstrap.sh                    # 完整安装
#   bash scripts/installer/bootstrap.sh --skip-models      # 跳过 RAG 模型
#   bash scripts/installer/bootstrap.sh --with-units ...   # systemd 托管
#   bash scripts/installer/bootstrap.sh --selftest         # 只跑判据自检
# ============================================================
set -u   # 刻意不用 set -e：每一步显式处理错误并给出指路，而不是静默中断

# ── 路径定位 ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHON_MIN="3.14"
PY_BIN=""

log() { echo "[ipip-bootstrap] $*"; }
warn() { echo "[WARN] $*" >&2; }
die() {
  echo "" >&2
  echo "======================================================================" >&2
  echo "ipip 安装中止" >&2
  echo "======================================================================" >&2
  echo "$1" >&2
  exit 1
}

# ── 前置：系统支持性判定（**零 Python 依赖**）────────────────────
# 为什么放在最前面、且必须是 shell：
#   判据只是"读 /etc/os-release 比版本号" —— shell 一行就够。若写成 Python，
#   就要求"先有一个能跑的 Python 才能知道这机器不该装"，本末倒置。
#   CentOS 7 自带 2.7.5，任何含 f-string 的 Python 调用都会在**解析期**崩，
#   用户看到的是一段 pkgutil.py 内部 traceback，完全不知道自己撞上的是
#   "系统不受支持"。
#
# 数据源：scripts/installer/supported-systems.conf（与 Python 侧同一份）。
#   `while IFS='|' read` 是 bash 4.2（CentOS 7）就有的看家活，不需要 jq。
#
# 放在最前：系统不受支持就**不该动用户任何东西**，连 mkdir /opt/ipip 都不做。
# 取发行版 ID（小写）。只读 os-release 的单个字段，不 source 整个文件
# （source 会执行发行版塞进来的任意命令）。供 check_system_support /
# openssl 预检 / check_sqlite_version 共用。
_distro_id() {
  [ -r /etc/os-release ] || { echo ""; return 0; }
  sed -n 's/^ID=["'"'"']\?\([^"'"'"']*\)["'"'"']\?$/\1/p' /etc/os-release \
    | head -n1 | tr 'A-Z' 'a-z'
}

check_system_support() {
  local conf="$SOURCE_ROOT/scripts/installer/supported-systems.conf"
  if [ ! -r "$conf" ]; then
    warn "找不到支持矩阵 ${conf}，跳过系统检查（将由编排器自行判定）"
    return 0
  fi

  local id="" ver="" like=""
  if [ -r /etc/os-release ]; then
    # 只取需要的三个字段，不 source 整个文件 —— 那会执行发行版塞进来的任意命令
    id="$(_distro_id)"
    ver="$(sed -n 's/^VERSION_ID=["'"'"']\?\([^"'"'"']*\)["'"'"']\?$/\1/p' /etc/os-release | head -n1)"
    like="$(sed -n 's/^ID_LIKE=["'"'"']\?\([^"'"'"']*\)["'"'"']\?$/\1/p' /etc/os-release | head -n1)"
  fi
  # 供后续模块（openssl 预检的风险提示 / sqlite 分级建议）复用，作为全局变量传出
  DISTRO_ID="$id"
  DISTRO_VER="$ver"

  # 版本前缀匹配："等于前缀 或 前缀+点" ⇒ "20.04.6" 也能命中 "20.04"
  local level="" reason="" advice="" matched=0
  while IFS='|' read -r c_distro c_prefix c_level c_reason c_advice; do
    case "$c_distro" in ''|\#*) continue ;; esac
    # 去掉首尾空白（配置里为了可读性会留空格）
    c_distro="$(echo "$c_distro" | tr -d '[:space:]')"
    c_prefix="$(echo "$c_prefix" | tr -d '[:space:]')"
    [ "$c_distro" = "$id" ] || continue
    if [ -z "$c_prefix" ] || [ "$ver" = "$c_prefix" ] \
       || [ "${ver#"$c_prefix".}" != "$ver" ]; then
      level="$c_level"; reason="$c_reason"; advice="$c_advice"; matched=1
      case "$c_level" in
        rejected) break ;;   # 拒绝项必须先命中：保守优先
      esac
    fi
  done < "$conf"

  case "$level" in
    rejected) ;;
    *) level="" ;;   # supported / manual / 未匹配 —— 都交给后续流程
  esac

  # 非 systemd 环境：与发行版无关的硬约束（ADR-003 依赖 systemd 托管进程）。
  # 判据是 /run/systemd/system 这个**运行时目录**（PID 1 是 systemd 才会有）。
  # 只查 `command -v systemctl` 会误判：容器里常装了 systemd 软件包却没在跑。
  # ⚠️ 顺序与 judge/support.py 一致：**systemd 检查先于**发行版表。
  #    否则 ubuntu 24.04 的容器会因为命中 supported 被放行。
  if [ -z "$level" ] && [ ! -d /run/systemd/system ]; then
    level="rejected"
    reason="未检测到 systemd。本项目依赖 systemd 托管进程（ADR-003）。"
    advice="在完整的 systemd 系统上部署（Debian/Ubuntu/Rocky 等）
容器部署请用镜像方案，不要在容器内跑本安装器"
  fi

  [ "$level" = "rejected" ] || return 0

  echo ""
  echo "======================================================================"
  echo "ipip 安装器 · 前置环境检查"
  echo "======================================================================"
  printf '  发行版    : %s %s\n' "${id:-未知}" "${ver:-未知}"
  printf '  架构      : %s\n' "$(uname -m)"
  if [ -d /run/systemd/system ]; then
    printf '  systemd   : 有\n'
  else
    printf '  systemd   : 无\n'
  fi
  echo ""
  echo "  [不支持] 这个系统不在支持范围内。"
  echo ""
  echo "  原因：$reason"
  echo ""
  echo "  怎么办："
  # advice 里的 \n 是**字面量两字符**（见 conf 头注释），此处还原成换行
  printf '%b\n' "$advice" | while IFS= read -r _line; do
    [ -n "$_line" ] && echo "    · $_line"
  done
  echo ""
  # ⚠️ 这里**不再推荐 el9**（2026-10-03 更正）：el9 能装完，但它的 sqlite
  #    锁在 3.34.1（< chromadb 要求的 3.35.0），AI 功能只能降级运行。
  #    同为 RHEL 系、迁移成本相当的答案是 el10（实测 sqlite 3.46.1 ✓）。
  echo "  推荐系统：Ubuntu 24.04 LTS、Debian 12、Rocky Linux 10 / AlmaLinux 10"
  echo "======================================================================"
  exit 1
}

# ── /tmp noexec 拦截 ────────────────────────────────────────
# 容器（以及部分加固过的生产机）把 /tmp 挂成 noexec：
#     tmpfs on /tmp type tmpfs (rw,nosuid,nodev,noexec,relatime,...)
# pip 的构建隔离环境建在 /tmp，其中 numpy 的 .so 要按可执行段 mmap；
# noexec 让 mmap 失败，报出来是 chroma-hnswlib / numpy 的构建错误 ——
# 与真正的原因相距极远。必须前置拦截并给出解法。
check_tmp_exec() {
  local probe
  probe="$(mktemp 2>/dev/null)" || {
    warn "/tmp 不可写（mktemp 失败）。pip 构建隔离环境需要 /tmp，请修好后重跑。"
    return 1
  }
  # 用 printf 写一个最小可执行体；不用 heredoc 是为了更好控错
  printf '#!/bin/sh\nexit 0\n' > "$probe" 2>/dev/null || true
  chmod +x "$probe" 2>/dev/null || true
  if "$probe" >/dev/null 2>&1; then
    rm -f "$probe"
    return 0
  fi
  rm -f "$probe"

  echo ""
  echo "======================================================================"
  echo "ipip 安装器 · 前置环境检查"
  echo "======================================================================"
  echo "  [不支持] /tmp 挂载在 noexec 下，无法执行文件。"
  echo ""
  echo "  为什么这会失败：pip 的构建隔离环境建在 /tmp，其中 numpy 的共享库"
  echo "  要按可执行段映射。noexec 令 mmap 失败，报错会指向 chroma-hnswlib /"
  echo "  numpy 的构建错误 —— 与真正的原因相距极远。"
  echo ""
  echo "  当前挂载："
  mount 2>/dev/null | grep -E ' /tmp ' | sed 's/^/    /' || echo "    (未找到 /tmp 挂载项)"
  echo ""
  echo "  怎么办（任选其一）："
  echo "    · 重新挂载：mount -o remount,exec /tmp"
  echo "    · 或用可执行的目录当临时区：TMPDIR=/var/tmp bash scripts/installer/bootstrap.sh ..."
  echo "      （TMPDIR 会被 pip 继承，构建环境随之落到 /var/tmp）"
  echo "======================================================================"
  return 1
}

# ── Python 3.14 获取 ────────────────────────────────────────
ver_ge() {
  awk -v cur="$1" -v min="$2" '
    BEGIN{ n=split(cur,a,"."); m=split(min,b,".")
           for(i=1;i<=m;i++){ if(a[i]+0>b[i]+0) exit 0; if(a[i]+0<b[i]+0) exit 1 }
           exit 0 }'
}

# Python：必须 >= 3.14，**不允许降级**
# 理由：realtime_gateway 使用 asyncio.AsyncGenerator，该属性在 Python 3.14 才存在；
# 低于它的机器装完就是必然崩。
detect_python() {
  local c v
  for c in python3.14 python3.13 python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      v="$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0.0)"
      if ver_ge "$v" "$PYTHON_MIN"; then PY_BIN="$c"; return 0; fi
    fi
  done
  return 1
}

# 自动补齐 Python 3.14 —— **纯 shell，零 Python 依赖**（鸡生蛋：此刻机器上
# 恰恰可能没有合格的 Python）。
#
# 路径选择不靠猜，靠 §supported-systems.conf 已判定的发行版：
#   · Ubuntu 24.04+ ：deadsnakes PPA 有现成 deb，1 分钟搞定，不编译
#   · 其它          ：优先 uv（python-build-standalone，自带高版本 sqlite），
#                     源码编译兜底
ensure_python314() {
  detect_python && return 0

  local id="" ver=""
  if [ -r /etc/os-release ]; then
    id="$(sed -n 's/^ID=["'"'"']\?\([^"'"'"']*\)["'"'"']\?$/\1/p' /etc/os-release | head -n1 | tr 'A-Z' 'a-z')"
    ver="$(sed -n 's/^VERSION_ID=["'"'"']\?\([^"'"'"']*\)["'"'"']\?$/\1/p' /etc/os-release | head -n1)"
  fi

  warn "未找到 Python >= ${PYTHON_MIN}（当前最高 $(python3 --version 2>/dev/null || echo 未知)），开始补齐"

  # ── 路径 1：Ubuntu 22.04+ 走 deadsnakes PPA（有现成 deb 就别编译）──
  if [ "$id" = "ubuntu" ]; then
    case "$ver" in
      22.04*|24.04*|26.04*)
        log "Ubuntu ${ver}：走 deadsnakes PPA（有 python3.14 现成包，约 1 分钟）"
        DEBIAN_FRONTEND=noninteractive apt-get install -y software-properties-common >/dev/null 2>&1 || true
        if add-apt-repository -y ppa:deadsnakes/ppa >/dev/null 2>&1 \
           && DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1 \
           && DEBIAN_FRONTEND=noninteractive apt-get install -y \
                python3.14 python3.14-venv python3.14-dev >/dev/null 2>&1; then
          # python3.14-venv 是**独立包**（内含 ensurepip）。Debian/Ubuntu 把它
          # 拆了出来，最小安装默认不带 —— 缺它会在创建 venv 时报
          # "ensurepip is not available"（Ubuntu 26.04 最小安装实测踩到）。
          hash -r 2>/dev/null || true
          detect_python && { log "Python 已补齐（$("$PY_BIN" --version 2>&1)）✓"; return 0; }
        fi
        warn "deadsnakes PPA 路径失败（网络受限或镜像未同步），改用 uv / 源码编译"
        ;;
    esac
  fi

  # ── 路径 2：uv（python-build-standalone，比源码编译快得多且自带
  #    高版本 sqlite —— el9 上它是首选而不只是加速器）──
  if command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1; then
    log "尝试 uv 获取 Python 3.14（比源码编译快，且自带 sqlite 3.53+）..."
    # ⚠️ 装不上 uv 的输出**不要丢弃**：这一步退化意味着多花 10~15 分钟
    #    源码编译，而运维完全不知道为什么。2026-10-04 Debian 12 实测：
    #    同一条命令第一次失败、隔几秒手动重跑立刻成功 —— 是瞬时网络抖动，
    #    但旧写法只留下一句「uv 路径不可用」，现场无法区分是网络、
    #    是 astral.sh 不可达、还是本机缺 unzip。
    _uv_install_log="${TMPDIR:-/tmp}/_ipip_uv_install.log"
    if curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | sh >"$_uv_install_log" 2>&1; then
      export PATH="$HOME/.local/bin:$PATH"
      # ⚠️ uv 默认把 Python 装到 **$HOME/.local/share/uv/** —— 本脚本以 root 执行时
      #    就是 /root/.local/share/uv，而 /root 是 0700（只有 root 能进）。
      #    后果不在安装期暴露，而在**服务启动期**：
      #      · .venv/bin/python3.14 软链指向 /root/.local/share/uv/.../python3.14
      #      · unit 默认以 ipip 运行 → exec 被内核拒 → status=203/EXEC
      #      · systemctl 只显示"反复重启"，curl 一律 HTTP 000
      #    实测 2026-10-04 Debian 12（无 deadsnakes，只能走 uv）踩到。
      #    根治办法就是装到全局可读目录 —— 不必为此放开 /root 的权限。
      export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/usr/local/lib/uv-python}"
      if command -v uv >/dev/null 2>&1 && uv python install 3.14 >/dev/null 2>&1; then
        local uvp
        uvp="$(uv python find 3.14 2>/dev/null || true)"
        if [ -n "$uvp" ] && [ -x "$uvp" ]; then
          # ⚠️ 必须软链到 /usr/local/bin 并以它交棒（2026-10-04 测试机实测）：
          # uv 会在 ~/.local/bin 建 python3.14 垫片，直接用它做 venv builder 时
          # venv 的 python 符号链指回 /root/.local —— systemd 单元 ProtectHome=true
          # 罩住 /root，服务 203/EXEC 全线起不来（conf:36 同款事故的第二跳板）。
          ln -sf "$uvp" /usr/local/bin/python3.14
          hash -r 2>/dev/null || true
          PY_BIN="/usr/local/bin/python3.14"
          log "Python 已补齐（uv：$("$PY_BIN" --version 2>&1)）✓"
          return 0
        fi
      fi
    fi
    if [ -s "$_uv_install_log" ]; then
      warn "  uv 安装器的原始输出（用于区分网络抖动 / 依赖缺失）："
      tail -n 5 "$_uv_install_log" 2>/dev/null | sed 's/^/      /'
    fi
    rm -f "$_uv_install_log" 2>/dev/null || true
    warn "uv 路径不可用，改用源码编译"
  fi

  # ── 路径 3：源码编译（跨发行版唯一可行的兜底手段）──
  handle_openssl_upgrade_risk
  compile_python314 || return 1
  detect_python && { log "Python 已补齐（$("$PY_BIN" --version 2>&1)）✓"; return 0; }
  return 1
}

# 源码编译 CPython 3.14。每个参数都对应一次实测，**不要随手改**。
compile_python314() {
  local ver="3.14.0" prefix="/usr/local"
  local src="/tmp/Python-${ver}"
  local mirrors="
https://mirrors.aliyun.com/python-release/source/Python-${ver}.tar.xz
https://mirrors.huaweicloud.com/python/${ver}/Python-${ver}.tar.xz
https://www.python.org/ftp/python/${ver}/Python-${ver}.tar.xz"

  log "源码编译 Python ${ver}（实测约 5-15 分钟，取决于核数与网络）"

  # 编译依赖。**这里必须装"编译依赖"而不是只装 gcc** ——
  # 缺 -dev 包不会报错，而是"编译成功但模块缺失"：
  #     Checked 114 modules (... 15 missing ...)
  # make 退出码是 0，但装出来的解释器 import ssl 就崩，等于白等 20 分钟。
  # [WARN] 发行版 ID 必须本函数自取（评审 P2）：曾依赖 ensure_python314 的
  # local id（动态作用域隐式契约），被 source 后单独调用即 set -u 未绑定崩。
  case "$(_distro_id)" in
    ubuntu|debian)
      DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1 || true
      DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential libssl-dev libffi-dev zlib1g-dev libbz2-dev \
        liblzma-dev libsqlite3-dev libreadline-dev libncurses-dev \
        uuid-dev tk-dev libgdbm-dev libnss3-dev \
        wget xz-utils bzip2 gzip >/dev/null 2>&1 \
        || warn "部分编译依赖安装失败，继续尝试（可能少编某些模块）"
      ;;
    rocky|almalinux|centos|rhel)
      dnf install -y gcc gcc-c++ make openssl-devel libffi-devel zlib-devel \
        bzip2-devel readline-devel sqlite-devel xz-devel ncurses-devel \
        libuuid-devel tk-devel wget xz bzip2 gzip >/dev/null 2>&1 \
        || warn "部分编译依赖安装失败，继续尝试"
      # ⚠️ gdbm-devel 在 EL9 上**不存在**（dnf repoquery --whatprovides
      #    /usr/include/gdbm.h 返回空）。把它列进必装会让整条 dnf 命令
      #    `Error: Unable to find a match` —— 连 gcc 都装不上。
      dnf install -y gdbm-devel >/dev/null 2>&1 || true
      ;;
  esac

  # 解压工具是**可执行文件**包，与 -dev 开发库是**两个包**：
  # xz-devel 给头文件，xz 给 /usr/bin/xz。缺后者时 `tar -xf *.tar.xz` 报
  #     tar (child): xz: Cannot exec: No such file or directory
  # 且这个报错发生在 22MB 下载完之后。
  local t
  for t in xz gzip bzip2; do
    command -v "$t" >/dev/null 2>&1 || die "解压 $ver 需要 \`$t\`，但 PATH 里找不到。
  注意 -dev/-devel 包只提供编译用头文件，不提供 $t 可执行文件 —— 两者是不同的包。
  · Debian/Ubuntu : apt-get install -y $t
  · RHEL 系       : dnf install -y $t"
  done

  local base src_found=0
  for base in $mirrors; do
    [ -n "$base" ] || continue
    log "  下载 $base"
    if curl -fsSL --connect-timeout 15 -o "${src}.tar.xz" "$base" 2>/dev/null \
       && [ -s "${src}.tar.xz" ]; then
      src_found=1; break
    fi
  done
  [ "$src_found" -eq 1 ] || { warn "所有 Python 源码镜像均不可达"; return 1; }

  rm -rf "$src"
  tar -xf "${src}.tar.xz" -C /tmp || { warn "解压失败"; return 1; }
  cd "$src" || return 1

  # ⚠️ 必须 touch configure.ac / aclocal.m4 / configure。
  #    否则 make 会去重跑 autoconf，而新系统的 autoconf 2.72 与 CPython 的
  #    configure.ac 不兼容，报 "possibly undefined macro"。
  touch configure.ac aclocal.m4 configure

  # ⚠️ 三个参数缺一不可，每个都是实测换来的：
  #   · 不开 --with-lto    ：LTO 会在链接阶段串行重编 73 个 LTRANS 作业，
  #                          `make -jN` 完全失效，多花约 12 分钟。
  #   · 不开 --enable-shared：会只记录 soname 让动态链接器按 ldconfig 解析，
  #                          可能链到别人的 libpython3.14.so ⇒ `import ctypes`
  #                          段错误（10/10 稳定复现）。装到 /usr/local 更危险 ——
  #                          那里本就在 ld.so.conf 里，会把劫持源固化到官方路径。
  #   · PROFILE_TASK 排除 test_generators：PGO 跑测该用例固定失败
  #                          （插桩改变信号时序），会让 make 断在 profile-run-stamp
  #                          并留下跑不起来的插桩二进制。
  ./configure --prefix="$prefix" --enable-optimizations >/dev/null 2>&1 \
    || { warn "configure 失败"; return 1; }

  # 留一个核：编译占满全部核心会拖死心跳线程、sshd、监控 agent，
  # 表现为"安装卡死"，而实际只是被打满了。上限 8：更高并发在受限
  # 云主机上因内存压力反而更慢。
  local n
  n="$(nproc 2>/dev/null || echo 2)"
  n=$((n - 1)); [ "$n" -lt 1 ] && n=1; [ "$n" -gt 8 ] && n=8

  if ! PROFILE_TASK="-m test --pgo --timeout=1200 -x test_generators" \
       make -j"$n" >/dev/null 2>&1; then
    # 主路径已排除已知时序敏感用例，仍失败 ⇒ 清掉半成品，去掉
    # --enable-optimizations 重编。**这一步不是防御性编程** —— 它保证
    # 哪怕遇到新情况也不会因此装不上 Python。
    # 清理必须彻底：不清 .o/.gcda 会让新 configure 复用插桩状态的目标文件，
    # **仍然链出插桩二进制**，重编等于白编（"看起来降级了、其实还是坏的"）。
    warn "PGO 构建失败，清理后改用非优化构建重编（会慢一些，但保证能装出来）"
    make clean >/dev/null 2>&1 || true
    find . -name '*.o' -o -name '*.a' -o -name '*.so' -o -name '*.gcda' -o -name '*.gcno' \
      | xargs -r rm -f 2>/dev/null || true
    ./configure --prefix="$prefix" >/dev/null 2>&1 || { warn "configure 重跑失败"; return 1; }
    make -j"$n" >/dev/null 2>&1 || { warn "make 失败"; return 1; }
  fi

  # ⚠️ 用 altinstall 而非 install：后者会覆盖 /usr/bin/python3，
  #    而 apt/dnf 自身是 Python 写的，直接搞坏系统包管理。
  make altinstall >/dev/null 2>&1 || { warn "make altinstall 失败"; return 1; }

  # 判据是"真跑一次 import"，不是 make 的退出码 —— 见上文 -dev 包那段。
  local py="$prefix/bin/python3.14"
  if [ -x "$py" ] && "$py" -c "import ctypes,ssl,zlib,sqlite3" 2>/dev/null; then
    log "编译完成：$("$py" --version 2>&1)  关键模块（ctypes/ssl/zlib/sqlite3）可导入 ✓"
  else
    warn "编译产物缺失关键模块（ssl/sqlite3 等），多为缺少 -dev 包所致"
    warn "  请确认已装 libssl-dev / libsqlite3-dev（或 openssl-devel / sqlite-devel）后重跑"
    return 1
  fi

  return 0
}

# ── openssl 升级风险处置（原 install.sh reboot 续跑机制的最小继承）──────
#
# 2026-10-03 真实事故（CentOS Stream 9）：`dnf install openssl-devel` 把
# openssl-libs 从 3.0.1 顶到 3.5.8，sshd 等所有针对旧版本编译的系统组件
# 启动即崩（`OpenSSL version mismatch ... exit 255`），机器失联，重启也不恢复。
#
# 老的整套处置（切国内源 → dnf update → reboot → systemd oneshot 续跑）
# 随 install.sh 删除。风险面本身已大幅压缩：el9 的 Python 编译路径已被
# uv 取代（uv 不装 openssl-devel），仍走源码编译的只剩 el10 与
# deadsnakes 失败回退，el10 已真机全流程实测（Rocky 10.2，未中招）。
#
# 但"检测到 openssl-libs 会被顶掉就**绝不静默继续**"这条底线必须保留：
# 一旦命中就阻断，给出手动步骤（先 update 再 reboot，然后重跑）——
# 重启的时间窗必须由用户自己选，安装器不能替他决定。
handle_openssl_upgrade_risk() {
  precheck_openssl_upgrade || return 0
  echo ""
  echo "======================================================================"
  echo "  ⚠ 检测到安装编译依赖会把系统 openssl-libs 升级 —— 已阻断"
  echo "======================================================================"
  echo "  当前: openssl-libs ${SYS_OPENSSL_CUR}"
  echo "  仓库: openssl-libs ${SYS_OPENSSL_NEW}"
  echo ""
  echo "  2026-10-03 真实事故（CentOS Stream 9）：openssl-libs 被被动升级后，"
  echo "  sshd 等所有针对旧版本编译的系统组件启动即崩（exit 255），机器失联。"
  echo ""
  echo "  正确做法（先把系统更新做完再回来装，全程只失配一次）："
  echo "    dnf update -y && reboot"
  echo "    重启完成后重跑本脚本即可。"
  echo "  （客户机上若跑了锁版本的自编译软件/第三方 rpm，update 会一并升级，"
  echo "    请自行评估后再执行。）"
  echo "======================================================================"
  die "openssl-libs 将被升级，为避免 sshd 失联已阻断：先 'dnf update -y && reboot' 再重跑。"
}

# 取本机某包的版本（无则空）
_rpm_version() {
  rpm -q --qf "%{VERSION}-%{RELEASE}" "$1" 2>/dev/null || true
}

# 查仓库里某包的最新版本。用 `repoquery --latest-limit 1` 而不是
# `dnf install --assumeno` 解析输出：前者无副作用、输出单一字段、好比对。
_repo_latest_version() {
  dnf repoquery --latest-limit 1 --queryformat "%{version}-%{release}" \
    "$1" 2>/dev/null | head -n1 || true
}

# 比较两个 RPM 版本字符串：$1 < $2 时返回 0（真）。
# 用 `sort -V` 判定 —— 对 "3.0.1-18.el9" vs "3.5.8-1.el9" 这种形态结论正确。
_rpm_ver_lt() {
  local a="$1" b="$2"
  [ -z "$a" ] && return 0          # 本机没装 ⇒ 视作"更旧"
  [ -z "$b" ] && return 1          # 仓库查不到 ⇒ 视作"不需要升"
  [ "$a" = "$b" ] && return 1
  # 只比较主版本号（3.0.1 vs 3.5.8）—— 同 major 内的小版本跃迁不会让
  # OpenSSL_version_num 失配（实测 3.5.7 → 3.5.8 时 sshd 正常），
  # 只有 major/minor 变了才炸。这里放宽到完整版本，宁可多提示也不要漏。
  [ "$(printf '%s\n%s\n' "$a" "$b" | sort -V | head -n1)" = "$a" ]
}

# 预检：装 openssl-devel 会不会把系统 openssl-libs 顶上去？
# 输出（设全局变量）：SYS_OPENSSL_CUR / SYS_OPENSSL_NEW
# 返回 0 = 会被升级（需要处理），1 = 不会（可以继续）
precheck_openssl_upgrade() {
  SYS_OPENSSL_CUR="$(_rpm_version openssl-libs)"
  # [WARN] 按**本机架构**查询（评审 P2）：曾硬编码 openssl-libs.x86_64，
  # aarch64 上 repoquery 落空 → "仓库查不到" → 风险门禁在 ARM 上静默失效。
  SYS_OPENSSL_NEW="$(_repo_latest_version "openssl-libs.$(uname -m)")"

  # 本机没装 openssl-libs 或仓库查不到 —— 判不了，按"不用管"处理，
  # 让后续 dnf 自己决定。宁可漏报也不要在此处误拦住正常流程。
  [ -n "$SYS_OPENSSL_CUR" ] && [ -n "$SYS_OPENSSL_NEW" ] || return 1

  if _rpm_ver_lt "$SYS_OPENSSL_CUR" "$SYS_OPENSSL_NEW"; then
    return 0
  fi
  return 1
}

# ── sqlite3 版本检查（2026-10-03 实测新增）──────────────────────────
# ⚠️ 这个检查必须**独立于 Python 准备之外**、每次运行都执行。
#
#    第一版（install.sh）把它放在 ensure_python314() 内部，而该函数第一行
#    就是 `detect_python && return 0` —— Python 已装好时直接返回，
#    检查**根本不执行**。实测抓到：el9 容器第二次跑完整安装，
#    日志里"AI 功能将降级运行"**一次都没出现** —— 而那台机器的
#    sqlite 恰恰是 3.34.1，本该提示。
#
#    教训：把"环境判据"挂在"补齐动作"内部，等于它只在**需要做那个动作**
#    时才生效。判据要独立，不能寄生。
check_sqlite_version() {
  # ⚠️ 「能 import sqlite3」不等于「sqlite3 够新」——这是两个判据。
  #
  #    Python 的 sqlite3 是标准库模块，但**引擎不是 Python 的**：
  #    _sqlite3.cpython-*.so 只做 C 封装，SQL 引擎在系统的 libsqlite3.so.0 里。
  #    所以换 Python 版本救不了 —— 版本由操作系统决定（el9 锁 3.34.1）。
  #    例外是 uv 装的 python-build-standalone：它**自带**高版本 sqlite，
  #    不链系统库 —— 这正是 el9 的推荐出路。
  local sqlite_ver
  sqlite_ver="$("$PY_BIN" -c 'import sqlite3; print(sqlite3.sqlite_version)' 2>/dev/null)" || true
  if [ -n "$sqlite_ver" ] && "$PY_BIN" -c \
    'import sqlite3,sys; sys.exit(0 if sqlite3.sqlite_version_info >= (3,35,0) else 1)' 2>/dev/null; then
    log "sqlite3 $sqlite_ver ✓ (>= 3.35.0，chromadb 要求；RAG 可用)"
    return 0
  fi

  # ── 版本不足：按发行版主版本给出确切结论 ────────────────────────
  # 取主版本号：VERSION_ID 可能是 "9" / "9.3" / "10.2" / "7"
  local maj="" el_name=""
  maj="$(echo "${DISTRO_VER:-}" | cut -d. -f1)"
  case "${DISTRO_ID:-}" in
    rhel|centos|rocky|almalinux|oracle|scientific) el_name="el${maj:-?}" ;;
  esac

  echo ""
  echo "======================================================================"
  echo "  ⚠ AI 功能将降级运行（sqlite3 ${sqlite_ver:-探测失败} < 3.35.0）"
  echo "======================================================================"
  echo ""
  echo "  这不是安装失败 —— 安装会继续，但**本地 RAG 向量检索不可用**。"
  echo ""
  if [ -n "$el_name" ]; then
  case "$maj" in
    7|8|9)
      echo "  原因：${DISTRO_ID} ${DISTRO_VER}（${el_name}）自带的 sqlite 锁在"
      echo "        $(case "$maj" in 7) echo 3.7.17 ;; 8) echo 3.26.0 ;; 9) echo 3.34.1 ;; esac)，"
      echo "        且发行版仓库里**没有任何更新版本可选**（RHEL 系在生命周期内"
      echo "        不升系统库次版本，这是 ABI 稳定性策略，不是没打补丁）。"
      echo ""
      echo "  ⟶ 注意：系统 sqlite 升不动，但**不必为此换操作系统** ——"
      echo "        见下面\"出路 ①\"，换一个 Python 构建即可绕开，代价远小于重装系统。"
      echo ""
      ;;
    *)
      echo "  原因：本机 sqlite 版本低于 chromadb 要求的 3.35.0。"
      echo ""
      ;;
  esac
  else
  echo "  原因：本机 sqlite 版本低于 chromadb 要求的 3.35.0。"
  echo ""
  fi
  echo "  ── 受影响的 AI 能力 ────────────────────────────────────────"
  echo "    · RAG 向量检索（chromadb）        ✗ 不可用"
  echo "    · 混合检索里的关键词侧（FTS5）    ✗ 随 RAGStore 一并停用"
  echo "    · 其余功能（设备管理 / 监控 / IP 管理 / trap / 网关）  ✓ 正常"
  echo ""
  echo "  ── 出路（按代价从小到大）──────────────────────────────────"
  echo ""
  echo "  ① 换用 uv 安装的 Python（推荐 —— 不换系统、不打补丁）"
  echo "     uv python install 3.14"
  echo "     官方 python-build-standalone 构建**自带 sqlite**，不走系统库。"
  echo "     实测：el9 容器系统 sqlite-libs 3.34.1，uv 装的 3.14 → sqlite 3.53.1 ✓"
  echo ""
  echo "  ② 换系统：el10 / Ubuntu 22.04+ / Debian 12+"
  echo "     el10（RHEL 10 / Rocky 10 / Alma 10 / CentOS Stream 10）"
  echo "       实测系统 sqlite 3.46.1 ✓ —— 同为 RHEL 系，迁移成本最低"
  echo "     Ubuntu 22.04+  sqlite 3.37+ ✓"
  echo "     Debian 12（bookworm）+  sqlite 3.40+ ✓"
  echo ""
  echo "  ③ 就地打 shim（次选；chromadb 官方列为第 2 选项，非首选）"
  echo "     pip install pysqlite3-binary        # 自带 sqlite 3.51"
  echo "     并在导入链最早期注入（须早于 import chromadb）："
  echo '       import sys, pysqlite3; sys.modules["sqlite3"] = pysqlite3'
  echo "     ⚠ 它自带另一份 libsqlite3，与系统库是两个构建，行为可能有差异；"
  echo "       且是全局副作用，散落在业务模块里会埋雷。"
  echo ""
  echo "  详见 docs/ops/install-behavior-baseline.md §1.3。"
  echo "======================================================================"
  echo ""
  return 0
}

# ── dnf 源自检与强制修复（RHEL 系，装任何东西之前执行）─────────────
# 2026-10-04 测试机实装教训：机器 yum 源被改坏（centos.repo 的所有段——
# 含 AppStream/CRB——baseurl 全部指向 BaseOS 路径），AppStream 段拉到的
# 其实是 BaseOS 元数据，gcc-c++/cmake 全部 No match，报错完全看不出
# "源被改坏了"，直到安装中段才炸，浪费一整轮。
#
# 策略（强制修复，但绝不静默）：
#   ① 探测关键包可见性（gcc-c++≈AppStream/CRB，make≈BaseOS）
#   ② 失败 → 修"段路径错位"（每段 baseurl 的组件目录必须与 [repo] 名对应）
#   ③ 仍失败 → 整体切换 USTC per-component 标准路径
#   ④ 元数据仍拉不到的仓库自动停用（如 USTC 无 stream9 extras）
#   ⑤ 复验；再失败只 WARN 不阻断——让后续步骤给出明确 No match
# 修改前整体备份到 $REPOS_DIR.bak-repair-<ts>/，幂等可重跑。
REPOS_DIR="${REPOS_DIR:-/etc/yum.repos.d}"

_repo_component_dir() {
  case "$1" in
    baseos) echo BaseOS ;;
    appstream) echo AppStream ;;
    crb) echo CRB ;;
    powertools) echo PowerTools ;;
    extras-common|extras) echo extras ;;
    highavailability) echo HighAvailability ;;
    nfv) echo NFV ;;
    rt) echo RT ;;
    sap) echo SAP ;;
    sapphire) echo Sapphire ;;
    devel) echo devel ;;
    *) echo "" ;;
  esac
}

_repo_arch_segment() {
  case "$(uname -m)" in
    aarch64) echo aarch64 ;;
    *) echo x86_64 ;;
  esac
}

_dnf_packages_visible() {
  # ⚠️ 必须用 `dnf list`（含已安装）而不是 `list available`：
  # available 只列**未安装**的包 —— gcc-c++/make 已装好的机器（本次测试机）
  # 会永远探测"失败"，修复流程每次都白白切源（评审实装第二日发现）。
  dnf -q list gcc-c++ make >/dev/null 2>&1
}

_fix_repo_component_paths() {
  # 每段 baseurl 里紧贴 /<arch>/os 的目录必须与 [repo] 段名对应；
  # 不对应就改写。输出（echo）改动文件数。
  local fixed=0 f sec comp arch tmp line newurl changed
  arch="$(_repo_arch_segment)"
  for f in "$REPOS_DIR"/*.repo; do
    [ -e "$f" ] || continue
    sec=""; changed=0
    tmp="$(mktemp)"
    while IFS= read -r line; do
      case "$line" in
        \[*\]) sec="${line#[}"; sec="${sec%]}"
               sec="$(printf '%s' "$sec" | tr 'A-Z' 'a-z')" ;;
      esac
      newurl="$line"
      if printf '%s' "$line" | grep -qE '^baseurl=' && [ -n "$sec" ]; then
        comp="$(_repo_component_dir "$sec")"
        # 仅当“组件目录≠目标”且形状匹配（/某段/<arch>/os）时改写。
        # [WARN] 模式里组件段与 arch 段之间的 "/" 不能省：
        #   /[^/]+/($arch/os)  ✓（/BaseOS + /x86_64/os）
        #   /[^/]+($arch/os)   ✗（中间的 / 没人吃，永远匹配不上）
        if [ -n "$comp" ] \
           && printf '%s' "$line" | grep -qE "/[^/]+/$arch/os" \
           && ! printf '%s' "$line" | grep -qE "/$comp/$arch/os"; then
          newurl="$(printf '%s' "$line" | sed -E "s#/[^/]+/($arch/os)#/$comp/\1#")"
        fi
      fi
      if [ "$newurl" != "$line" ]; then
        changed=1
        printf '%s\n' "$newurl" >> "$tmp"
      else
        printf '%s\n' "$line" >> "$tmp"
      fi
    done < "$f"
    if [ "$changed" = 1 ]; then
      cp "$f" "$f.bak-repair-$(date +%s)" 2>/dev/null || true
      mv "$tmp" "$f"
      fixed=$((fixed + 1))
      log "  修正段路径错位: $f"
    else
      rm -f "$tmp"
    fi
  done
  echo "$fixed"
}

# ── 第③步切源的镜像候选 ─────────────────────────────────────
# ⚠️ 不硬编码 USTC（2026-10-04 评审反馈：国外机器切 USTC 反而更糟）。
# 候选 = 官方源 + 国内三镜像，按 repomd.xml 探测耗时择优；全不可达则不切。
_repo_releasever() {
  # dnf 自己展开的 ${releasever} 在探测时需解析成真实值
  local v
  v="$(grep -E '^VERSION_ID=' /etc/os-release 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"')"
  case "$(_distro_id)" in
    centos) printf '%s-stream' "${v%%.*}" ;;
    *)      printf '%s' "${v%%.*}" ;;
  esac
}

_pick_dnf_mirror() {
  # 输出：最快的可达镜像 base（到发行版目录为止）；全部不可达时输出空串。
  # :param $1: 镜像布局 kind（centos-stream / rocky / almalinux）
  local kind="$1" ver arch cand probe res code t
  local best="" best_t="999999"
  ver="$(_repo_releasever)"
  arch="$(_repo_arch_segment)"
  local -a bases=()
  case "$kind" in
    centos-stream)
      bases=("https://mirror.stream.centos.org"
             "https://mirrors.ustc.edu.cn/centos-stream"
             "https://mirrors.tuna.tsinghua.edu.cn/centos-stream"
             "https://mirrors.aliyun.com/centos-stream") ;;
    rocky)
      bases=("https://dl.rockylinux.org/pub/rocky"
             "https://mirrors.ustc.edu.cn/rocky"
             "https://mirrors.tuna.tsinghua.edu.cn/rocky"
             "https://mirrors.aliyun.com/rocky") ;;
    almalinux)
      bases=("https://repo.almalinux.org/almalinux"
             "https://mirrors.ustc.edu.cn/almalinux"
             "https://mirrors.tuna.tsinghua.edu.cn/almalinux"
             "https://mirrors.aliyun.com/almalinux") ;;
    *) return 0 ;;                     # rhel/ol：无公开同构镜像，不切
  esac
  for cand in "${bases[@]}"; do
    probe="$cand/$ver/BaseOS/$arch/os/repodata/repomd.xml"
    res="$(curl -s -o /dev/null --connect-timeout 4 -m 10 \
             -w '%{http_code} %{time_total}' "$probe" 2>/dev/null)"
    code="${res%% *}"
    [ "$code" = "200" ] || continue
    t="$(printf '%s' "$res" | awk '{print $2}')"
    if awk -v a="$t" -v b="$best_t" 'BEGIN{exit !(a<b)}'; then
      best="$cand"; best_t="$t"
    fi
  done
  printf '%s' "$best"
}

_switch_repos_to_mirror() {
  # 已知段整体重写为 $1（镜像 base）的 per-component 标准 baseurl；
  # 未知段原样保留。$releasever 必须以字面量落盘（dnf 自己展开）。
  # 落盘 URL：<base>/${releasever}<SUFFIX>/$comp/$arch/os
  # SUFFIX：centos-stream 需要 -stream（releasever=9 → 9-stream），其余为空。
  local base="$1" suffix=""
  case "$(_distro_id)" in
    centos) suffix="-stream" ;;
  esac
  local f sec comp arch url
  arch="$(_repo_arch_segment)"
  for f in "$REPOS_DIR"/*.repo; do
    [ -e "$f" ] || continue
    sec=""
    tmp="$(mktemp)"
    while IFS= read -r line; do
      case "$line" in
        \[*\]) sec="${line#[}"; sec="${sec%]}"
               sec="$(printf '%s' "$sec" | tr 'A-Z' 'a-z')" ;;
      esac
      if printf '%s' "$line" | grep -qE '^baseurl=' && [ -n "$sec" ]; then
        comp="$(_repo_component_dir "$sec")"
        if [ -n "$comp" ]; then
          case "$(_distro_id)" in
            centos|rocky|almalinux)
              url="${base}/\${releasever}${suffix}/$comp/$arch/os" ;;
            *)
              url="" ;;
          esac
          if [ -n "$url" ]; then
            printf 'baseurl=%s\n' "$url" >> "$tmp"
            continue
          fi
        fi
      fi
      printf '%s\n' "$line" >> "$tmp"
    done < "$f"
    mv "$tmp" "$f"
  done
}

_disable_broken_repos() {
  # 元数据拉不到的仓库自动停用（如 USTC 未同步 stream9 的 extras），
  # 否则一次 makecache 失败会连累所有仓库的可见性判定。
  local errs id
  errs="$(dnf makecache 2>&1)"
  printf '%s\n' "$errs" \
    | grep -oE "repo '[^']+'" | sed "s/repo '//;s/'//" | sort -u \
    | while read -r id; do
        [ -n "$id" ] || continue
        warn "  仓库 $id 元数据不可用，自动停用（若安装需要它请手工换源）"
        dnf config-manager --set-disabled "$id" 2>/dev/null \
          || sed -i -E "/^\[$id\]/,/^\$/s/^enabled=1/enabled=0/" \
               "$REPOS_DIR"/*.repo 2>/dev/null
      done
}

repair_dnf_repos() {
  case "$(_distro_id)" in
    centos|rocky|almalinux|rhel|ol) ;;
    *) return 0 ;;                     # 非 RHEL 系（apt）无此问题
  esac
  command -v dnf >/dev/null 2>&1 || return 0

  if _dnf_packages_visible; then
    log "dnf 源自检通过（关键包 gcc-c++/make 可见），不改源"
    return 0
  fi
  log "dnf 源自检失败（关键包不可见）——开始强制修复为标准格式（先备份）"
  cp -r "$REPOS_DIR" "$REPOS_DIR.bak-repair-$(date +%s)" 2>/dev/null || true

  local n
  n="$(_fix_repo_component_paths)"
  dnf clean all -q 2>/dev/null
  _disable_broken_repos
  if _dnf_packages_visible; then
    log "  修复完成：段路径错位 $n 个文件，自检通过 ✓"
    return 0
  fi

  log "  仍不可见，测速选择镜像（官方源 + 国内镜像候选，取最快可达）"
  local kind base
  case "$(_distro_id)" in
    centos)    kind="centos-stream" ;;
    rocky)     kind="rocky" ;;
    almalinux) kind="almalinux" ;;
    *)         kind="" ;;            # rhel/ol：无公开同构镜像，不切
  esac
  if [ -n "$kind" ]; then
    base="$(_pick_dnf_mirror "$kind")"
    if [ -n "$base" ]; then
      log "  最快可达镜像：$base"
      _switch_repos_to_mirror "$base"
      dnf clean all -q 2>/dev/null
      _disable_broken_repos
      if _dnf_packages_visible; then
        log "  切换镜像后自检通过 ✓"
        return 0
      fi
    else
      warn "  所有候选镜像均不可达 —— 放弃切源（切了也没用，原始源已备份）"
    fi
  fi
  warn "dnf 源修复后关键包仍不可见 —— 继续安装，失败时优先排查源配置"
  warn "  （原始源已备份在 $REPOS_DIR.bak-repair-*/）"
}

# ── 主流程 ─────────────────────────────────────────────────
main() {
  # exec 前会 cd scripts/，先把相对的 --source-root 值转为绝对
  # （评审 P2：相对路径会在 cd 后静默指向错误目录）
  if [ "$#" -gt 0 ]; then
    local -a _args=()
    local _want_val=0 _a
    for _a in "$@"; do
      if [ "$_want_val" = 1 ]; then
        _want_val=0
        case "$_a" in
          /*) _args+=("$_a") ;;
          *)  _args+=("$PWD/$_a") ;;
        esac
      else
        [ "$_a" = "--source-root" ] && _want_val=1
        _args+=("$_a")
      fi
    done
    set -- ${_args[@]+"${_args[@]}"}
  fi

  check_system_support          # 不支持直接 exit 1，什么都不动
  repair_dnf_repos              # RHEL 系：源被改坏时强制修复为标准格式（自愈，不阻断）
  check_tmp_exec || die "/tmp 不可执行，安装无法继续（原因见上）。"

  ensure_python314 || die "无法为本机准备 Python >= ${PYTHON_MIN}。
  自动补齐的三条路径（deadsnakes PPA / uv / 源码编译）都未成功。
  可手工装好 Python 3.14 后重跑本脚本，已完成的步骤不会重做。"

  # 独立判据：sqlite 版本（不足只 WARN 降级，不阻断 —— 与 conf 口径一致）
  check_sqlite_version

  log "交接给编排器：$PY_BIN -m installer $*"
  cd "$SOURCE_ROOT/scripts" || die "找不到 scripts 目录：$SOURCE_ROOT/scripts"
  exec "$PY_BIN" -m installer "$@"
}

# 仅直接执行时跑 main；被 source（测试抠函数）时不触发
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
