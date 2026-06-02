"""
认证与权限管理路由
================

提供：
1. 登录 / 登出（登录时注入页面权限到 session）
2. login_required 装饰器（会话保护）
3. 用户管理与权限分配 CRUD（仅 admin）
4. 首次启动时自动创建 admin 账号
"""

import json
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from loguru import logger

from backend.models import db, User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# 所有可分配的页面权限
ALL_PERMISSIONS = [
    {"key": "dashboard",    "label": "总览",       "icon": "📊"},
    {"key": "environments", "label": "环境管理",    "icon": "🌐"},
    {"key": "proxy",        "label": "代理管理",    "icon": "🔌"},
    {"key": "videos",       "label": "视频管理",    "icon": "🎬"},
    {"key": "config",       "label": "配置管理",    "icon": "⚙️"},
    {"key": "logs",         "label": "日志查看",    "icon": "📋"},
    {"key": "scripts",      "label": "脚本管理",    "icon": "🤖"},
    {"key": "executions",   "label": "执行状态",    "icon": "📈"},
    {"key": "users",        "label": "权限配置",    "icon": "👥"},
]


def _parse_permissions(user: User) -> list:
    """解析用户的权限 JSON 字符串为列表。"""
    try:
        perms = json.loads(user.permissions) if user.permissions else []
        return perms if isinstance(perms, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _user_has_permission(perm_key: str) -> bool:
    """
    检查当前登录用户是否有指定页面权限。
    admin 拥有全部权限。
    """
    if session.get("role") == "admin":
        return True
    user_perms = session.get("permissions", [])
    return perm_key in user_perms


# ============================================================
# 登录保护装饰器
# ============================================================

def login_required(f):
    """登录保护装饰器。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"code": -1, "data": None, "msg": "未登录，请先登录"}), 401
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """管理员权限装饰器。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"code": -1, "data": None, "msg": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated


# ============================================================
# 登录 / 登出
# ============================================================

@auth_bp.route("/login", methods=["GET"])
def login_page():
    """登录页面"""
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    """处理登录请求"""
    data = request.get_json()
    if not data:
        return jsonify({"code": -1, "msg": "请求体为空"})

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"code": -1, "msg": "用户名和密码不能为空"})

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"code": -1, "msg": "用户名或密码错误"})

    if not user.is_active:
        return jsonify({"code": -1, "msg": "账号已被禁用，请联系管理员"})

    if not check_password_hash(user.password_hash, password):
        return jsonify({"code": -1, "msg": "用户名或密码错误"})

    # 解析权限
    user_permissions = _parse_permissions(user)

    # 登录成功，写入 session
    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    session["permissions"] = user_permissions  # 页面权限列表
    session.permanent = True

    logger.info(f"用户 {username} (角色: {user.role}, 权限: {user_permissions}) 登录成功")
    return jsonify({
        "code": 0,
        "data": {
            "username": user.username,
            "role": user.role,
            "permissions": user_permissions,
        },
        "msg": "登录成功",
    })


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """登出"""
    username = session.get("username", "unknown")
    session.clear()
    logger.info(f"用户 {username} 登出")
    return jsonify({"code": 0, "msg": "已登出"})


@auth_bp.route("/me", methods=["GET"])
@login_required
def current_user():
    """获取当前登录用户信息（含权限）"""
    return jsonify({
        "code": 0,
        "data": {
            "user_id": session.get("user_id"),
            "username": session.get("username"),
            "role": session.get("role"),
            "permissions": session.get("permissions", []),
        },
        "msg": "success",
    })


# ============================================================
# 用户管理与权限分配（仅 admin）
# ============================================================

@auth_bp.route("/users", methods=["GET"])
@login_required
@admin_required
def list_users():
    """获取所有用户列表（仅 admin），含权限信息"""
    users = User.query.order_by(User.id).all()
    return jsonify({
        "code": 0,
        "data": [{
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "permissions": _parse_permissions(u),
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        } for u in users],
        "msg": "success",
    })


