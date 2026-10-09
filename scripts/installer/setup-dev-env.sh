#!/usr/bin/env bash
# setup-dev-env.sh —— IPIP 一键开发环境自举（沙箱 / 新机通用，可分发）
#
# 痛点：重置沙箱 / 换机后工具链丢光，手敲 grep -rn / 翻日志找文件太慢。
# 本脚本一次性恢复：
#   1) CLI 查找工具：fd（文件查找）、fzf（模糊选择）、ripgrep（rg / rg -F）、bat（预览高亮）
#   2) 交互式检索函数（写入 ~/.zshrc.d & ~/.bashrc.d，由 rc 自动 source）：
#        fs  'regex'       全仓正则搜索，fzf 列表 + bat 预览，选中 vim +行号打开
#        fs  -F 'literal'  固定字符串搜索
#        fspy 'def '       仅搜 .py
#        ff  name          按文件名查找，选中打开
#        fh                历史命令交互回填到当前命令行
#   3) 前端门禁：自动确保 Node≥26.7 + pnpm（基线单一真源 = judge/version.py 的 BASELINES，
#      勿在此另写数字），跑 `pnpm install` 触发 husky 钩子 + lint-staged（pre-commit 卡口）
#   4) skill 加载：把本仓 .codebuddy/skills/* 软链到 ~/.codebuddy/skills，任意 cwd 的会话都能自动加载
#   5) 宿主机基线：Python 3.14 + Redis —— **复用** scripts/installer 的判据层/执行层，
#      本脚本不另写 apt/brew 逻辑（那边已处理 deadsnakes PPA / EPEL / 源码编译等发行版差异）
#   6) 项目环境：.venv314（本仓主力解释器，Makefile 优先取它）+ 依赖 + 测试前置 Redis 可达
#
# 跳过 Node 安装：SKIP_NODE=1 bash scripts/installer/setup-dev-env.sh（假设你已自装满足基线的 node + pnpm）
# 跳过依赖安装：SKIP_DEPS=1 bash scripts/installer/setup-dev-env.sh（只建 .venv314，不装 torch/requirements）
#
# 多平台：Linux(apt/dnf/yum/apk) / macOS(brew)；双 shell：zsh & bash 自动注入。
# 幂等：重复执行安全（工具已装则跳过；rc 片段按标记去重；旧版块自动清理；函数文件固定名覆盖写）。
# Git 跟踪位置：scripts/installer/；其他机器 clone 本仓库后可直接 bash 运行。
#
# 用法：
#   bash scripts/installer/setup-dev-env.sh
#   新开交互 shell（bash/zsh）后即生效；当前 shell 执行：source ~/.zshrc （或 ~/.bashrc）
#
# 注意：fzf 需要交互式终端（tty）。ssh / tmux 进沙箱敲命令即可；非交互 Bash 调用（无 tty）跑不了 fzf。
set -euo pipefail

# 脚本真实目录与仓库根（供 [5][6] 段定位 frontend-new / .codebuddy/skills）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

OS="$(uname -s)"
echo "==> 平台检测: $OS"

# root 直装，非 root 走 sudo
run_as() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

# 取**系统** python（绕开 pyenv shim）—— 供 [5][7][8] 段调 installer 用。
# 为什么不能用 `python3`：本仓 `.python-version` 是 3.14，pyenv shim 在 3.14
# 尚未安装时会先报错退出，命令根本跑不起来；而 [7] 段要装的恰恰就是 3.14。
host_python() {
  local c
  for c in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  command -v python3 2>/dev/null || true
}

