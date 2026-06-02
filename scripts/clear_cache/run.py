"""
清除缓存脚本
============

清除指定环境的浏览器缓存数据（local_storage, cookie, history 等）。

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

from typing import Any, Dict


def run(context: Dict[str, Any]) -> Dict[str, Any]:
    """执行清除缓存。"""
    log_step = context["log_step"]
    client = context["client"]
    params = context["params"]

    log_step(1, "▶️ 开始清除所有环境缓存...")
    # 获取所有环境并逐个清除缓存
    all_profiles = client.get_all_profiles()
    success_count = 0
    for p in all_profiles:
        pid = p.get("profile_id", "")
        if pid:
            try:
                client.clear_cache(pid)
                success_count += 1
                log_step(1, f"  ✅ {p.get('name', pid)} 缓存已清除")
            except Exception as e:
                log_step(1, f"  ⚠️ {p.get('name', pid)} 清除失败: {e}")

    resp = client.delete_cache([profile_id])

    if resp.get("code") == 0:
        log_step(2, f"✅ 缓存清除成功", "success", detail=resp)
        log_step(999, f"🏁 清除完成", "end")
        return {"success": True, "profile_id": profile_id}
    else:
        error_msg = resp.get("msg", "清除缓存失败")
        log_step(2, f"❌ 清除失败: {error_msg}", "error", detail=resp)
        log_step(999, f"🏁 清除失败", "end")
        return {"success": False, "error": error_msg}