@auth_bp.route("/users", methods=["POST"])
@login_required
@admin_required
def create_user():
    """
    创建子账号并分配权限（仅 admin）。

    POST /auth/users
    Body: {
        "username": "子账号名",
        "password": "密码",
        "permissions": ["dashboard", "proxy", "logs"]   // 允许访问的页面列表
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"code": -1, "msg": "请求体为空"})

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or len(username) < 2:
        return jsonify({"code": -1, "msg": "用户名至少2个字符"})
    if not password or len(password) < 4:
        return jsonify({"code": -1, "msg": "密码至少4个字符"})

    existing = User.query.filter_by(username=username).first()
    if existing:
        return jsonify({"code": -1, "msg": f"用户名 {username} 已存在"})

    # 解析权限（前端传来的是数组）
    perms = data.get("permissions", [])
    if not isinstance(perms, list):
        perms = []
    # 验证权限 key 合法性
    valid_keys = {p["key"] for p in ALL_PERMISSIONS}
    perms = [p for p in perms if p in valid_keys]

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role="user",
        permissions=json.dumps(perms, ensure_ascii=False),
        is_active=1,
    )
    db.session.add(user)
    db.session.commit()

    logger.info(f"管理员 {session.get('username')} 创建了子账号: {username}，权限: {perms}")
    return jsonify({
        "code": 0,
        "data": {"id": user.id, "username": user.username, "permissions": perms},
        "msg": f"子账号 {username} 创建成功",
    })


@auth_bp.route("/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
def update_user(user_id):
    """
    更新用户信息和权限（仅 admin）。

    PUT /auth/users/{id}
    Body: {
        "password": "新密码（可选）",
        "is_active": 1,
        "permissions": ["dashboard", "proxy"]
    }
    """
    user = User.query.get(user_id)
    if not user:
        return jsonify({"code": -1, "msg": "用户不存在"})

    if user.id == session.get("user_id"):
        return jsonify({"code": -1, "msg": "不能修改自己的账号"})

    data = request.get_json()
    if not data:
        return jsonify({"code": -1, "msg": "请求体为空"})

    if "password" in data and data["password"]:
        user.password_hash = generate_password_hash(data["password"])

    if "is_active" in data:
        user.is_active = int(data["is_active"])

    if "role" in data and data["role"] in ("admin", "user"):
        user.role = data["role"]

    # 更新权限
    if "permissions" in data:
        perms = data["permissions"]
        if isinstance(perms, list):
            valid_keys = {p["key"] for p in ALL_PERMISSIONS}
            perms = [p for p in perms if p in valid_keys]
            user.permissions = json.dumps(perms, ensure_ascii=False)
        else:
            user.permissions = "[]"

    db.session.commit()
    logger.info(f"管理员 {session.get('username')} 更新了用户 {user.username} 的权限")

    return jsonify({
        "code": 0,
        "data": {"permissions": _parse_permissions(user)},
        "msg": f"用户 {user.username} 已更新",
    })


@auth_bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(user_id):
    """删除用户（仅 admin，不能删除自己）"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"code": -1, "msg": "用户不存在"})

    if user.id == session.get("user_id"):
        return jsonify({"code": -1, "msg": "不能删除自己的账号"})

    if user.role == "admin":
        return jsonify({"code": -1, "msg": "不能删除管理员账号"})

    username = user.username
    db.session.delete(user)
    db.session.commit()
    logger.info(f"管理员 {session.get('username')} 删除了用户 {username}")
    return jsonify({"code": 0, "msg": f"用户 {username} 已删除"})


# ============================================================
# 默认 admin 初始化
# ============================================================

def seed_admin(app):
    """
    初始化默认 admin 账号。
    用户名: admin  密码: admin123
    """
    with app.app_context():
        db.create_all()
        existing = User.query.first()
        if existing:
            return

        admin = User(
            username="admin",
            password_hash=generate_password_hash("admin123"),
            role="admin",
            permissions="[]",
            is_active=1,
        )
        db.session.add(admin)
        db.session.commit()
        logger.warning("===== 默认 admin 账号已创建 =====")
        logger.warning("  用户名: admin")
        logger.warning("  密码:   admin123")
        logger.warning("  请立即登录后台并修改密码！")
