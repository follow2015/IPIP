#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
应用启动脚本

仅限本地开发使用。生产环境请使用 gunicorn 或 uwsgi。
"""
import os
import sys
from app import create_app

env = os.getenv('FLASK_ENV', 'development')

app = create_app(env)

if __name__ == '__main__':
    debug = env == 'development'
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '127.0.0.1')  # 默认仅监听本地回环

    if debug and host == '0.0.0.0':
        print("FATAL: debug=True + host=0.0.0.0 is forbidden (Werkzeug RCE risk)")
        print("Use '127.0.0.1' for local dev, or gunicorn for production")
        sys.exit(1)

    print(f"启动Flask应用（仅限开发环境）...")
    print(f"环境: {env}")
    print(f"调试模式: {debug}")
    print(f"监听地址: {host}:{port}")

    app.run(
        host=host,
        port=port,
        debug=debug
    )
