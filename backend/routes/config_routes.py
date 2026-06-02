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
from flask import Blueprint, request, jsonify, session
from backend.models import (
    db, GeneralConfig, ProxyConfig, FingerprintPool, PreservedEnv, AdminLog,
)

config_bp = Blueprint("config", __name__, url_prefix="/api/config")


def _log_admin(action: str, target: str = "", detail: dict = None):
    """记录管理员操作日志（自动获取用户名和IP）。"""
    import json as _json
    operator = session.get("username", "system")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    log_entry = AdminLog(
        operator_username=operator,
        action=action,
        target=target,
        ip_address=ip,
        detail=_json.dumps(detail, ensure_ascii=False) if detail else None,
    )
    db.session.add(log_entry)
    # commit 由调用方负责（在同一个事务中）


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
                "operator": c.operator,
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

    operator_name = session.get("username", "system")
    existing = GeneralConfig.query.filter_by(config_key=data["config_key"]).first()
    if existing:
        old_value = existing.config_value
        existing.config_value = str(data["config_value"])
        existing.category = data.get("category", existing.category)
        existing.remark = data.get("remark", existing.remark)
        existing.operator = operator_name
        _log_admin("修改通用配置", data["config_key"], {"old": old_value, "new": data["config_value"]})
    else:
        new_config = GeneralConfig(
            config_key=data["config_key"],
            config_value=str(data["config_value"]),
            category=data.get("category", "general"),
            remark=data.get("remark", ""),
            operator=operator_name,
        )
        db.session.add(new_config)
        _log_admin("新增通用配置", data["config_key"], {"value": data["config_value"]})
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
    key = config.config_key
    db.session.delete(config)
    _log_admin("删除通用配置", key)
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
                "operator": p.operator,
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

    operator_name = session.get("username", "system")
    # 支持 other 类型时自定义代理软件名称
    proxy_soft = data.get("proxy_soft", "other")
    if proxy_soft == "other" and data.get("custom_soft_name"):
        proxy_soft = data["custom_soft_name"]

    proxy = ProxyConfig(
        ads_proxy_id=data.get("ads_proxy_id", ""),
        name=data.get("name", ""),
        proxy_soft=proxy_soft,
        proxy_type=data.get("proxy_type", "socks5"),
        proxy_host=data["proxy_host"],
        proxy_port=str(data["proxy_port"]),
        proxy_user=data.get("proxy_user", ""),
        proxy_password=data.get("proxy_password", ""),
        enabled=data.get("enabled", 1),
        remark=data.get("remark", ""),
        operator=operator_name,
    )
    db.session.add(proxy)
    _log_admin("新增代理配置", f"{proxy.proxy_host}:{proxy.proxy_port}", {"name": proxy.name, "type": proxy.proxy_type})
    db.session.commit()
    return jsonify({"code": 0, "data": {"id": proxy.id}, "msg": "代理配置已创建"})