# 点分数字版本比较：``_ge_ver A B`` 为真表示 A >= B（缺位按 0，故 26.7 == 26.7.0）
_ge_ver() {
  local i max x y
  local -a a b
  IFS='.' read -r -a a <<< "${1:-0}"
  IFS='.' read -r -a b <<< "${2:-0}"
  max=${#a[@]}; [ "${#b[@]}" -gt "$max" ] && max=${#b[@]}
  for ((i = 0; i < max; i++)); do
    x="${a[i]:-0}"; y="${b[i]:-0}"
    [ "$x" -gt "$y" ] 2>/dev/null && return 0
    [ "$x" -lt "$y" ] 2>/dev/null && return 1
  done
  return 0
}

# ---------- [1] 安装工具 ----------
install_tools() {
  local bin need=()
  for bin in fd fzf rg bat; do
    if command -v "$bin" >/dev/null 2>&1; then
      echo "    $bin: 已就绪，跳过"
    else
      need+=("$bin")
    fi
  done
  # fd 可能已以 fdfind 形式存在（Debian fd-find 包的二进制名）
  if [ ${#need[@]} -eq 1 ] && [ "${need[0]}" = "fd" ] && command -v fdfind >/dev/null 2>&1; then
    need=()
  fi
  if [ ${#need[@]} -eq 0 ]; then
    echo "==> [1/8] 工具已就绪，跳过安装"
    return 0
  fi
  echo "==> [1/8] 待安装: ${need[*]}"

  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      brew install "${need[@]}"
    else
      echo "    macOS 未检测到 brew，请先装 Homebrew，或手动安装: ${need[*]}" >&2
    fi
  elif [ "$OS" = "Linux" ]; then
    if command -v apt-get >/dev/null 2>&1; then
      run_as apt-get update || true   # 容忍非主干源（nvidia/cli.github 等）握手失败
      local apt_pkgs=()
      for bin in "${need[@]}"; do
        case "$bin" in
          fd) apt_pkgs+=(fd-find) ;;   # Debian/Ubuntu 的 fd 包名为 fd-find
          *)  apt_pkgs+=("$bin") ;;
        esac
      done
      run_as apt-get install -y "${apt_pkgs[@]}" || echo "    警告: 安装部分失败(源/网络), 预览将降级, 不影响 fs/ff 核心"
    elif command -v dnf >/dev/null 2>&1; then
      run_as dnf install -y "${need[@]}" || echo "    警告: dnf 安装失败"
    elif command -v yum >/dev/null 2>&1; then
      run_as yum install -y "${need[@]}" || echo "    警告: yum 安装失败"
    elif command -v apk >/dev/null 2>&1; then
      run_as apk add "${need[@]}" || echo "    警告: apk 安装失败"
    else
      echo "    未识别的 Linux 包管理器，请手动安装: ${need[*]}" >&2
    fi
  else
    echo "    未识别平台 ${OS}，请手动安装: ${need[*]}" >&2
  fi
}

install_tools

# Debian/Ubuntu 的 bat 包二进制名为 batcat（避免与 bacula 的 bat 冲突），建立软链让检索函数里的 `bat` 可用
if command -v batcat >/dev/null 2>&1 && ! command -v bat >/dev/null 2>&1; then
  echo "==> [1.5/8] 建立 bat -> batcat 软链（Debian/Ubuntu）"
  run_as ln -sf "$(command -v batcat)" /usr/local/bin/bat
fi

# 与上面 bat 同款 Debian 改名问题：官方 fd 包在这里叫 **fdfind**（同源于和
# fdisk 的 fd 冲突）。
# 光靠下面 [2] 步写进 rc 的 `alias fd='fdfind'` 是不够的 —— alias 只在
# **交互式** shell 生效，`~/.bashrc` 开头那句 `[ -z "$PS1" ] && return` 会让
# 非交互 shell 直接返回。后果是：`make xxx` 调的脚本、CI step、subprocess、
# editor 的 shell 命令里 `fd` 一律 command not found，只有人肉敲命令时好用。
# 所以在 /usr/local/bin 补一个同名软链，两种场景都能用；rc 里的 alias 保留
# 无害（指向同一处，且纯 new-instance shell 不读 alias 时软链兜底）。
if command -v fdfind >/dev/null 2>&1 && ! [ -e /usr/local/bin/fd ]; then
  echo "==> [1.6/8] 建立 fd -> fdfind 软链（Debian/Ubuntu）"
  run_as ln -sf "$(command -v fdfind)" /usr/local/bin/fd
fi

# ---------- [2] rc 片段：fd 别名 + FZF 默认选项（幂等，去重旧版） ----------
echo "==> [2/8] 配置 rc 片段（fd 别名 / FZF 选项）"
for rc in ~/.zshrc ~/.bashrc; do
  [ -f "$rc" ] || continue
  # 清理旧版 setup-cli-tools.sh 注入的 "IPIP CLI 工具链" 块（功能已被新块覆盖，避免重复 alias/FZF 设置）
  if grep -q "IPIP CLI 工具链" "$rc" 2>/dev/null; then
    sed -i '/# ---- IPIP CLI 工具链/,/# ---- end IPIP CLI 工具链 ----/d' "$rc"
    echo "    清理旧版 CLI 块: $rc"
  fi
  # 已存在新块则跳过
  if grep -q "IPIP dev-env" "$rc" 2>/dev/null; then
    echo "    跳过（已存在）: $rc"
    continue
  fi
  cat >> "$rc" <<'RC_EOF'

# ---- IPIP dev-env（setup-dev-env.sh 注入，幂等）----
# fd: 快速文件查找（fd-find 的二进制名为 fdfind）
alias fd='fdfind'
# 搜索直接用 ripgrep：rg '正则' / rg -F '字面串'（已装，无需另设 fg 包装）
export FZF_DEFAULT_OPTS="--height 40% --border"
# ---- end IPIP dev-env ----
RC_EOF
  echo "    已写入: $rc"
done

# ---------- [3] 交互式检索函数（写入 .zshrc.d & .bashrc.d） ----------
echo "==> [3/8] 写入检索函数（zsh & bash 通用）"
ZSH_DIR="$HOME/.zshrc.d"; BASH_DIR="$HOME/.bashrc.d"
mkdir -p "$ZSH_DIR" "$BASH_DIR"
# 清理旧版文件名（避免重复 source 同名函数两次）
rm -f "$ZSH_DIR/fs-funcs.zsh" "$BASH_DIR/fs-funcs.sh" 2>/dev/null || true

cat > "$ZSH_DIR/99-ipip-search.zsh" <<'FUNC_EOF'
# ===== IPIP 交互式检索工具链（fs/ff/fh，zsh & bash 通用）=====
# 依赖：rg fzf（必）；fd/fdfind（ff 用，缺则回退 find）；bat（预览高亮，缺则 cat 回退）
# 修复：--with-filename 保证单文件匹配也带文件名；主管道 --color=never 防 ANSI 残留
export EDITOR="${EDITOR:-vim}"

fs() {
  if [ $# -eq 0 ]; then
    echo "Usage: fs <regex>        # 正则搜索"
    echo "       fs -F 'literal'   # 固定字符串"
    echo "       fs -t py 'def '   # 限定类型"
    return 1
  fi
  local result file line
  result=$(rg --with-filename --line-number --color=never "$@" | fzf \
    --delimiter : \
    --preview 'bat --color=always --highlight-line {2} {1} 2>/dev/null || rg --color=always -n {2} {1} 2>/dev/null || cat {1}' \
    --preview-window '~3,+50')
  [ -z "$result" ] && return 0
  file=$(printf '%s' "$result" | cut -d: -f1)
  line=$(printf '%s' "$result" | cut -d: -f2)
  "${EDITOR}" +"$line" "$file"
}

fspy() { fs -t py "$@"; }

ff() {
  local result src
  if command -v fdfind >/dev/null 2>&1; then
    src=$(fdfind --color=never "$@")
  elif command -v fd >/dev/null 2>&1; then
    src=$(fd --color=never "$@")
  else
    src=$(find . -type f -name "*$1*" 2>/dev/null)
  fi
  result=$(printf '%s\n' "$src" | fzf \
    --preview 'bat --color=always {} 2>/dev/null || cat {}' \
    --preview-window 'right,50%')
  [ -z "$result" ] && return 0
  "${EDITOR}" "$result"
}

fh() {
  local cmd
  cmd=$(history 1 | fzf --height 40% --tac | sed 's/^[0-9]\+[[:space:]]*//')
  [ -z "$cmd" ] && return 0
  if [ -n "${ZSH_VERSION:-}" ]; then
    print -z -- "$cmd"
  else
    READLINE_LINE="$cmd"
    READLINE_POINT=${#READLINE_LINE}
  fi
}
FUNC_EOF

cp "$ZSH_DIR/99-ipip-search.zsh" "$BASH_DIR/99-ipip-search.sh"
echo "    已写入: $ZSH_DIR/99-ipip-search.zsh 和 $BASH_DIR/99-ipip-search.sh"

# ---------- [4] 确保 rc 自动 source .d 目录（兼容基础镜像/dotfiles 自带的循环，避免重复注入） ----------
echo "==> [4/8] 确保 rc 自动 source .d 目录"
ensure_autosource() {
  local rc="$1" base="$2"
  if grep -qE "\.$base\b" "$rc" 2>/dev/null; then
    echo "    跳过（已存在 .$base 自动 source）: $rc"
  else
    printf '\n# ---- IPIP dev-env auto-source .%s ----\nfor i in $(ls -A $HOME/.%s); do source $HOME/.%s/$i; done\n# ---- end ----\n' "$base" "$base" "$base" >> "$rc"
    echo "    已写入: $rc"
  fi
}
ensure_autosource "$HOME/.zshrc" "zshrc.d"
ensure_autosource "$HOME/.bashrc" "bashrc.d"

# ---------- [5/8] 前端门禁恢复（Node 基线 + husky 钩子 + lint-staged） ----------
# 目标：新 clone / 新沙箱一次跑完，pre-commit 卡口自动就位。
# 逻辑：确保 node 满足**基线**与 pnpm → cd frontend-new && pnpm install
#       （prepare 跑 `cd .. && husky .husky`）→ 校验 .husky/_/h 生成、hooksPath 已设。
# 可跳过：SKIP_NODE=1 跳过 Node 安装（假设你已自装满足基线的 node + pnpm）。
#
# ⚠️ 为什么基线不是 `>=20`：vite 8 / rolldown 的 engines 是
#    `^20.19.0 || >=22.12.0`，像 20.18.x 这种版本能通过粗放的主版本检查，
#    但 pnpm 会**静默跳过**不满足 engines 的原生依赖
#    @rolldown/binding-linux-x64-gnu，直到构建阶段才报
#    `Cannot find native binding` —— 报错点离根因极远。
#    基线的单一真源是 scripts/installer/judge/version.py 的 BASELINES。
echo "==> [5/8] 前端门禁恢复（Node 基线 + husky + lint-staged）"
FE_ROOT="$REPO_ROOT/frontend-new"

# 读基线（单一真源）；读不到才退回硬编码值 —— 不让「读配置」本身变成失败点
NODE_BASELINE="$( ( cd "$REPO_ROOT/scripts" && "$(host_python)" - <<'PY_EOF'
import sys
sys.path.insert(0, ".")
try:
    from installer.judge.version import BASELINES
    print(BASELINES["node"])
except Exception:
    print("")
PY_EOF
) 2>/dev/null | tail -1)"
[ -n "$NODE_BASELINE" ] || NODE_BASELINE="26.7"
echo "    node 基线: ${NODE_BASELINE}（scripts/installer/judge/version.py）"

# 确保 pnpm（版本取自 frontend-new/package.json 的 packageManager，单一真源）
ensure_pnpm() {
  local want
  want="$(node -e "try{process.stdout.write(((require('$FE_ROOT/package.json').packageManager||'').split('@')[1])||'')}catch(e){}" 2>/dev/null || true)"
  [ -n "$want" ] || want="10.34.5"
  if command -v pnpm >/dev/null 2>&1; then
    echo "    pnpm: 已就绪 $(pnpm -v)（package.json 要求 ${want}）"
    return 0
  fi
  if command -v corepack >/dev/null 2>&1; then
    run_as corepack enable >/dev/null 2>&1 && run_as corepack prepare "pnpm@$want" --activate >/dev/null 2>&1 \
      && echo "    corepack 启用 pnpm@$want" \
      || echo "    警告: corepack 启用 pnpm 失败"
  elif command -v npm >/dev/null 2>&1; then
    run_as npm i -g "pnpm@$want" >/dev/null 2>&1 && echo "    npm 全局装 pnpm@$want" || echo "    警告: npm 装 pnpm 失败"
  else
    echo "    警告: 无 npm/corepack，无法装 pnpm"
  fi
}

ensure_node() {
  local v
  if command -v node >/dev/null 2>&1; then
    v="$(node -v 2>/dev/null | tr -d 'v')"
    if _ge_ver "$v" "$NODE_BASELINE"; then
      echo "    node: 已就绪 $(node -v)（>= ${NODE_BASELINE}），跳过安装"
      ensure_pnpm
      return 0
    fi
    echo "    node: 版本偏低 v${v}（基线 ${NODE_BASELINE}），尝试补齐"
  fi
  if [ "${SKIP_NODE:-0}" = "1" ]; then
    echo "    SKIP_NODE=1：跳过 Node 安装，假设你已自装 node>=${NODE_BASELINE} 与 pnpm"
    return 0
  fi

  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    # 有 nvm：用 nvm 管版本与 default alias（不动系统包，最不易与既有环境打架）。
    # 本地若已有满足基线的版本就直接用它 —— 否则 `nvm install 26.7` 会为了
    # 「26.7」再下一个 26.7.x，而机器上可能早有 26.10.0。
    # shellcheck disable=SC1090
    . "$HOME/.nvm/nvm.sh"
    local have=""
    while read -r vv; do
      [ -n "$vv" ] || continue
      if _ge_ver "$vv" "$NODE_BASELINE"; then have="$vv"; break; fi
    done < <(nvm ls --no-colors 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | tr -d 'v' | sort -Vr)
    if [ -n "$have" ]; then
      nvm alias default "$have" >/dev/null 2>&1 \
        && echo "    nvm: 本地已有 v${have}（>= ${NODE_BASELINE}），已设为 default" \
        || echo "    警告: nvm alias default $have 失败"
    else
      nvm install "$NODE_BASELINE" && nvm alias default "$NODE_BASELINE" \
        && echo "    nvm 安装完成: node $(nvm version default 2>/dev/null)" \
        || echo "    警告: nvm 安装 node 失败，请手动安装 node>=${NODE_BASELINE}"
    fi
    # 关键：切到 default，确保脚本后续 pnpm install 真正用上满足基线的 node
    # （否则 vite 8 / rolldown 会静默跳过原生依赖，构建期才报 Cannot find native binding）
    nvm use default >/dev/null 2>&1 || echo "    警告: nvm use default 失败"
  elif [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      brew install node || echo "    警告: brew install node 失败"
    else
      echo "    警告: macOS 上未检测到 nvm/brew，请手动安装 node>=${NODE_BASELINE}"
    fi
  else
    # 无 nvm：复用 installer 的 syspkg.ensure_node（NodeSource / 各发行版配方，
    # 单一真源）—— 不在这里再抄一份下载解包逻辑
    ( cd "$REPO_ROOT/scripts" && "$(host_python)" - <<'PY_EOF'
import sys
sys.path.insert(0, ".")
from installer.judge.facts import collect
from installer.judge.version import BASELINES
from installer.act import syspkg

syspkg.ensure_node(collect(), BASELINES["node"])
PY_EOF
    ) || echo "    警告: Node 补齐未成功（继续；前端构建可能失败）"
  fi
  ensure_pnpm
}
ensure_node

if [ -d "$FE_ROOT" ]; then
  # 1) 确保依赖：首次 clone 必须 install（会触发 prepare → husky）；node_modules 已存在则跳过
  if [ ! -d "$FE_ROOT/node_modules" ]; then
    echo "    运行 pnpm install（首次安装会触发 prepare → husky 钩子）..."
    ( cd "$FE_ROOT" && pnpm install ) 2>&1 | tail -5 || echo "    警告: pnpm install 失败，门禁未恢复"
  else
    echo "    依赖已装（node_modules 存在），跳过 pnpm install"
  fi
  # 2) 显式兜底：husky shim 缺失时直接初始化（pnpm 在 node_modules 已存在时未必重跑 prepare）
  if [ ! -e "$REPO_ROOT/.husky/_/h" ]; then
    echo "    husky shim 缺失，显式初始化..."
    ( cd "$REPO_ROOT" && "$FE_ROOT/node_modules/.bin/husky" .husky ) 2>&1 | tail -3 \
      || echo "    警告: husky 初始化失败，请手动 cd frontend-new && pnpm install"
  fi
  # 3) 校验（.husky 在仓库根，非 frontend-new 下）
  if [ -e "$REPO_ROOT/.husky/_/h" ]; then
    hp="$(git -C "$REPO_ROOT" config core.hooksPath 2>/dev/null || true)"
    echo "    husky 就绪: shim=yes hooksPath=${hp:-未设}"
  else
    echo "    警告: husky shim 仍未生成，pre-commit 不会触发，请手动 cd frontend-new && pnpm install"
  fi
else
  echo "    未找到 ${FE_ROOT}，跳过前端门禁（非前端项目？）"
fi

# ---------- [6] skill 全局软链（任意 cwd 的 WorkBuddy 会话都能自动加载 IPIP skill） ----------
echo "==> [6/8] 加载 IPIP skill 到全局 ~/.codebuddy/skills"
SKILL_SRC="$REPO_ROOT/.codebuddy/skills"
SKILL_DST="$HOME/.codebuddy/skills"
if [ -d "$SKILL_SRC" ]; then
  mkdir -p "$SKILL_DST"
  linked=0
  for d in "$SKILL_SRC"/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    link="$SKILL_DST/$name"
    if [ -L "$link" ]; then
      if [ "$(readlink "$link")" = "${d%/}" ]; then echo "    跳过（已链接）: $name"; continue; fi
      rm -f "$link"
    elif [ -e "$link" ]; then
      echo "    跳过（已存在非软链，避免覆盖）: $name"; continue
    fi
    ln -s "${d%/}" "$link" && { echo "    已链接: $name -> ${d%/}"; linked=1; }
  done
  [ "$linked" = "1" ] && echo "    完成。重启 WorkBuddy 会话后，从任意目录都能自动加载这些 skill"
else
  echo "    未找到 ${SKILL_SRC}，跳过 skill 链接"
fi

# ---------- [7/8] 宿主机基线：Python 3.14 + Redis ----------
# 为什么这里不自己 apt/brew 一遍：**single source of truth**。
# scripts/installer/（生产安装器）已经把各发行版差异处理完了 ——
#   · Ubuntu 24.04 官方源给不出 3.14 → 走 deadsnakes PPA（1 分钟 vs 源码编译 15 分钟）；
#   · 其它发行版走源码编译（RHEL 系连 PPA 都没有，PPA 是 Debian 系的东西）；
#   · redis 在 RHEL 系位于 EPEL（不加 repo 会报 "No match for argument: redis"，
#     那个报错不指向"你没启用 EPEL"，极易被读成"这发行版没有 redis"）。
# 这些配方写在 act/syspkg.py 的 matrix 里且有测试守着；在本脚本里重写一份，
# 就是把「同一件事的两套实现」再种一遍，迟早漂移。
#
# Python 3.14 是**硬要求**而非"有余力再升"：realtime_gateway 用了
# asyncio.AsyncGenerator，该属性 3.14 才存在，低于此版本启动即崩
# （判据见 scripts/installer/judge/version.py 的 BASELINES）。
#
# ⚠️ 两个坑（2026-10-04 实测）：
#   1) 调 installer 必须用**系统 python**（见脚本前部 host_python），不能用 `python3`
#      —— 本仓 `.python-version` 是 3.14，pyenv shim 在 3.14 尚未安装时会先报错
#      退出，命令根本跑不起来；而本步要装的恰恰就是 3.14，正好鸡生蛋。
#   2) `uv` 同样可能是 pyenv shim，在仓库目录下调用会踩同一个坑（须在 $HOME 下调用）。
echo "==> [7/8] 宿主机基线（Python 3.14 + Redis）"

if [ "$OS" = "Darwin" ]; then
  # macOS 不在 installer 的支持矩阵内（judge/support.py 只覆盖 Linux 发行版），走 brew
  if command -v brew >/dev/null 2>&1; then
    for pkg in python@3.14 redis; do
      if brew list --versions "$pkg" >/dev/null 2>&1; then
        echo "    $pkg: 已就绪，跳过"
      else
        brew install "$pkg" || echo "    警告: brew install $pkg 失败（继续）"
      fi
    done
  else
    echo "    警告: 未检测到 brew，无法自动补齐 Python 3.14 / Redis（请手动安装）"
  fi
else
  HP="$(host_python)"
  if [ -z "$HP" ]; then
    echo "    警告: 找不到可用的系统 python3，跳过宿主机基线补齐"
  else
    ( cd "$REPO_ROOT/scripts" && "$HP" - <<'PY_EOF'
import sys
sys.path.insert(0, ".")
from installer.judge.facts import collect
from installer.judge.version import BASELINES
from installer.act import syspkg

f = collect()
print(f"    当前: Python {f.python_display}  redis {f.redis_version or '缺失'}")
syspkg.ensure_python(f, BASELINES["python"])
syspkg.ensure_redis(f)
PY_EOF
    ) || echo "    警告: 宿主机基线补齐未成功（继续；后续步骤可能受影响）"
  fi
fi

# ---------- [8/8] 项目环境：.venv314 + 依赖 + Redis 可达 ----------
# .venv314 是 **Makefile 的优先解释器**（Makefile:15：有 .venv314/bin/python 就用它，
# 否则退回历史 .venv）。缺了它，`make test` 会静默跑在别的解释器上。
# 建 venv / 装依赖同样复用 installer 的 act/venv.py —— 那里处理了两个易踩的坑：
#   · **torch 必须先于 requirements 装**：requirements 里的 sentence-transformers
#     传递依赖 torch>=2.2，先装它 pip 会从 PyPI 拉默认形态（CUDA 版，wheel 单独
#     554MB + nvidia-* 约 3GB），随后再被 --force-reinstall 覆盖成 CPU 版 —— 下载两遍；
#   · requirements.lock 走 `--no-deps` 跳过依赖图求解（实测省 147s）。
echo "==> [8/8] 项目环境（.venv314 + 依赖 + Redis 可达）"

if [ "${SKIP_DEPS:-0}" = "1" ] && [ -x "$REPO_ROOT/.venv314/bin/python" ]; then
  echo "    SKIP_DEPS=1 且 .venv314 已存在，跳过"
elif [ -x "$REPO_ROOT/.venv314/bin/python" ] \
     && "$REPO_ROOT/.venv314/bin/python" -c "import flask, sqlalchemy, pytest, ruff" >/dev/null 2>&1; then
  echo "    .venv314 依赖已就绪（含 dev），跳过"
else
  HP="$(host_python)"
  if [ -z "$HP" ]; then
    echo "    警告: 找不到可用的系统 python3，跳过 .venv314 创建"
  else
    ( cd "$REPO_ROOT/scripts" \
        && IPIP_REPO_ROOT="$REPO_ROOT" SKIP_DEPS="${SKIP_DEPS:-0}" "$HP" - <<'PY_EOF'
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")
from installer.judge.facts import collect
from installer.act import shell as sh
from installer.act import venv as venv_mod

repo = Path(os.environ["IPIP_REPO_ROOT"])
skip_deps = os.environ.get("SKIP_DEPS") == "1"

facts = collect()
if not facts.python_bin:
    print("    [skip] 未找到满足基线的 Python 3.14，跳过 .venv314（请先解决上一步）")
    raise SystemExit(0)

v = venv_mod.ensure_venv(repo / ".venv314", facts.python_bin)

# uv 创建的 venv **默认不带 pip**（uv 自己管包安装），而 installer 的
# install_torch 走 `python -m pip` —— 不补这一步就会报 "No module named pip"，
# 且报错点离真因很远（表现为「CPU 版 torch 安装失败」，像是镜像/网络问题）。
# 由 `python -m venv` 创建的 venv 自带 pip，此判断自然跳过。
if not sh.run([v.py, "-m", "pip", "--version"], check=False, echo=False).ok:
    print("[venv] venv 内无 pip（uv 建的默认不带），用 ensurepip 补上")
    sh.run([v.py, "-m", "ensurepip", "--upgrade"], check=False, label="补 pip")

venv_mod.upgrade_pip(v)
if skip_deps:
    print("    SKIP_DEPS=1：只建 venv，跳过依赖安装")
else:
    flavor, multi = venv_mod.resolve_flavor(repo / "instance" / ".install-flavor", "cpu")
    venv_mod.install_torch(v, repo, flavor, cuda_multi_mirror=multi, force_upstream=False)
    venv_mod.install_requirements(v, repo)

    # installer 的 install_requirements 只认 requirements.txt（**生产口径**）；
    # 开发口径的 requirements-dev.txt（pytest / ruff / coverage / hypothesis…）
    # 要在这里补一次 —— 它内部 `-r requirements.txt`，重复部分会被跳过。
    # 不补这一步的后果：`make test` 找不到 pytest；Makefile 的 RUFF 变量
    # （找 .venv314/bin/ruff）落空后退回系统 ruff，版本不再受 requirements-dev 钉定。
    dev_req = repo / "requirements-dev.txt"
    if dev_req.is_file():
        uv_bin = Path(v.py).parent / "uv"
        if uv_bin.is_file():
            args = [str(uv_bin), "pip", "install", "--python", v.py]
        else:
            args = [v.py, "-m", "pip", "install"]
        idx = venv_mod._index_url()  # noqa: SLF001 —— 复用同一套选源结果，避免两处不一致
        if idx:
            args += ["--index-url", idx]
        args += ["-r", str(dev_req)]
        sh.run(args, check=False, label="安装 requirements-dev（pytest / ruff）")
PY_EOF
    ) || echo "    警告: .venv314 / 依赖安装未成功（继续；跑 make 前请手动补齐）"
  fi
fi

# 测试前置：Redis 可达。复用**既有门禁**（Makefile:411 的 ensure-test-redis 是同一个脚本），
# 不重写探测逻辑 —— 它已处理「systemd 优先 / 无 systemd 时 daemonize 直起 / 并发兜底」。
PY_FOR_GATE="$REPO_ROOT/.venv314/bin/python"
[ -x "$PY_FOR_GATE" ] || PY_FOR_GATE="$(host_python)"
if [ -n "$PY_FOR_GATE" ]; then
  "$PY_FOR_GATE" "$REPO_ROOT/scripts/ensure_test_redis.py" \
    || echo "    警告: Redis 未就绪（跑 make test 时门禁会自动重试拉起）"
fi

# ---------- 校验 ----------
echo
echo "==> 校验"
for t in fdfind fzf rg bat; do
  printf "  %-8s " "$t"
  if command -v "$t" >/dev/null 2>&1; then echo "OK"; else echo "缺失 (bat 预览降级)"; fi
done
printf "  %-8s " "fd"
# 分两档报告：**非交互可用**（软链/真名，才是脚本与 CI 能用的那档）与
# **仅交互可用**（只有 alias）。两者不同档 —— alias 在非交互 shell 里不存在，
# 只报"OK"会让人以为 Makefile 里也能用 fd。
if command -v fd >/dev/null 2>&1; then
  echo "OK（非交互可用：$(command -v fd)）"
elif command -v fdfind >/dev/null 2>&1; then
  echo "仅交互可用（缺 /usr/local/bin/fd 软链，脚本里请用 fdfind 或重跑本脚本）"
else
  echo "缺失 (ff 回退 find)"
fi
echo "  函数文件:"
ls -1 "$ZSH_DIR/99-ipip-search.zsh" "$BASH_DIR/99-ipip-search.sh" 2>/dev/null
echo "  前端门禁:"
printf "  %-8s " "node"; \
  if command -v node >/dev/null 2>&1; then \
    _nv="$(node -v 2>/dev/null | tr -d 'v')"; \
    if _ge_ver "$_nv" "${NODE_BASELINE:-26.7}"; then \
      echo "OK ($(node -v) >= ${NODE_BASELINE:-26.7})"; \
    else \
      echo "低于基线 ($(node -v) < ${NODE_BASELINE:-26.7}；若刚装完，请新开 shell)"; \
    fi; \
  else \
    echo "缺失（SKIP_NODE 或手动装）"; \
  fi
printf "  %-8s " "pnpm"; command -v pnpm >/dev/null 2>&1 && echo "OK ($(pnpm -v))" || echo "缺失"
printf "  %-8s " "husky"; [ -e "$REPO_ROOT/.husky/_/h" ] && echo "OK (钩子已生成)" || echo "未生成（cd frontend-new && pnpm install）"
echo "  skill 链接:"
ls -1d "$HOME/.codebuddy/skills"/ipip-* 2>/dev/null | sed 's#^#    #' || echo "    无 ipip-* skill 软链"
echo "  宿主机基线:"
printf "  %-8s " "python3"; command -v python3 >/dev/null 2>&1 && echo "OK ($(python3 --version 2>&1))" || echo "缺失"
printf "  %-8s " "venv314"; [ -x "$REPO_ROOT/.venv314/bin/python" ] && echo "OK ($("$REPO_ROOT/.venv314/bin/python" --version 2>&1))" || echo "未创建（重跑本脚本；SKIP_DEPS=1 时只会建空 venv）"
printf "  %-8s " "redis"; \
  if command -v redis-cli >/dev/null 2>&1 && [ "$(redis-cli ping 2>/dev/null)" = "PONG" ]; then \
    echo "OK (可达)"; \
  elif command -v redis-server >/dev/null 2>&1; then \
    echo "已装但未启动（跑 make test 时门禁会自动拉起）"; \
  else \
    echo "缺失"; \
  fi
echo
echo "完成。新开交互 shell（bash/zsh）后生效；当前 shell 执行："
echo "  source ~/.zshrc   # 或 source ~/.bashrc"
echo "用法：fs 'regex' | fs -F 'literal' | fspy 'def ' | ff name | fh"
