"""
创建环境脚本
============

在 AdsPower 中创建新的浏览器环境。
支持批量创建、随机指纹、代理配置等。

调用方式：
    run(context)
    
    context = {
        "execution_id": str,      # 执行批次ID
        "params": dict,           # 参数（来自 config.json）
        "log_step": callable,     # 记录步骤: (step_index, message, step_type, detail, profile_id)
        "client": AdsPowerClient, # AdsPower API 客户端
        "manager": EnvManager,    # 环境管理器
    }
"""

import json
import datetime
from typing import Any, Dict


def run(context: Dict[str, Any]) -> Dict[str, Any]:
    """执行创建环境。"""
    log_step = context["log_step"]
    client = context["client"]
    manager = context["manager"]
    params = context["params"]

    count = int(params.get("count", 1))
    prefix = params.get("env_name", "Auto")

    log_step(1, f"▶️ 开始创建环境，数量: {count}", "start",
             {"prefix": prefix, "count": count})

    results = []
    for i in range(count):
        env_name = f"{prefix}_{i+1}" if count > 1 else prefix
        step = i + 2

        log_step(step, f"🚀 正在创建第 {i+1}/{count} 个环境: {env_name}", "api_call")

        result = manager.create_environment(
            env_name=env_name,
            group_id=params.get("group_id", "0"),
            proxy_id=params.get("proxy_id") or None,
            open_url=params.get("open_url") or None,
        )

        if result.get("success"):
            log_step(step, f"✅ 环境 [{env_name}] 创建成功 (ID: {result['profile_id']})",
                     "success", detail=json.dumps(result, ensure_ascii=False))
        else:
            log_step(step, f"❌ 环境 [{env_name}] 创建失败: {result.get('error', '未知错误')}",
                     "error", detail=json.dumps(result, ensure_ascii=False))
        results.append(result)

    success = sum(1 for r in results if r.get("success"))
    log_step(999, f"🏁 创建完成: {success}/{count} 成功", "end",
             {"total": count, "success": success})

    return {"success": success > 0, "results": results, "total": count, "success_count": success}
