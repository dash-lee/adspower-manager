"""
配置管理 API 路由
================

提供后台配置的增删改查 REST API。

配置类别：
1. 通用配置 (general_config)       - 系统参数（API地址、密钥、轮询间隔等）
2. 代理配置 (proxy_config)         - 代理服务器配置
3. 指纹随机池 (fingerprint_pool)   - 创建环境时的随机候选参数
4. 环境保留 (preserved_env)        - 需要保留不被删除的环境

所有接口返回 JSON 格式：{"code": 0, "data": ..., "msg": "success"}
"""

import json
from flask import Blueprint, request, jsonify
from backend.models import (
    db, GeneralConfig, ProxyConfig, FingerprintPool, PreservedEnv,
)

config_bp = Blueprint("config", __name__, url_prefix="/api/config")


# ============================================================
# 通用配置 CRUD
# ============================================================

@config_bp.route("/general", methods=["GET"])
def get_all_general_config():
    """
    获取所有通用配置。

    GET /api/config/general

    Returns:
        {"code": 0, "data": [...], "msg": "success"}
    """
    configs = GeneralConfig.query.order_by(GeneralConfig.category, GeneralConfig.config_key).all()
    return jsonify({
        "code": 0,
        "data": [
            {
                "id": c.id,
                "config_key": c.config_key,
                "config_value": c.config_value,
                "category": c.category,
                "remark": c.remark,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in configs
        ],
        "msg": "success",
    })


@config_bp.route("/general/<string:key>", methods=["GET"])
def get_one_general_config(key):
    """
    获取单个通用配置。

    GET /api/config/general/{key}

    Args:
        key: 配置键名
    """
    config = GeneralConfig.query.filter_by(config_key=key).first()
    if not config:
        return jsonify({"code": -1, "data": None, "msg": f"配置 {key} 不存在"})
    return jsonify({
        "code": 0,
        "data": {
            "id": config.id,
            "config_key": config.config_key,
            "config_value": config.config_value,
            "category": config.category,
            "remark": config.remark,
        },
        "msg": "success",
    })


@config_bp.route("/general", methods=["POST"])
def upsert_general_config():
    """
    创建或更新通用配置（如果 key 已存在则更新值）。

    POST /api/config/general
    Body: {
        "config_key": "adspower_api_url",
        "config_value": "http://local.adspower.net:50325",
        "category": "general",
        "remark": "AdsPower API地址"
    }
    """
    data = request.get_json()
    if not data or "config_key" not in data or "config_value" not in data:
        return jsonify({"code": -1, "data": None, "msg": "缺少必填参数 config_key 和 config_value"})

    existing = GeneralConfig.query.filter_by(config_key=data["config_key"]).first()
    if existing:
        existing.config_value = str(data["config_value"])
        existing.category = data.get("category", existing.category)
        existing.remark = data.get("remark", existing.remark)
    else:
        new_config = GeneralConfig(
            config_key=data["config_key"],
            config_value=str(data["config_value"]),
            category=data.get("category", "general"),
            remark=data.get("remark", ""),
        )
        db.session.add(new_config)
    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "配置已保存（即时生效）"})


@config_bp.route("/general/<int:config_id>", methods=["DELETE"])
def delete_general_config(config_id):
    """
    删除通用配置。

    DELETE /api/config/general/{id}
    """
    config = GeneralConfig.query.get(config_id)
    if not config:
        return jsonify({"code": -1, "data": None, "msg": "配置不存在"})
    db.session.delete(config)
    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "配置已删除"})


# ============================================================
# 代理配置 CRUD
# ============================================================