@config_bp.route("/proxy/sync_from_adspower", methods=["POST"])
def sync_proxies_from_adspower():
    """
    从 AdsPower 同步代理列表到本地数据库。

    POST /api/config/proxy/sync_from_adspower

    从 AdsPower API 获取代理列表，将新代理添加到本地数据库。
    """
    from flask import current_app
    from backend.services.adspower_client import AdsPowerClient
    client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]

    resp = client.list_proxies(limit=200)
    if not client._is_success(resp):
        return jsonify({"code": -1, "data": None, "msg": f"从 AdsPower 获取代理列表失败: {resp.get('msg')}"})

    proxy_list = resp.get("data", {}).get("list", [])
    if not proxy_list:
        return jsonify({"code": 0, "data": {"added": 0, "skipped": 0}, "msg": "AdsPower 中未找到代理"})

    added = 0
    skipped = 0
    for ap in proxy_list:
        proxy_id = ap.get("proxy_id", "")
        if not proxy_id:
            continue
        existing = ProxyConfig.query.filter_by(ads_proxy_id=proxy_id).first()
        if existing:
            # 如果已有记录但代理信息为空（上一个版本的 bug 导致），则更新之
            if not existing.proxy_host:
                existing.proxy_soft = ap.get("proxy_soft", "other")
                existing.proxy_type = ap.get("type", "socks5")
                existing.proxy_host = ap.get("host", "")
                existing.proxy_port = str(ap.get("port", ""))
                existing.proxy_user = ap.get("user", "")
                existing.proxy_password = ap.get("password", "")
                existing.remark = ap.get("remark", "")
                existing.operator = session.get("username", "system")
                added += 1  # 算作有效新增
            else:
                skipped += 1
            continue
        new_proxy = ProxyConfig(
            ads_proxy_id=proxy_id,
            name=ap.get("name", "") or ap.get("remark", ""),
            proxy_soft=ap.get("proxy_soft", "other"),
            proxy_type=ap.get("type", "socks5"),
            proxy_host=ap.get("host", ""),
            proxy_port=str(ap.get("port", "")),
            proxy_user=ap.get("user", ""),
            proxy_password=ap.get("password", ""),
            enabled=1,
            remark=ap.get("remark", ""),
            operator=session.get("username", "system"),
        )
        db.session.add(new_proxy)
        added += 1

    db.session.commit()
    _log_admin("从AdsPower同步代理", f"新增{added},跳过{skipped}")
    return jsonify({
        "code": 0,
        "data": {"added": added, "skipped": skipped},
        "msg": f"同步完成：新增 {added} 个代理，跳过 {skipped} 个已有代理",
    })


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

    operator_name = session.get("username", "system")
    # 更新传入的字段
    for field in ["ads_proxy_id", "name", "proxy_soft", "proxy_type",
                   "proxy_host", "proxy_port", "proxy_user", "proxy_password",
                   "enabled", "remark"]:
        if field in data:
            # 支持 other 类型时自定义代理软件名称
            if field == "proxy_soft" and data[field] == "other" and data.get("custom_soft_name"):
                setattr(proxy, field, data["custom_soft_name"])
            elif field not in ["enabled"]:
                setattr(proxy, field, str(data[field]))
            else:
                setattr(proxy, field, int(data[field]))
    proxy.operator = operator_name

    _log_admin("修改代理配置", f"{proxy.proxy_host}:{proxy.proxy_port}", {"name": proxy.name})
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
    info = f"{proxy.proxy_host}:{proxy.proxy_port}"
    db.session.delete(proxy)
    _log_admin("删除代理配置", info)
    db.session.commit()
    return jsonify({"code": 0, "data": None, "msg": "代理配置已删除"})


# ============================================================
# 指纹随机池 CRUD
# ============================================================

@config_bp.route("/fingerprint", methods=["GET"])
def get_all_fingerprints():
    """
    获取所有指纹池配置。

    GET /api/config/fingerprint

    每个参数名只有一条记录（候选值用逗号分隔）。

    Query params:
        param_name: 过滤指定参数名（可选）
    """
    param_filter = request.args.get("param_name")
    query = FingerprintPool.query.order_by(FingerprintPool.param_name)
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
                "param_weights": f.param_weights,
                "weight": f.weight,
                "enabled": f.enabled,
                "remark": f.remark,
                "operator": f.operator,
            }
            for f in items
        ],
        "msg": "success",
    })


