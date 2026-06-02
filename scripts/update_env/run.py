"""
更新环境脚本
============

更新现有 AdsPower 浏览器环境的配置。
一次只能更新一个环境。

调用方式：
    run(context)
    
    context = {
        "execution_id": str,
        "params": dict,
        "log_step": callable,
        "client": AdsPowerClient,
        "manager": EnvManager,
    }
"""

import json
from typing import Any, Dict


def run(context: Dict[str, Any]) -> Dict[str, Any]:
    """执行更新环境。"""
    log_step = context["log_step"]
    manager = context["manager"]
    params = context["params"]

    profile_id = params.get("profile_id", "")
    if not profile_id:
        log_step(1, "❌ 缺少必填参数: profile_id", "error")
        return {"success": False, "error": "profile_id 不能为空"}

    log_step(1, f"▶️ 开始更新环境: {profile_id}", "start")

    result = manager.update_environment(
        profile_id=profile_id,
        name=params.get("name") or None,
        proxy_id=params.get("proxy_id") or None,
        remark=params.get("remark") or None,
    )

    if result.get("success"):
        log_step(2, f"✅ 环境 {profile_id} 更新成功: {result.get('updated_fields', [])}",
                 "success", detail=json.dumps(result, ensure_ascii=False))
    else:
        log_step(2, f"❌ 更新失败: {result.get('error', '未知错误')}",
                 "error", detail=json.dumps(result, ensure_ascii=False))

    log_step(999, f"🏁 更新完成", "end")
    return result
