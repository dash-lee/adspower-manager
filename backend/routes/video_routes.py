"""
视频管理路由
==========

提供视频的增删改查 REST API。
"""
import datetime
from flask import Blueprint, request, jsonify, session
from loguru import logger

from backend.models import db, Video, VideoVisitLog, VideoDailyStats

video_bp = Blueprint("video", __name__, url_prefix="/api/videos")


def _get_today_str():
    """获取今天的日期字符串 YYYY-MM-DD。"""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


@video_bp.route("", methods=["GET"])
def list_videos():
    """
    获取视频列表（含今日访问次数统计）。

    GET /api/videos
    Query params:
        keyword: 搜索关键词（可选，匹配视频名称或网站）
    """
    today = _get_today_str()
    keyword = request.args.get("keyword", "").strip()
    account_filter = request.args.get("account_name", "").strip()
    query = Video.query.order_by(Video.id.desc())

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            db.or_(Video.video_name.like(like), Video.website.like(like))
        )
    if account_filter:
        query = query.filter(Video.account_name == account_filter)

    videos = query.all()

    # 批量统计今日访问次数
    video_ids = [v.id for v in videos]
    if video_ids:
        from sqlalchemy import func
        visit_counts = dict(
            db.session.query(
                VideoVisitLog.video_id,
                func.count(VideoVisitLog.id)
            )
            .filter(
                VideoVisitLog.video_id.in_(video_ids),
                VideoVisitLog.visit_date == today,
            )
            .group_by(VideoVisitLog.video_id)
            .all()
        )
    else:
        visit_counts = {}

    result = []
    for v in videos:
        d = v.to_dict()
        d["today_visits"] = visit_counts.get(v.id, 0)
        result.append(d)

    return jsonify({"code": 0, "data": result, "msg": "success"})


@video_bp.route("/accounts", methods=["GET"])
def list_video_accounts():
    """
    获取所有视频中存在的账号名称列表（去重，用于搜索下拉）。

    GET /api/videos/accounts

    Returns:
        {"code": 0, "data": ["账号1", "账号2", ...], "msg": "success"}
    """
    accounts = (
        db.session.query(Video.account_name)
        .filter(Video.account_name != "")
        .distinct()
        .order_by(Video.account_name)
        .all()
    )
    return jsonify({"code": 0, "data": [a[0] for a in accounts], "msg": "success"})


@video_bp.route("/websites", methods=["GET"])
def list_video_websites():
    """
    获取所有视频中存在的网站名称列表（去重，用于搜索下拉）。

    GET /api/videos/websites

    Returns:
        {"code": 0, "data": ["网站1", "网站2", ...], "msg": "success"}
    """
    websites = (
        db.session.query(Video.website)
        .filter(Video.website != "")
        .distinct()
        .order_by(Video.website)
        .all()
    )
    return jsonify({"code": 0, "data": [w[0] for w in websites], "msg": "success"})


@video_bp.route("", methods=["POST"])
def create_video():
    """
    新增视频。

    POST /api/videos
    Body: {
        "video_name": "示例视频",
        "video_url": "https://example.com/video",
        "website": "YouTube",
        "operator": "admin"
    }
    """
    data = request.get_json()
    if not data or not data.get("video_name") or not data.get("video_url"):
        return jsonify({"code": -1, "data": None, "msg": "视频名称和链接不能为空"})

    operator_name = session.get("username", "system")
    video = Video(
        video_name=data["video_name"].strip(),
        video_url=data["video_url"].strip(),
        website=data.get("website", "").strip(),
        account_name=data.get("account_name", "").strip(),
        operator=operator_name,
    )
    db.session.add(video)
    db.session.commit()
    logger.info(f"新增视频: {video.video_name} (操作人: {operator_name})")
    return jsonify({"code": 0, "data": video.to_dict(), "msg": "视频已添加"})


@video_bp.route("/<int:video_id>", methods=["PUT"])
def update_video(video_id):
    """
    编辑视频。

    PUT /api/videos/{id}
    Body: { "video_name": "...", "video_url": "...", "website": "..." }
    """
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"code": -1, "data": None, "msg": "视频不存在"})

    data = request.get_json()
    if not data:
        return jsonify({"code": -1, "data": None, "msg": "请求体为空"})

    if "video_name" in data:
        video.video_name = data["video_name"].strip()
    if "video_url" in data:
        video.video_url = data["video_url"].strip()
    if "website" in data:
        video.website = data["website"].strip()
    if "account_name" in data:
        video.account_name = data["account_name"].strip()

    video.operator = session.get("username", "system")
    db.session.commit()
    logger.info(f"更新视频: {video.video_name}")
    return jsonify({"code": 0, "data": video.to_dict(), "msg": "视频已更新"})


@video_bp.route("/<int:video_id>", methods=["DELETE"])
def delete_video(video_id):
    """
    删除视频。

    DELETE /api/videos/{id}
    """
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"code": -1, "data": None, "msg": "视频不存在"})

    name = video.video_name
    # 同时删除关联的访问日志
    VideoVisitLog.query.filter_by(video_id=video_id).delete()
    db.session.delete(video)
    db.session.commit()
    logger.info(f"删除视频: {name}")
    return jsonify({"code": 0, "data": None, "msg": "视频已删除"})


@video_bp.route("/<int:video_id>/visit", methods=["POST"])
def record_visit(video_id):
    """
    记录视频访问（IP 去重）。

    POST /api/videos/{id}/visit
    需要客户端传入访问者 IP 地址。
    Body: { "ip": "192.168.1.1" }
    """
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"code": -1, "data": None, "msg": "视频不存在"})

    data = request.get_json() or {}
    ip = data.get("ip", request.remote_addr or "unknown")
    today = _get_today_str()

    # 检查今天该 IP 是否已访问过
    existing = VideoVisitLog.query.filter_by(
        video_id=video_id, ip_address=ip, visit_date=today
    ).first()

    if not existing:
        log = VideoVisitLog(
            video_id=video_id, ip_address=ip, visit_date=today
        )
        db.session.add(log)
        db.session.commit()

    # 统计今日访问次数
    from sqlalchemy import func
    count = db.session.query(func.count(VideoVisitLog.id)).filter(
        VideoVisitLog.video_id == video_id,
        VideoVisitLog.visit_date == today,
    ).scalar() or 0

    return jsonify({
        "code": 0,
        "data": {"today_visits": count, "is_new": not bool(existing)},
        "msg": "success",
    })


@video_bp.route("/history", methods=["GET"])
def list_video_history():
    """
    获取视频历史访问统计（分页）。

    GET /api/videos/history
    Query params:
        page:   页码（默认1）
        limit:  每页数量（默认50，最大200）
        date:   按日期筛选（可选 YYYY-MM-DD）
        video_id: 按视频ID筛选（可选）
    """
    page = int(request.args.get("page", 1))
    limit = min(int(request.args.get("limit", 50)), 200)
    date_filter = request.args.get("date", "").strip()
    video_id_filter = request.args.get("video_id", "").strip()

    query = VideoDailyStats.query.order_by(VideoDailyStats.stats_date.desc(), VideoDailyStats.video_id)

    if date_filter:
        query = query.filter(VideoDailyStats.stats_date == date_filter)
    if video_id_filter:
        try:
            query = query.filter(VideoDailyStats.video_id == int(video_id_filter))
        except ValueError:
            pass

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        "code": 0,
        "data": {
            "list": [item.to_dict() for item in items],
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": max(1, (total + limit - 1) // limit),
        },
        "msg": "success",
    })
