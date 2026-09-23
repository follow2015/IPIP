#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP-4 · 生产配置离线预检（不启动服务）

存量部署在 `systemctl restart ipip.target` 前运行本脚本，即可在不打断
服务的情况下知道：**这次重启会不会被打挂、缺哪些项、每项怎么补**。
背景：A-P2-4 给 ProductionConfig.validate 加了多处 fail-fast 硬校验
（/metrics 暴露面、双密钥相同、LDAP CA、占位符密钥等）——不带平滑路径
的话，存量部署升级后重启即 5 个单元连环失败。

用法：
    python3 scripts/precheck_prod_config.py [--env-file PATH]...

- --env-file 可重复给出；后加载者覆盖先加载者，并覆盖继承自 shell 的
  同名变量。缺省时依次尝试 deploy/systemd/ipip.env、.env（存在哪个用哪个）。
- 仓库 .env 的自动加载（load_dotenv）在预检进程内**被禁用**：
  预检判据必须只来自显式给定的 env 文件与环境，否则开发机本机 .env
  会静默补齐缺失项，把"该报的缺陷"洗成"通过"。
- 退出码：0 = 通过；1 = 存在配置缺陷；2 = 用法/文件错误。
- 本脚本只读：不写任何文件、不连数据库/Redis、不监听端口、不启动服务。

仅用标准库，可在部署机系统 Python 下直接运行。
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

_SUGGESTIONS = {
    "REQUIRED_SECRETS": "SECRET_KEY/JWT_SECRET_KEY/SWITCH_SECRET_KEY 各自执行 `openssl rand -hex 32` 生成；⚠️ SWITCH_SECRET_KEY 一旦丢失，switch_credentials 密文永久不可解",
    "CORS_ORIGINS": "CORS_ORIGINS=https://你的前端域名（逗号分隔多个，不要用 *）",
    "DEBUG_DISABLED": "删除 FLASK_DEBUG=true 或设 FLASK_DEBUG=false",
    "METRICS_EXPOSURE": "METRICS_TOKEN=<openssl rand -hex 32> 或 METRICS_ALLOWED_IPS=<Prometheus 所在网段>；不要该端点则 METRICS_ENABLED=false",
    "SECRET_KEY_DUPLICATE": "两把密钥分别执行 `openssl rand -hex 32`；更换 SECRET_KEY 会使现有会话失效（用户需重新登录）",
    "LDAP_CA_FILE": "LDAP_CA_FILE=/etc/ssl/certs/ca-certificates.crt（或指向自家企业 CA 的 PEM 路径）",
    "DEPLOY_LOCATION": "部署到 /opt/ipip（scripts/install.sh 的固定安装目标），或将单元模板 ProtectHome=true 改为 read-only",
    "BASE_CONFIG": "基础配置（端口/必需项）校验失败，见上方消息",
}


def parse_env_file(path):
    """极简 KEY=VALUE 解析，兼容 systemd EnvironmentFile 语法。

    与 systemd 一致的取子集：忽略空行/#注释、值取到行尾并去掉首尾空白、
    去掉一层成对引号；不支持变量展开与命令替换（也不需要）。
    """
    entries = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                print(f"⚠️  {path}:{lineno} 无法解析（缺少 =）：{line}", file=sys.stderr)
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if not key:
                print(f"⚠️  {path}:{lineno} 空变量名", file=sys.stderr)
                continue
            entries[key] = value
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="生产配置离线预检：不启动服务，逐项列出配置缺陷与建议值"
    )
    parser.add_argument(
        "--env-file", action="append", default=[],
        help="env 文件路径（可重复，后者覆盖前者）；缺省依次尝试 deploy/systemd/ipip.env、.env",
    )
    args = parser.parse_args(argv)

    env_files = list(args.env_file)
    if not env_files:
        for candidate in ("deploy/systemd/ipip.env", ".env"):
            path = os.path.join(REPO_ROOT, candidate)
            if os.path.isfile(path):
                env_files.append(path)
                break
        if not env_files:
            print("未找到 env 文件：请用 --env-file 显式指定（如 --env-file /etc/ipip/ipip.env）",
                  file=sys.stderr)
            return 2

    loaded_from = []
    for path in env_files:
        if not os.path.isfile(path):
            print(f"env 文件不存在：{path}", file=sys.stderr)
            return 2
        for key, value in parse_env_file(path).items():
            os.environ[key] = value  # 文件是预检判据的唯一真源：覆盖继承值
        loaded_from.append(path)

    os.environ["IPIP_PRECHECK_SKIP_DOTENV"] = "1"
    os.environ.setdefault("FLASK_ENV", "production")

    from config import ProductionConfig, _assert_deploy_location

    violations = []
    try:
        _assert_deploy_location()
    except RuntimeError as exc:
        violations.append(("DEPLOY_LOCATION", str(exc)))

    print("════════ 生产配置离线预检 ════════")
    print(f"env 文件：{', '.join(loaded_from)}")
    print(f"配置类：ProductionConfig（FLASK_ENV=production）")
    print()
    for check_id, message in ProductionConfig.collect_violations():
        violations.append((check_id, message))

    if violations:
        print(f"发现 {len(violations)} 项配置缺陷（重启将被 fail-fast 拒绝）：")
        print()
        for check_id, message in violations:
            print(f"  ✗ [{check_id}] {message}")
            suggestion = _SUGGESTIONS.get(check_id)
            if suggestion:
                print(f"      建议：{suggestion}")
            print()
        print(f"结果：{len(violations)} 项缺陷，退出码 1。补全后重跑本脚本至退出 0 再执行 systemctl restart。")
        return 1

    print("✓ 全部检查通过。本次 systemctl restart 不会被配置校验打挂。")
    print("  （注意：预检只覆盖配置面，不覆盖数据库迁移状态。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
