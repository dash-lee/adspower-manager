"""
环境管理 API 路由
================

提供环境管理操作的 REST API：
- 初始化检查
- 环境列表
- 创建环境
- 删除环境
- 更新环境
- 浏览器启动/停止
- 任务队列管理
"""

import json
import datetime
from flask import Blueprint, request, jsonify, current_app
from backend.models import db, TaskQueue
from backend.services.adspower_client import AdsPowerClient
from backend.services.env_manager import EnvManager

env_bp = Blueprint("env", __name__, url_prefix="/api/env")


def _get_manager() -> EnvManager:
    """
    从 Flask 应用上下文中获取 EnvManager 实例。

    Returns:
        EnvManager 实例
    """
    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    return EnvManager(client)


# ============================================================
# 初始化检查
# ============================================================

@env_bp.route("/check", methods=["GET"])
def init_check():
    """
    执行系统初始化检查。

    GET /api/env/check

    检查项：
    1. AdsPower API 状态
    2. 保留环境与实际的对比
    3. 可清理环境的统计
    """
    manager = _get_manager()
    result = manager.init_check()
    return jsonify({"code": 0, "data": result, "msg": "success"})


# ============================================================
# 环境列表
# ============================================================

@env_bp.route("/list", methods=["GET"])
def list_profiles():
    """
    获取 AdsPower 中的环境列表。

    GET /api/env/list

    Query params:
        group_id: 分组ID过滤
        page:     页码（默认1）
        limit:    每页数量（默认50）
    """
    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    group_id = request.args.get("group_id")
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 50))

    resp = client.list_profiles(group_id=group_id, page=page, limit=limit)
    return jsonify(resp)


@env_bp.route("/list/all", methods=["GET"])
def list_all_profiles():
    """
    获取 AdsPower 中所有环境（自动分页）。

    GET /api/env/list/all
    """
    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    profiles = client.get_all_profiles()
    return jsonify({
        "code": 0,
        "data": {"list": profiles, "total": len(profiles)},
        "msg": "success",
    })


# ============================================================
# 创建环境
# ============================================================

@env_bp.route("/create", methods=["POST"])
def create_environment():
    """
    创建新环境。

    POST /api/env/create
    Body: {
        "count": 1,                    // 创建数量（可选，默认1）
        "env_name": "MyEnv",           // 环境名称前缀（会自动加序号）
        "group_id": "0",               // 分组ID（默认"0"）
        "proxy_id": "xxx",             // 代理ID（可选，不传则随机选择）
        "open_url": "https://...",     // 初始打开URL（可选）
        "use_queue": false             // 是否加入任务队列（可选，默认false直接执行）
    }
    """
    data = request.get_json() or {}
    count = data.get("count", 1)
    group_id = str(data.get("group_id", "0"))
    proxy_id = data.get("proxy_id")
    open_url = data.get("open_url")
    env_name_prefix = data.get("env_name", f"Auto")
    use_queue = data.get("use_queue", False)

    manager = _get_manager()

    if use_queue:
        # 加入任务队列
        results = []
        for i in range(count):
            params = {
                "env_name": f"{env_name_prefix}_{i+1}",
                "group_id": group_id,
                "proxy_id": proxy_id,
                "open_url": open_url,
            }
            task = TaskQueue(
                task_type="create_env",
                params=json.dumps(params),
                status="pending",
            )
            db.session.add(task)
            results.append({"task_id": None, "env_name": params["env_name"]})
        db.session.commit()
        # 刷新获取实际任务ID
        for i, t in enumerate(
            TaskQueue.query.filter_by(task_type="create_env", status="pending")
            .order_by(TaskQueue.id.desc())
            .limit(count)
            .all()
        ):
            results[i]["task_id"] = t.id

        return jsonify({
            "code": 0,
            "data": {"results": results, "queued": True},
            "msg": f"{count}个创建任务已加入队列",
        })
    else:
        # 直接执行
        results = []
        for i in range(count):
            env_name = f"{env_name_prefix}_{i+1}" if count > 1 else env_name_prefix
            result = manager.create_environment(
                env_name=env_name,
                group_id=group_id,
                proxy_id=proxy_id,
                open_url=open_url,
            )
            results.append(result)

        success_count = sum(1 for r in results if r["success"])
        return jsonify({
            "code": 0 if success_count > 0 else -1,
            "data": {"results": results, "success_count": success_count, "total": count},
            "msg": f"创建完成: {success_count}/{count} 成功",
        })


# ============================================================
# 删除环境
# ============================================================

@env_bp.route("/delete", methods=["POST"])
def delete_environments():
    """
    批量删除环境。

    POST /api/env/delete
    Body: {
        "profile_ids": ["id1", "id2"],  // 环境ID列表（必填）
        "force": false,                  // 是否强制删除（包括保留环境）
        "use_queue": false               // 是否加入任务队列
    }
    """
    data = request.get_json() or {}
    profile_ids = data.get("profile_ids", [])
    force = data.get("force", False)
    use_queue = data.get("use_queue", False)

    if not profile_ids:
        return jsonify({"code": -1, "data": None, "msg": "请提供要删除的环境ID列表"})

    manager = _get_manager()

    if use_queue:
        task = TaskQueue(
            task_type="delete_env",
            params=json.dumps({"profile_ids": profile_ids, "force": force}),
            status="pending",
        )
        db.session.add(task)
        db.session.commit()
        return jsonify({
            "code": 0,
            "data": {"task_id": task.id},
            "msg": f"删除任务已加入队列（{len(profile_ids)}个环境）",
        })
    else:
        result = manager.delete_environments(profile_ids, force=force)
        return jsonify({"code": 0 if result["success"] else -1, "data": result, "msg": "删除完成"})


