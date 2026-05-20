#!/usr/bin/env python3
"""
AdsPower 环境管理后端 - 启动脚本
===============================

用法:
    python run.py              # 默认在 0.0.0.0:5000 启动
    python run.py --port 8080  # 指定端口
    python run.py --host 127.0.0.1 --port 5001  # 指定地址和端口

环境变量:
    PORT=5000          # 服务端口
    HOST=0.0.0.0       # 绑定地址
    DATABASE_URL=...   # 数据库连接（默认 SQLite）
    SECRET_KEY=...     # Flask 密钥
"""

import os
import sys
import argparse

# 确保项目根目录在 Python 路径中
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

from loguru import logger


def setup_logging():
    """
    配置日志输出。

    日志同时输出到：
    1. 控制台（终端）
    2. 文件 data/app.log（自动轮转，保留7天）
    """
    log_dir = os.path.join(project_dir, "data")
    os.makedirs(log_dir, exist_ok=True)

    # 移除默认 handler
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
               "<cyan>{name}</cyan> | <level>{message}</level>",
    )

    # 文件输出
    logger.add(
        os.path.join(log_dir, "app.log"),
        rotation="10 MB",      # 每 10MB 轮转
        retention="7 days",    # 保留 7 天
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
               "{name}:{function}:{line} | {message}",
    )


def main():
    parser = argparse.ArgumentParser(description="AdsPower 环境管理后端")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址（默认: 0.0.0.0）")
    parser.add_argument("--port", type=int, default=5000, help="服务端口（默认: 5000）")
    parser.add_argument("--debug", action="store_true", help="开启调试模式")
    args = parser.parse_args()

    # 环境变量覆盖命令行参数
    host = os.environ.get("HOST", args.host)
    port = int(os.environ.get("PORT", args.port))

    setup_logging()

    from backend.app import create_app
    app = create_app()

    logger.info(f"=" * 60)
    logger.info(f"   AdsPower 环境管理后端")
    logger.info(f"   地址: http://{host}:{port}")
    logger.info(f"   管理面板: http://{host}:{port}/dashboard")
    logger.info(f"=" * 60)

    scheduler = app.config.get("SCHEDULER")
    try:
        app.run(host=host, port=port, debug=args.debug, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    finally:
        if scheduler:
            scheduler.stop()
        logger.info("服务已停止")


if __name__ == "__main__":
    main()