@config_bp.route("/fingerprint", methods=["POST"])
def upsert_fingerprint_item():
    """
    新增或更新指纹参数（按参数名 upsert）。

    如果参数名已存在，则更新其候选值和其他属性；
    如果参数名不存在，则创建新的记录。

    POST /api/config/fingerprint
    Body: {
        "param_name": "screen_resolution",
        "param_value": "1920_1080,1366_768,2560_1440",
        "weight": 5,
        "enabled": 1,
        "remark": "屏幕分辨率候选池"
    }
    """
    data = request.get_json()
    if not data or "param_name" not in data or "param_value" not in data:
        return jsonify({"code": -1, "data": None, "msg": "缺少必填参数 param_name 和 param_value"})

    operator_name = session.get("username", "system")

    # 查找是否已存在该参数名
    existing = FingerprintPool.query.filter_by(param_name=data["param_name"]).first()

    if existing:
        # 更新已有记录
        existing.param_value = data["param_value"]
        if "param_weights" in data:
            existing.param_weights = data["param_weights"]
        if "weight" in data:
            existing.weight = data["weight"]
        if "enabled" in data:
            existing.enabled = data["enabled"]
        if "remark" in data:
            existing.remark = data.get("remark", "")
        existing.operator = operator_name
        _log_admin("修改指纹参数", data["param_name"], {"value": data["param_value"]})
        msg = "指纹参数已更新"
    else:
        # 创建新记录
        existing = FingerprintPool(
            param_name=data["param_name"],
            param_value=data["param_value"],
            param_weights=data.get("param_weights", ""),
            weight=data.get("weight", 1),
            enabled=data.get("enabled", 1),
            remark=data.get("remark", ""),
            operator=operator_name,
        )
        db.session.add(existing)
        _log_admin("新增指纹参数", data["param_name"], {"value": data["param_value"]})
        msg = "指纹参数已添加"

    db.session.commit()
    return jsonify({"code": 0, "data": {"id": existing.id}, "msg": msg})


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
    item.operator = session.get("username", "system")

    _log_admin("修改指纹候选项", item.param_name, {"value": item.param_value})
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
    info = f"{item.param_name}={item.param_value}"
    db.session.delete(item)
    _log_admin("删除指纹候选项", info)
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
                "operator": e.operator,
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
        operator=session.get("username", "system"),
    )
    db.session.add(env)
    _log_admin("新增保留环境", data["profile_id"], {"name": data.get("env_name", "")})
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
    info = env.profile_id
    db.session.delete(env)
    _log_admin("删除保留环境", info)
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
        ("adspower_api_url", "http://local.adspower.net:50325", "general", "AdsPower Local API 地址（修改后需点「重载客户端」）"),
        ("adspower_api_key", "", "general", "AdsPower API 密钥，在客户端→账号管理→设置→API 中获取（修改后需点「重载客户端」）"),
        ("default_group_id", "0", "general", "创建环境时的默认分组ID（0=默认分组）"),
        ("task_poll_interval", "30", "general", "任务队列轮询间隔（秒，修改后即时生效）"),
        ("auto_check_interval", "3600", "general", "自动状态检查间隔（秒，修改后即时生效）"),
        ("max_env_limit", "100", "general", "环境数量上限（超过后无法创建新环境）"),
        ("log_retention_days", "7", "general", "操作日志保留天数（超过自动清理）"),
        ("batch_delete_limit", "100", "general", "批量删除每批最大数量"),
        ("video_websites", "YouTube,Bilibili,TikTok,Twitch,Vimeo", "general", "视频管理中的可选网站列表（逗号分隔）"),
    ]
    for key, value, category, remark in defaults:
        existing = GeneralConfig.query.filter_by(config_key=key).first()
        if not existing:
            gc = GeneralConfig(config_key=key, config_value=value, category=category, remark=remark)
            db.session.add(gc)
            results["general_configs"] += 1

    # --- 指纹池默认候选值（每个参数一条记录，值用逗号分隔） ---
    fingerprint_defaults = [
        # screen_resolution 屏幕分辨率
        ("screen_resolution", "1920_1080,1366_768,2560_1440,3840_2160,1440_900,1536_864,1680_1050,1280_720", 5, "屏幕分辨率候选池（随机选取）"),
        # hardware_concurrency CPU核心数
        ("hardware_concurrency", "2,4,6,8,16", 5, "CPU核心数候选池"),
        # device_memory 内存
        ("device_memory", "2,4,8,16", 5, "设备内存(GB)候选池"),
        # media_devices 媒体设备
        ("media_devices", "0,1,2", 5, "媒体设备模式: 0=关闭, 1=噪音跟随, 2=自定义"),
        # media_devices_num 自定义设备数量 (JSON)
        ("media_devices_num", '{"audioinput_num":"1","videoinput_num":"1","audiooutput_num":"1"},{"audioinput_num":"2","videoinput_num":"1","audiooutput_num":"1"}', 3, "自定义媒体设备数候选(JSON)"),
        # fonts 字体 (JSON数组)
        ("fonts", '["Arial","Calibri","Cambria","Times New Roman"],["Arial","Helvetica","sans-serif","Georgia"],["all"]', 5, "字体候选池(JSON数组)"),
    ]
    for param_name, param_value, weight, remark in fingerprint_defaults:
        existing = FingerprintPool.query.filter_by(param_name=param_name).first()
        if not existing:
            # 自动生成等权权重
            num_values = len([v.strip() for v in param_value.split(",") if v.strip()])
            default_weights = ",".join(["5"] * num_values)
            item = FingerprintPool(
                param_name=param_name, param_value=param_value,
                param_weights=default_weights, weight=weight, remark=remark
            )
            db.session.add(item)
            results["fingerprint_items"] += 1

    db.session.commit()
    return jsonify({
        "code": 0,
        "data": results,
        "msg": f"默认配置已初始化：{results['general_configs']}个通用配置，{results['fingerprint_items']}个指纹候选项",
    })