# ============================================================
# 更新环境
# ============================================================

@env_bp.route("/update", methods=["POST"])
def update_environment():
    """
    更新环境配置。

    POST /api/env/update
    Body: {
        "profile_id": "xxx",          // 环境ID（必填）
        "fingerprint_updates": {       // 要更新的指纹参数
            "screen_resolution": "1920_1080",
            "hardware_concurrency": "8"
        },
        "proxy_id": "xxx",            // 新代理ID（可选）
        "name": "新名称",             // 新名称（可选）
        "remark": "备注"              // 新备注（可选）
    }
    """
    data = request.get_json() or {}
    profile_id = data.get("profile_id")
    if not profile_id:
        return jsonify({"code": -1, "data": None, "msg": "缺少必填参数 profile_id"})

    manager = _get_manager()
    result = manager.update_environment(
        profile_id=profile_id,
        fingerprint_updates=data.get("fingerprint_updates"),
        proxy_id=data.get("proxy_id"),
        name=data.get("name"),
        remark=data.get("remark"),
    )
    return jsonify({"code": 0 if result["success"] else -1, "data": result, "msg": "更新完成"})


# ============================================================
# 浏览器启动/停止
# ============================================================

@env_bp.route("/browser/start", methods=["POST"])
def start_browser():
    """
    启动浏览器环境。

    POST /api/env/browser/start
    Body: {
        "profile_id": "xxx",
        "headless": 0,
        "proxy_detection": 1
    }
    """
    data = request.get_json() or {}
    profile_id = data.get("profile_id")
    if not profile_id:
        return jsonify({"code": -1, "data": None, "msg": "缺少必填参数 profile_id"})

    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    resp = client.start_browser(
        profile_id=profile_id,
        headless=int(data.get("headless", 0)),
        proxy_detection=int(data.get("proxy_detection", 1)),
    )
    return jsonify(resp)


@env_bp.route("/browser/stop", methods=["POST"])
def stop_browser():
    """
    关闭浏览器环境。

    POST /api/env/browser/stop
    Body: {"profile_id": "xxx"}
    """
    data = request.get_json() or {}
    profile_id = data.get("profile_id")
    if not profile_id:
        return jsonify({"code": -1, "data": None, "msg": "缺少必填参数 profile_id"})

    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    resp = client.stop_browser(profile_id)
    return jsonify(resp)


@env_bp.route("/browser/stop-all", methods=["POST"])
def stop_all_browsers():
    """
    关闭所有浏览器环境。

    POST /api/env/browser/stop-all
    """
    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    resp = client.stop_all_browsers()
    return jsonify(resp)


@env_bp.route("/browser/active", methods=["GET"])
def check_active():
    """
    检查环境启动状态。

    GET /api/env/browser/active?profile_id=xxx
    """
    profile_id = request.args.get("profile_id")
    if not profile_id:
        return jsonify({"code": -1, "data": None, "msg": "缺少参数 profile_id"})

    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    resp = client.check_active(profile_id)
    return jsonify(resp)


@env_bp.route("/browser/local-active", methods=["GET"])
def get_local_active():
    """
    获取当前设备所有已启动浏览器。

    GET /api/env/browser/local-active
    """
    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
    resp = client.get_local_active()
    return jsonify(resp)


# ============================================================
# 任务队列
# ============================================================

@env_bp.route("/tasks", methods=["GET"])
def list_tasks():
    """
    获取任务队列。

    GET /api/env/tasks

    Query params:
        status: 过滤状态（pending/running/completed/failed）
        limit:  返回数量（默认50）
    """
    status_filter = request.args.get("status")
    limit = int(request.args.get("limit", 50))

    query = TaskQueue.query.order_by(TaskQueue.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)

    tasks = query.limit(limit).all()
    return jsonify({
        "code": 0,
        "data": [
            {
                "id": t.id,
                "task_type": t.task_type,
                "params": t.params,
                "status": t.status,
                "priority": t.priority,
                "result_msg": t.result_msg,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ],
        "msg": "success",
    })


@env_bp.route("/tasks/<int:task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    """
    取消任务。

    POST /api/env/tasks/{id}/cancel
    """
    task = TaskQueue.query.get(task_id)
    if not task:
        return jsonify({"code": -1, "data": None, "msg": "任务不存在"})
    if task.status not in ("pending", "running"):
        return jsonify({"code": -1, "data": None, "msg": f"任务状态为 {task.status}，无法取消"})

    task.status = "cancelled"
    task.completed_at = datetime.datetime.utcnow()
    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "任务已取消"})


@env_bp.route("/tasks/process", methods=["POST"])
def process_tasks():
    """
    手动触发任务处理。

    POST /api/env/tasks/process
    """
    manager = _get_manager()
    count = manager.process_pending_tasks()
    return jsonify({"code": 0, "data": {"processed": count}, "msg": f"已处理 {count} 个任务"})
