"""
数据库初始化模块
================

负责创建 SQLAlchemy 实例、配置数据库连接、以及提供数据库初始化函数。

使用 SQLite 作为本地轻量级数据库，文件存储在 data/ 目录下。
后续迁移到 VPS 时只需修改 SQLALCHEMY_DATABASE_URI 即可切换数据库。
"""

import os
from flask_sqlalchemy import SQLAlchemy

# 全局 SQLAlchemy 实例（在 app.py 中通过 init_app 绑定 Flask 应用）
db = SQLAlchemy()


def get_database_uri() -> str:
    """
    获取数据库连接 URI。

    默认使用 SQLite，数据文件存放在项目根目录的 data/ 文件夹中。
    可以通过环境变量 DATABASE_URL 覆盖（用于 VPS 部署时切换 PostgreSQL 等）。

    Returns:
        str: SQLAlchemy 数据库连接 URI
    """
    # 获取项目根目录（backend/ 的上一级）
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 确保 data 目录存在
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    # 默认使用 SQLite
    default_db_path = os.path.join(data_dir, "adspower_manager.db")
    return os.environ.get("DATABASE_URL", f"sqlite:///{default_db_path}")


def init_db(app):
    """
    将 Flask 应用绑定到 SQLAlchemy 并在应用上下文中创建所有表。

    Args:
        app: Flask 应用实例
    """
    # 配置数据库连接
    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # 初始化 SQLAlchemy
    db.init_app(app)
    # 在应用上下文中创建所有表
    with app.app_context():
        db.create_all()
