"""
AdsPower 环境管理后端 - 主应用
============================

Flask Web 应用，提供：
- 后台管理 API（RESTful）
- 管理面板前端页面
- 定时任务调度
- 数据库管理

启动方式：
    python run.py
    或
    cd backend && python app.py
"""

import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify
from flask_cors import CORS
from loguru import logger

from backend.database import db, init_db
from backend.routes.config_routes import config_bp
from backend.routes.env_routes import env_bp
from backend.routes.log_routes import log_bp
from backend.services.adspower_client import AdsPowerClient
from backend.services.scheduler import TaskScheduler


def create_app() -> Flask:
    """
    创建并配置 Flask 应用。

    Returns:
        Flask 应用实例
    """
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    # ---- 基础配置 ----
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "adspower-manager-secret-change-me")
    app.config["JSON_AS_ASCII"] = False  # 支持中文 JSON 输出

    # ---- CORS 配置 ----
    CORS(app)  # 允许跨域（开发阶段全开，生产环境应限制）

    # ---- 初始化数据库 ----
    init_db(app)

    # ---- 初始化 AdsPower 客户端 ----
    # 从数据库中读取 API 配置（如果有的话）
    # 默认值在首次运行后可通过后台修改
    api_url = "http://local.adspower.net:50325"
    api_key = ""
    
    # 尝试从数据库读取配置（仅在应用上下文中可用）
    try:
        with app.app_context():
            from backend.models import GeneralConfig
            url_config = GeneralConfig.query.filter_by(config_key="adspower_api_url").first()
            key_config = GeneralConfig.query.filter_by(config_key="adspower_api_key").first()
            if url_config:
                api_url = url_config.config_value
            if key_config:
                api_key = key_config.config_value
    except Exception as e:
        logger.warning(f"从数据库读取配置失败（可能首次启动）: {e}")

    client = AdsPowerClient(api_url=api_url, api_key=api_key)
    app.config["ADSPOWER_CLIENT"] = client

    # ---- 初始化定时调度器 ----
    scheduler = TaskScheduler(client)
    app.config["SCHEDULER"] = scheduler

    # ---- 注册蓝图 ----
    app.register_blueprint(config_bp)
    app.register_blueprint(env_bp)
    app.register_blueprint(log_bp)

    # ---- 前端页面路由 ----
    @app.route("/")
    def index():
        """主页 - 重定向到仪表盘"""
        return render_template("dashboard.html")

    @app.route("/dashboard")
    def dashboard():
        """仪表盘页面"""
        return render_template("dashboard.html")

    @app.route("/config")
    def config_page():
        """配置管理页面"""
        return render_template("config.html")

    @app.route("/environments")
    def environments_page():
        """环境管理页面"""
        return render_template("environments.html")

    @app.route("/logs")
    def logs_page():
        """日志查看页面"""
        return render_template("logs.html")

    # ---- 系统 API ----
    @app.route("/api/status", methods=["GET"])
    def api_status():
        """获取系统整体状态"""
        client: AdsPowerClient = app.config["ADSPOWER_CLIENT"]
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        
        return jsonify({
            "code": 0,
            "data": {
                "adspower_api": api_url,
                "adspower_ok": client.check_status(),
                "scheduler_running": scheduler._scheduler.running if scheduler._scheduler else False,
                "scheduler_jobs": scheduler.get_jobs(),
            },
            "msg": "success",
        })

    @app.route("/api/scheduler/jobs", methods=["GET"])
    def get_scheduler_jobs():
        """获取定时任务列表"""
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        return jsonify({"code": 0, "data": scheduler.get_jobs(), "msg": "success"})

    @app.route("/api/scheduler/pause/<job_id>", methods=["POST"])
    def pause_scheduler_job(job_id):
        """暂停定时任务"""
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        ok = scheduler.pause_job(job_id)
        return jsonify({"code": 0 if ok else -1, "data": None, "msg": "已暂停" if ok else "暂停失败"})

    @app.route("/api/scheduler/resume/<job_id>", methods=["POST"])
    def resume_scheduler_job(job_id):
        """恢复定时任务"""
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        ok = scheduler.resume_job(job_id)
        return jsonify({"code": 0 if ok else -1, "data": None, "msg": "已恢复" if ok else "恢复失败"})

    # ---- 错误处理 ----
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"code": -1, "data": None, "msg": "路由不存在"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"服务器错误: {e}")
        return jsonify({"code": -1, "data": None, "msg": "服务器内部错误"}), 500

    # ---- 启动时初始化 ----
    with app.app_context():
        logger.info("===== AdsPower 环境管理后端启动 =====")
        logger.info(f"AdsPower API 地址: {api_url}")
        scheduler.start()

    return app


def main():
    """直接运行 app.py 时的入口"""
    # 配置 loguru 日志
    logger.add(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app.log"),
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    )

    app = create_app()
    # 从环境变量读取端口，默认 5000
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info(f"Flask 应用启动在 http://{host}:{port}")
    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    finally:
        # 应用退出时停止调度器
        scheduler = app.config.get("SCHEDULER")
        if scheduler:
            scheduler.stop()


if __name__ == "__main__":
    main()