@config_bp.route("/proxy", methods=["GET"])
def get_all_proxy_config():
    """
    获取所有代理配置。

    GET /api/config/proxy
    """
    proxies = ProxyConfig.query.order_by(ProxyConfig.enabled.desc(), ProxyConfig.id).all()
    return jsonify({
        "code": 0,
        "data": [
            {
                "id": p.id,
                "ads_proxy_id": p.ads_proxy_id,
                "name": p.name,
                "proxy_soft": p.proxy_soft,
                "proxy_type": p.proxy_type,
                "proxy_host": p.proxy_host,
                "proxy_port": p.proxy_port,
                "proxy_user": p.proxy_user,
                "proxy_password": "***" if p.proxy_password else "",  # 密码脱敏
                "enabled": p.enabled,
                "remark": p.remark,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in proxies
        ],
        "msg": "success",
    })


@config_bp.route("/proxy", methods=["POST"])
def create_proxy_config():
    """
    创建代理配置。

    POST /api/config/proxy
    Body: {
        "ads_proxy_id": "xxx",    // AdsPower 中的代理ID（可选）
        "name": "代理1",
        "proxy_soft": "other",
        "proxy_type": "socks5",
        "proxy_host": "1.2.3.4",
        "proxy_port": "1080",
        "proxy_user": "user",
        "proxy_password": "pass",
        "enabled": 1,
        "remark": "备注"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"code": -1, "data": None, "msg": "请求体为空"})

    required = ["proxy_host", "proxy_port"]
    for field in required:
        if field not in data:
            return jsonify({"code": -1, "data": None, "msg": f"缺少必填参数: {field}"})

    proxy = ProxyConfig(
        ads_proxy_id=data.get("ads_proxy_id", ""),
        name=data.get("name", ""),
        proxy_soft=data.get("proxy_soft", "other"),
        proxy_type=data.get("proxy_type", "socks5"),
        proxy_host=data["proxy_host"],
        proxy_port=str(data["proxy_port"]),
        proxy_user=data.get("proxy_user", ""),
        proxy_password=data.get("proxy_password", ""),
        enabled=data.get("enabled", 1),
        remark=data.get("remark", ""),
    )
    db.session.add(proxy)
    db.session.commit()
    return jsonify({"code": 0, "data": {"id": proxy.id}, "msg": "代理配置已创建"})


@config_bp.route("/proxy/<int:proxy_id>", methods=["PUT"])
def update_proxy_config(proxy_id):
    """
    更新代理配置。

    PUT /api/config/proxy/{id}
    """
    proxy = ProxyConfig.query.get(proxy_id)
    if not proxy:
        return jsonify({"code": -1, "data": None, "msg": "代理配置不存在"})

    data = request.get_json()
    if not data:
        return jsonify({"code": -1, "data": None, "msg": "请求体为空"})

    # 更新传入的字段
    for field in ["ads_proxy_id", "name", "proxy_soft", "proxy_type",
                   "proxy_host", "proxy_port", "proxy_user", "proxy_password",
                   "enabled", "remark"]:
        if field in data:
            setattr(proxy, field, str(data[field]) if field not in ["enabled"] else int(data[field]))

    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "代理配置已更新"})


@config_bp.route("/proxy/<int:proxy_id>", methods=["DELETE"])
def delete_proxy_config(proxy_id):
    """
    删除代理配置。

    DELETE /api/config/proxy/{id}
    """
    proxy = ProxyConfig.query.get(proxy_id)
    if not proxy:
        return jsonify({"code": -1, "data": None, "msg": "代理配置不存在"})
    db.session.delete(proxy)
    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "代理配置已删除"})


# ============================================================
# 指纹随机池 CRUD
# ============================================================

@config_bp.route("/fingerprint", methods=["GET"])
def get_all_fingerprints():
    """
    获取所有指纹池配置，按参数名分组。

    GET /api/config/fingerprint

    Query params:
        param_name: 过滤指定参数名（可选）
    """
    param_filter = request.args.get("param_name")
    query = FingerprintPool.query.order_by(FingerprintPool.param_name, FingerprintPool.id)
    if param_filter:
        query = query.filter_by(param_name=param_filter)

    items = query.all()
    return jsonify({
        "code": 0,
        "data": [
            {
                "id": f.id,
                "param_name": f.param_name,
                "param_value": f.param_value,
                "weight": f.weight,
                "enabled": f.enabled,
                "remark": f.remark,
            }
            for f in items
        ],
        "msg": "success",
    })


@config_bp.route("/fingerprint", methods=["POST"])
def create_fingerprint_item():
    """
    添加指纹池候选项。

    POST /api/config/fingerprint
    Body: {
        "param_name": "screen_resolution",
        "param_value": "1920_1080",
        "weight": 5,
        "enabled": 1,
        "remark": "Full HD"
    }
    """
    data = request.get_json()
    if not data or "param_name" not in data or "param_value" not in data:
        return jsonify({"code": -1, "data": None, "msg": "缺少必填参数 param_name 和 param_value"})

    item = FingerprintPool(
        param_name=data["param_name"],
        param_value=data["param_value"],
        weight=data.get("weight", 1),
        enabled=data.get("enabled", 1),
        remark=data.get("remark", ""),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"code": 0, "data": {"id": item.id}, "msg": "指纹候选项已添加"})


@config_bp.route("/fingerprint/<int:item_id>", methods=["PUT"])
def update_fingerprint_item(item_id):
    """
    更新指纹池候选项。

    PUT /api/config/fingerprint/{id}
    """
    item = FingerprintPool.query.get(item_id)
    if not item:
        return jsonify({"code": -1, "data": None, "msg": "候选项不存在"})

    data = request.get_json()
    if not data:
        return jsonify({"code": -1, "data": None, "msg": "请求体为空"})

    for field in ["param_name", "param_value", "weight", "enabled", "remark"]:
        if field in data:
            setattr(item, field, data[field])

    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "指纹候选项已更新"})


@config_bp.route("/fingerprint/<int:item_id>", methods=["DELETE"])
def delete_fingerprint_item(item_id):
    """
    删除指纹池候选项。

    DELETE /api/config/fingerprint/{id}
    """
    item = FingerprintPool.query.get(item_id)
    if not item:
        return jsonify({"code": -1, "data": None, "msg": "候选项不存在"})
    db.session.delete(item)
    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "指纹候选项已删除"})


# ============================================================
# 环境保留 CRUD
# ============================================================

@config_bp.route("/preserved", methods=["GET"])
def get_all_preserved():
    """
    获取所有保留环境配置。

    GET /api/config/preserved
    """
    envs = PreservedEnv.query.order_by(PreservedEnv.id).all()
    return jsonify({
        "code": 0,
        "data": [
            {
                "id": e.id,
                "profile_id": e.profile_id,
                "env_name": e.env_name,
                "remark": e.remark,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in envs
        ],
        "msg": "success",
    })


@config_bp.route("/preserved", methods=["POST"])
def add_preserved_env():
    """
    添加保留环境。

    POST /api/config/preserved
    Body: {
        "profile_id": "h1yynkm",
        "env_name": "测试环境1",
        "remark": "用于日常测试"
    }
    """
    data = request.get_json()
    if not data or "profile_id" not in data:
        return jsonify({"code": -1, "data": None, "msg": "缺少必填参数 profile_id"})

    existing = PreservedEnv.query.filter_by(profile_id=data["profile_id"]).first()
    if existing:
        return jsonify({"code": -1, "data": None, "msg": "该环境已在保留列表中"})

    env = PreservedEnv(
        profile_id=data["profile_id"],
        env_name=data.get("env_name", ""),
        remark=data.get("remark", ""),
    )
    db.session.add(env)
    db.session.commit()
    return jsonify({"code": 0, "data": {"id": env.id}, "msg": "保留环境已添加"})


@config_bp.route("/preserved/<int:env_id>", methods=["DELETE"])
def remove_preserved_env(env_id):
    """
    移除保留环境。

    DELETE /api/config/preserved/{id}
    """
    env = PreservedEnv.query.get(env_id)
    if not env:
        return jsonify({"code": -1, "data": None, "msg": "保留环境不存在"})
    db.session.delete(env)
    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "保留环境已移除"})


# ============================================================
# 批量导入初始配置
# ============================================================

@config_bp.route("/init_defaults", methods=["POST"])
def init_default_configs():
    """
    初始化默认配置数据（仅在首次部署时使用）。

    POST /api/config/init_defaults

    自动插入以下默认数据：
    1. 通用配置默认值
    2. 常用指纹池候选值
    """
    results = {"general_configs": 0, "fingerprint_items": 0}

    # --- 通用配置默认值 ---
    defaults = [
        ("adspower_api_url", "http://local.adspower.net:50325", "general", "AdsPower Local API 地址"),
        ("adspower_api_key", "", "general", "AdsPower API 密钥（在客户端→自动化→API中获取）"),
        ("default_group_id", "0", "general", "创建环境时的默认分组ID（0=默认分组）"),
        ("task_poll_interval", "30", "general", "任务队列轮询间隔（秒）"),
        ("auto_check_interval", "3600", "general", "自动状态检查间隔（秒）"),
        ("max_env_limit", "100", "general", "环境数量上限（超过后不再创建）"),
    ]
    for key, value, category, remark in defaults:
        existing = GeneralConfig.query.filter_by(config_key=key).first()
        if not existing:
            gc = GeneralConfig(config_key=key, config_value=value, category=category, remark=remark)
            db.session.add(gc)
            results["general_configs"] += 1

    # --- 指纹池默认候选值 ---
    fingerprint_defaults = [
        # screen_resolution 屏幕分辨率
        ("screen_resolution", "1920_1080", 5, "1920x1080 (Full HD)"),
        ("screen_resolution", "1366_768", 4, "1366x768 (常见笔记本)"),
        ("screen_resolution", "2560_1440", 3, "2560x1440 (2K)"),
        ("screen_resolution", "3840_2160", 1, "3840x2160 (4K)"),
        ("screen_resolution", "1440_900", 3, "1440x900"),
        ("screen_resolution", "1536_864", 2, "1536x864"),
        ("screen_resolution", "1680_1050", 2, "1680x1050"),
        ("screen_resolution", "1280_720", 2, "1280x720 (HD)"),
        # hardware_concurrency CPU核心数
        ("hardware_concurrency", "4", 4, "4核"),
        ("hardware_concurrency", "8", 4, "8核"),
        ("hardware_concurrency", "2", 2, "2核"),
        ("hardware_concurrency", "6", 3, "6核"),
        ("hardware_concurrency", "16", 1, "16核"),
        # device_memory 内存
        ("device_memory", "8", 5, "8GB"),
        ("device_memory", "4", 4, "4GB"),
        ("device_memory", "16", 3, "16GB"),
        ("device_memory", "2", 1, "2GB"),
        # media_devices 媒体设备
        ("media_devices", "1", 5, "噪音（跟随本机设备数）"),
        ("media_devices", "2", 2, "噪音（自定义设备数）"),
        ("media_devices", "0", 1, "关闭（使用本机默认）"),
        # media_devices_num 自定义设备数量
        ("media_devices_num", '{"audioinput_num":"1","videoinput_num":"1","audiooutput_num":"1"}', 3, "1麦克风+1摄像头+1扬声器"),
        ("media_devices_num", '{"audioinput_num":"2","videoinput_num":"1","audiooutput_num":"1"}', 2, "2麦克风+1摄像头+1扬声器"),
        # fonts 字体
        ("fonts", '["Arial","Calibri","Cambria","Times New Roman"]', 3, "常见英文字体组合1"),
        ("fonts", '["Arial","Helvetica","sans-serif","Georgia"]', 3, "常见英文字体组合2"),
        ("fonts", '["all"]', 2, "使用所有字体"),
    ]
    for param_name, param_value, weight, remark in fingerprint_defaults:
        existing = FingerprintPool.query.filter_by(
            param_name=param_name, param_value=param_value
        ).first()
        if not existing:
            item = FingerprintPool(
                param_name=param_name, param_value=param_value, weight=weight, remark=remark
            )
            db.session.add(item)
            results["fingerprint_items"] += 1

    db.session.commit()
    return jsonify({
        "code": 0,
        "data": results,
        "msg": f"默认配置已初始化：{results['general_configs']}个通用配置，{results['fingerprint_items']}个指纹候选项",
    })
