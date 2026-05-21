"""
Ads Manager 环境管理后端 - 主应用
================================

Flask Web 应用，提供：
- 后台管理 API（RESTful）
- 管理面板前端页面
- 定时任务调度
- 数据库管理
- 登录认证 & 权限管理

启动方式：
    python run.py
    或
    cd backend && python app.py
"""

import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, session
from flask_cors import CORS
from loguru import logger
from datetime import timedelta

from backend.database import db, init_db
from backend.routes.config_routes import config_bp
from backend.routes.env_routes import env_bp
from backend.routes.log_routes import log_bp
from backend.routes.auth_routes import auth_bp, login_required, admin_required, seed_admin
from backend.services.adspower_client import AdsPowerClient
from backend.services.scheduler import TaskScheduler
from backend.models import GeneralConfig


def _get_api_config() -> tuple:
    """
    从数据库读取 AdsPower API 配置（即时读取）。

    Returns:
        (api_url: str, api_key: str)
    """
    api_url = "http://local.adspower.net:50325"
    api_key = ""
    try:
        url_cfg = GeneralConfig.query.filter_by(config_key="adspower_api_url").first()
        key_cfg = GeneralConfig.query.filter_by(config_key="adspower_api_key").first()
        if url_cfg and url_cfg.config_value:
            api_url = url_cfg.config_value
        if key_cfg and key_cfg.config_value:
            api_key = key_cfg.config_value
    except Exception:
        pass
    return api_url, api_key


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
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)  # session 8小时有效

    # ---- CORS 配置 ----
    CORS(app)  # 允许跨域（开发阶段全开，生产环境应限制）

    # ---- 初始化数据库 ----
    init_db(app)

    # ---- 初始化 AdsPower 客户端 ----
    api_url, api_key = _get_api_config()
    client = AdsPowerClient(api_url=api_url, api_key=api_key)
    app.config["ADSPOWER_CLIENT"] = client

    # ---- 初始化定时调度器 ----
    scheduler = TaskScheduler(client)
    app.config["SCHEDULER"] = scheduler

    # ---- 注册蓝图 ----
    app.register_blueprint(auth_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(env_bp)
    app.register_blueprint(log_bp)

    # ---- 全局登录 + 权限保护 ----
    # 页面路径 → 权限 key 映射
    PAGE_PERM_MAP = {
        "/dashboard": "dashboard",
        "/environments": "environments",
        "/proxy": "proxy",
        "/config": "config",
        "/logs": "logs",
        "/users": "users",
    }

    @app.before_request
    def check_login_and_permission():
        """全局登录 + 权限检查。"""
        from flask import request, session as flask_session

        # 允许未登录访问的路径
        if request.path.startswith("/auth/login") or request.path.startswith("/static/"):
            return None

        # 登录检查
        if "user_id" not in flask_session:
            if request.path.startswith("/api/"):
                return jsonify({"code": -1, "data": None, "msg": "未登录，请先登录"}), 401
            from flask import redirect as _redirect
            return _redirect(url_for("auth.login_page"))

        # 权限检查：admin 跳过，非 admin 按页面权限校验
        if flask_session.get("role") != "admin":
            # 只检查页面路由，API 路由不在此处检查（API 有自己的装饰器）
            if not request.path.startswith("/api/") and not request.path.startswith("/auth/"):
                # 匹配页面权限
                has_access = False
                for page_path, perm_key in PAGE_PERM_MAP.items():
                    if request.path == page_path or request.path.startswith(page_path + "?"):
                        if perm_key in flask_session.get("permissions", []):
                            has_access = True
                        break
                else:
                    # 根路径默认等同于 dashboard
                    if request.path == "/":
                        has_access = "dashboard" in flask_session.get("permissions", [])

                if not has_access:
                    # 页面请求返回友好 HTML 错误
                    if request.path.startswith("/api/"):
                        return jsonify({
                            "code": -1, "data": None,
                            "msg": "您没有访问此页面的权限，请联系管理员",
                        }), 403
                    else:
                        return render_template("error_403.html"), 403

        return None

    # ---- 前端页面路由 ----
    @app.route("/")
    @login_required
    def index():
        """主页 - 重定向到总览"""
        return render_template("dashboard.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        """总览页面"""
        return render_template("dashboard.html")

    @app.route("/config")
    @login_required
    def config_page():
        """配置管理页面"""
        return render_template("config.html")

    @app.route("/environments")
    @login_required
    def environments_page():
        """环境管理页面"""
        return render_template("environments.html")

    @app.route("/proxy")
    @login_required
    def proxy_page():
        """代理管理页面"""
        return render_template("proxy.html")

    @app.route("/logs")
    @login_required
    def logs_page():
        """日志查看页面"""
        return render_template("logs.html")

    @app.route("/users")
    @login_required
    @admin_required
    def users_page():
        """用户管理页面（仅 admin）"""
        return render_template("users.html")

    # ---- 系统 API ----
    @app.route("/api/status", methods=["GET"])
    @login_required
    def api_status():
        """获取系统整体状态"""
        client: AdsPowerClient = app.config["ADSPOWER_CLIENT"]
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        api_url, api_key = _get_api_config()

        return jsonify({
            "code": 0,
            "data": {
                "adspower_api": api_url,
                "adspower_ok": client.check_status(),
                "scheduler_running": scheduler._scheduler.running if scheduler._scheduler else False,
                "scheduler_jobs": scheduler.get_jobs(),
                "current_user": {
                    "username": session.get("username"),
                    "role": session.get("role"),
                },
            },
            "msg": "success",
        })

    @app.route("/api/scheduler/jobs", methods=["GET"])
    @login_required
    def get_scheduler_jobs():
        """获取定时任务列表"""
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        return jsonify({"code": 0, "data": scheduler.get_jobs(), "msg": "success"})

    @app.route("/api/scheduler/pause/<job_id>", methods=["POST"])
    @login_required
    def pause_scheduler_job(job_id):
        """暂停定时任务"""
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        ok = scheduler.pause_job(job_id)
        return jsonify({"code": 0 if ok else -1, "data": None, "msg": "已暂停" if ok else "暂停失败"})

    @app.route("/api/scheduler/resume/<job_id>", methods=["POST"])
    @login_required
    def resume_scheduler_job(job_id):
        """恢复定时任务"""
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        ok = scheduler.resume_job(job_id)
        return jsonify({"code": 0 if ok else -1, "data": None, "msg": "已恢复" if ok else "恢复失败"})

    # ---- 配置即时生效 API ----
    @app.route("/api/config/reload_client", methods=["POST"])
    @login_required
    def reload_client():
        """
        重新加载 AdsPower 客户端配置（API URL / Key 修改后调用）。
        立即用新的配置重建客户端和调度器连接。
        """
        api_url, api_key = _get_api_config()
        new_client = AdsPowerClient(api_url=api_url, api_key=api_key)
        app.config["ADSPOWER_CLIENT"] = new_client

        # 同步更新调度器中的客户端引用
        scheduler: TaskScheduler = app.config["SCHEDULER"]
        scheduler.client = new_client
        scheduler.env_manager.client = new_client

        status = new_client.check_status()
        logger.info(f"AdsPower 客户端已重载: url={api_url}, status={'正常' if status else '异常'}")
        return jsonify({
            "code": 0,
            "data": {"api_ok": status, "api_url": api_url},
            "msg": "客户端配置已重新加载",
        })

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
        # 创建默认 admin 账号（仅在首次启动时）
        seed_admin(app)

        logger.info("===== Ads Manager 环境管理后端启动 =====")
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
