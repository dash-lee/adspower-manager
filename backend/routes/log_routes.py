"""
日志查看 API 路由
================

提供操作日志和环境运行日志的查询接口。
供后台管理页面展示。

GET /api/logs/operation    - 操作日志列表（支持分页和过滤）
GET /api/logs/environment   - 环境运行日志列表（支持分页）
GET /api/logs/stats         - 日志统计概览
"""

import json
from flask import Blueprint, request, jsonify
from backend.models import db, OperationLog, EnvRuntimeLog

log_bp = Blueprint("log", __name__, url_prefix="/api/logs")


@log_bp.route("/operation", methods=["GET"])
def get_operation_logs():
    """
    获取操作日志。

    GET /api/logs/operation

    Query params:
        page:     页码（默认1）
        limit:    每页数量（默认50）
        level:    日志级别过滤（INFO/WARNING/ERROR）
        module:   模块过滤（adspower_client/env_manager/scheduler/system）
        keyword:  关键词搜索
    """
    page = int(request.args.get("page", 1))
    limit = min(int(request.args.get("limit", 50)), 200)
    level_filter = request.args.get("level")
    module_filter = request.args.get("module")
    keyword = request.args.get("keyword")

    query = OperationLog.query.order_by(OperationLog.created_at.desc())

    if level_filter:
        query = query.filter_by(level=level_filter.upper())
    if module_filter:
        query = query.filter_by(module=module_filter)
    if keyword:
        query = query.filter(OperationLog.message.contains(keyword))

    total = query.count()
    logs = query.offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        "code": 0,
        "data": {
            "list": [
                {
                    "id": l.id,
                    "level": l.level,
                    "module": l.module,
                    "message": l.message,
                    "detail": l.detail,
                    "created_at": l.created_at.isoformat() if l.created_at else None,
                }
                for l in logs
            ],
            "total": total,
            "page": page,
            "limit": limit,
        },
        "msg": "success",
    })


@log_bp.route("/environment", methods=["GET"])
def get_env_runtime_logs():
    """
    获取环境运行日志。

    GET /api/logs/environment

    Query params:
        page:       页码（默认1）
        limit:      每页数量（默认50）
        profile_id: 环境ID过滤
        event_type: 事件类型过滤（create/delete/start/stop/ip_check）
    """
    page = int(request.args.get("page", 1))
    limit = min(int(request.args.get("limit", 50)), 200)
    profile_id = request.args.get("profile_id")
    event_type = request.args.get("event_type")

    query = EnvRuntimeLog.query.order_by(EnvRuntimeLog.created_at.desc())

    if profile_id:
        query = query.filter_by(profile_id=profile_id)
    if event_type:
        query = query.filter_by(event_type=event_type)

    total = query.count()
    logs = query.offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        "code": 0,
        "data": {
            "list": [
                {
                    "id": l.id,
                    "profile_id": l.profile_id,
                    "env_name": l.env_name,
                    "event_type": l.event_type,
                    "ip_address": l.ip_address,
                    "duration_seconds": l.duration_seconds,
                    "extra_data": l.extra_data,
                    "created_at": l.created_at.isoformat() if l.created_at else None,
                }
                for l in logs
            ],
            "total": total,
            "page": page,
            "limit": limit,
        },
        "msg": "success",
    })


@log_bp.route("/stats", methods=["GET"])
def get_log_stats():
    """
    获取日志统计概览。

    GET /api/logs/stats

    Returns:
        {
            "operation": {
                "total": 日志总数,
                "by_level": {"INFO": N, "WARNING": N, "ERROR": N},
                "today": 今日日志数
            },
            "environment": {
                "total": 记录总数,
                "by_type": {"create": N, "delete": N, ...},
                "today": 今日记录数
            }
        }
    """
    import datetime
    today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # 操作日志统计
    op_query = OperationLog.query
    op_total = op_query.count()
    op_today = op_query.filter(OperationLog.created_at >= today).count()
    op_by_level = {}
    for level in ["INFO", "WARNING", "ERROR"]:
        op_by_level[level] = OperationLog.query.filter_by(level=level).count()

    # 环境运行日志统计
    env_query = EnvRuntimeLog.query
    env_total = env_query.count()
    env_today = env_query.filter(EnvRuntimeLog.created_at >= today).count()
    env_by_type = {}
    for etype in ["create", "delete", "start", "stop", "ip_check"]:
        env_by_type[etype] = EnvRuntimeLog.query.filter_by(event_type=etype).count()

    return jsonify({
        "code": 0,
        "data": {
            "operation": {
                "total": op_total,
                "by_level": op_by_level,
                "today": op_today,
            },
            "environment": {
                "total": env_total,
                "by_type": env_by_type,
                "today": env_today,
            },
        },
        "msg": "success",
    })
