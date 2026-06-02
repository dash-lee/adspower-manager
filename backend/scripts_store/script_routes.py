"""
脚本管理 API 路由
=================

提供内置脚本的列表、查看、执行、日志查询等 REST API。
支持标准脚本和组合脚本两种类型。

所有接口返回格式：{"code": 0, "data": ..., "msg": "success"}
"""

from flask import Blueprint, request, jsonify, current_app
from loguru import logger

from backend.models import db, ExecutionStatus
from backend.scripts_store.script_manager import ScriptManager

scripts_bp = Blueprint("scripts", __name__, url_prefix="/api/scripts")


def _get_manager() -> ScriptManager:
    """从应用上下文中获取 ScriptManager 实例。"""
    return current_app.config["SCRIPT_MANAGER"]


# ============================================================
# 脚本列表与信息查询
# ============================================================

@scripts_bp.route("/list", methods=["GET"])
def list_scripts():
    """
    获取可用脚本列表。

    GET /api/scripts/list?type=standard
    GET /api/scripts/list?type=combo

    Query params:
        type: 脚本类型（standard / combo，默认 standard）

    Returns:
        {"code": 0, "data": [...], "msg": "success"}
    """
    script_type = request.args.get("type", "standard")
    manager = _get_manager()
    scripts = manager.list_scripts(script_type=script_type)
    return jsonify({"code": 0, "data": scripts, "msg": "success"})


@scripts_bp.route("/<script_name>/info", methods=["GET"])
def get_script_info(script_name):
    """
    获取单个脚本的详细信息。

    GET /api/scripts/{script_name}/info

    Args:
        script_name: 脚本名称

    Returns:
        {"code": 0, "data": {...}}
    """
    manager = _get_manager()
    info = manager.get_script_info(script_name)
    if not info:
        return jsonify({"code": -1, "data": None, "msg": f"脚本 {script_name} 不存在"})
    return jsonify({"code": 0, "data": info, "msg": "success"})


# ============================================================
# 标准脚本执行
# ============================================================

@scripts_bp.route("/<script_name>/run", methods=["POST"])
def run_script(script_name):
    """
    执行指定脚本。

    POST /api/scripts/{script_name}/run

    Body:
        {
            "params": {...},       // 脚本参数，根据脚本定义
            "task_name": "..."     // 可选，任务名称
        }

    Returns:
        {"code": 0, "data": {"execution_id": "...", "results": [...]}, "msg": "..."}
    """
    manager = _get_manager()
    info = manager.get_script_info(script_name)
    if not info:
        return jsonify({"code": -1, "data": None, "msg": f"脚本 {script_name} 不存在"})

    data = request.get_json() or {}
    params = data.get("params", {})
    task_name = data.get("task_name", "")

    logger.info(f"执行脚本: {script_name}, 任务: {task_name or '未命名'}, 参数: {params}")

    result = manager.execute_script(script_name, params, task_name)

    if result.get("success"):
        return jsonify({
            "code": 0,
            "data": {
                "execution_id": result["execution_id"],
                "results": result.get("results", []),
                "success_count": result.get("success_count", 0),
                "total": result.get("total", 0),
            },
            "msg": f"执行完成: {result.get('success_count', 0)}/{result.get('total', 0)} 成功",
        })
    else:
        return jsonify({
            "code": -1,
            "data": {
                "execution_id": result["execution_id"],
                "results": result.get("results", []),
                "success_count": result.get("success_count", 0),
                "total": result.get("total", 0),
            },
            "msg": result.get("error") or f"执行失败: 0/{result.get('total', 0)} 成功",
        })


# ============================================================
# 执行日志查询
# ============================================================

@scripts_bp.route("/log/<execution_id>", methods=["GET"])
def get_execution_log(execution_id):
    """
    获取指定执行批次的详细步骤日志。

    GET /api/scripts/log/{execution_id}

    Returns:
        {"code": 0, "data": [步骤日志列表], "msg": "success"}
    """
    manager = _get_manager()
    logs = manager.get_execution_log(execution_id)
    return jsonify({"code": 0, "data": logs, "msg": "success"})


# ============================================================
# 执行状态查询
# ============================================================

@scripts_bp.route("/executions", methods=["GET"])
def list_executions():
    """
    获取所有执行批次列表（分页）。

    GET /api/scripts/executions?page=1&limit=20&type=standard

    Query params:
        page:  页码（默认1）
        limit: 每页数量（默认20）
        type:  脚本类型（standard / combo，可选）

    Returns:
        {"code": 0, "data": {"batches": [...], "total": ..., "page": ..., "limit": ...}}
    """
    manager = _get_manager()
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    script_type = request.args.get("type")

    result = manager.list_execution_batches(
        page=page, limit=limit, script_type=script_type
    )
    return jsonify({"code": 0, "data": result, "msg": "success"})


@scripts_bp.route("/executions/<execution_id>/status", methods=["GET"])
def get_execution_status(execution_id):
    """
    获取指定执行批次的线程状态列表。

    GET /api/scripts/executions/{execution_id}/status

    Returns:
        {"code": 0, "data": [线程状态列表], "msg": "success"}
    """
    manager = _get_manager()
    records = manager.get_execution_status(execution_id)
    return jsonify({"code": 0, "data": records, "msg": "success"})
