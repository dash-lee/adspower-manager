"""
脚本管理器
==========

负责扫描 scripts/ 目录下的脚本文件，读取 config.json，动态加载并执行。
每个脚本是一个子文件夹，内含 config.json（元数据+参数schema）和 run.py（执行逻辑）。

脚本分类（通过 config.json 的 category 字段区分）：
- standard（标准脚本）：创建环境、更新环境、清除缓存
- combo（组合脚本）：视频广告等
"""

import os
import json
import uuid
import datetime
import importlib.util
from typing import Optional
from loguru import logger

from backend.models import db, ExecutionStatus, ScriptRunLog


# 项目根目录
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(_PROJECT_DIR, "scripts")


class ScriptManager:
    """脚本管理器，扫描 scripts/ 目录并提供脚本生命周期管理。"""

    def __init__(self, app=None):
        self._app = app
        os.makedirs(SCRIPTS_DIR, exist_ok=True)

    # ============================================================
    # 扫描脚本目录
    # ============================================================

    def list_scripts(self, script_type: str = "standard") -> list:
        """
        扫描 scripts/ 目录，返回指定类型的脚本列表。

        读取每个子文件夹的 config.json，按 category 字段分类。

        Args:
            script_type: "standard" 或 "combo"

        Returns:
            list[dict]: 脚本信息列表
        """
        results = []
        if not os.path.exists(SCRIPTS_DIR):
            return results

        for name in sorted(os.listdir(SCRIPTS_DIR)):
            script_dir = os.path.join(SCRIPTS_DIR, name)
            if not os.path.isdir(script_dir):
                continue

            config_path = os.path.join(script_dir, "config.json")
            if not os.path.exists(config_path):
                continue

            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"读取脚本配置失败 {name}: {e}")
                continue

            # 按类型过滤
            cfg_type = config.get("category", "standard")
            if cfg_type != script_type and script_type != "all":
                continue

            results.append({
                "script_name": name,
                "display_name": config.get("display_name", name),
                "description": config.get("description", ""),
                "version": config.get("version", "1.0"),
                "category": cfg_type,
                "params": config.get("params", []),
            })

        return results

    def get_script_info(self, script_name: str) -> Optional[dict]:
        """获取单个脚本的详细信息（含参数 schema）。"""
        config_path = os.path.join(SCRIPTS_DIR, script_name, "config.json")
        if not os.path.exists(config_path):
            return None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            config["script_name"] = script_name
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"读取脚本 {script_name} 失败: {e}")
            return None

    # ============================================================
    # 执行脚本
    # ============================================================

    def _get_script_path(self, script_name: str) -> str:
        """获取脚本文件 run.py 的绝对路径。"""
        return os.path.join(SCRIPTS_DIR, script_name, "run.py")

    def execute_script(
        self,
        script_name: str,
        params: dict,
        task_name: str = "",
    ) -> dict:
        """
        执行指定脚本。

        流程：
        1. 生成 execution_id
        2. 读取 config.json 获取脚本信息
        3. 动态导入 run.py 并调用 run(context)
        4. 记录每一步日志到 ScriptRunLog 表
        5. 为每个线程创建 ExecutionStatus 记录

        Args:
            script_name:  脚本名称（文件夹名）
            params:       执行参数
            task_name:    任务名称

        Returns:
            dict: {"execution_id": str, "success": bool, "results": [...]}
        """
        from flask import current_app
        from backend.services.env_manager import EnvManager
        from backend.services.adspower_client import AdsPowerClient

        execution_id = uuid.uuid4().hex[:8]
        script_path = self._get_script_path(script_name)
        config = self.get_script_info(script_name)

        if not config:
            return {"execution_id": execution_id, "success": False, "error": "脚本不存在"}

        display_name = config.get("display_name", script_name)
        script_type = config.get("category", "standard")

        # 检查 run.py
        if not os.path.exists(script_path):
            self._log_step(execution_id, script_name, task_name, 0,
                           "❌ 脚本文件 run.py 不存在", "error")
            return {"execution_id": execution_id, "success": False, "error": "脚本文件不存在"}

        # 动态导入
        try:
            spec = importlib.util.spec_from_file_location(f"_script_{script_name}", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            self._log_step(execution_id, script_name, task_name, 0,
                           f"❌ 加载脚本失败: {str(e)}", "error")
            return {"execution_id": execution_id, "success": False, "error": f"加载脚本失败: {str(e)}"}

        if not hasattr(module, "run"):
            self._log_step(execution_id, script_name, task_name, 0,
                           "❌ 脚本缺少 run() 函数", "error")
            return {"execution_id": execution_id, "success": False, "error": "脚本缺少 run() 函数"}

        # 创建客户端和管理器
        client: AdsPowerClient = current_app.config["ADSPOWER_CLIENT"]
        manager = EnvManager(client)

        # 创建执行上下文
        context = {
            "execution_id": execution_id,
            "script_name": script_name,
            "task_name": task_name,
            "params": params,
            "client": client,
            "manager": manager,
            "log_step": lambda step, msg, st="info", detail=None, pid=None:
                self._log_step(execution_id, script_name, task_name,
                               int(step) if isinstance(step, (int, float)) else 0,
                               msg, st, detail, pid),
        }

        # 记录开始日志 + 创建执行状态
        status_entry = ExecutionStatus(
            execution_id=execution_id,
            script_name=script_name,
            script_type=script_type,
            thread_index=0,
            status="running",
            params=json.dumps(params, ensure_ascii=False),
            started_at=datetime.datetime.utcnow(),
        )
        db.session.add(status_entry)
        db.session.commit()

        self._log_step(execution_id, script_name, task_name, 0,
                       f"▶️ 开始执行「{display_name}」", "start")

        try:
            result = module.run(context)
            success = bool(result.get("success", False))

            status_entry.status = "completed" if success else "failed"
            if not success:
                status_entry.error_message = result.get("error", "执行失败")

            self._log_step(execution_id, script_name, task_name, 999,
                           f"✅ 执行完成" if success else f"❌ 执行失败",
                           "end" if success else "error",
                           json.dumps(result, ensure_ascii=False)[:1000])

            status_entry.completed_at = datetime.datetime.utcnow()
            db.session.commit()

            return {
                "execution_id": execution_id,
                "success": success,
                "results": [{
                    "success": success,
                    "thread_index": 0,
                    "error": result.get("error") if not success else None,
                }],
                "total": 1,
                "success_count": 1 if success else 0,
            }

        except Exception as e:
            error_msg = f"💥 脚本执行异常: {str(e)}"
            logger.error(error_msg)
            status_entry.status = "failed"
            status_entry.error_message = str(e)
            status_entry.completed_at = datetime.datetime.utcnow()
            db.session.commit()

            self._log_step(execution_id, script_name, task_name, 998,
                           error_msg, "error", {"traceback": str(e)[:500]})

            return {
                "execution_id": execution_id, "success": False,
                "results": [{"success": False, "thread_index": 0, "error": str(e)}],
                "total": 1, "success_count": 0,
            }

    # ============================================================
    # 日志记录
    # ============================================================

    def _log_step(self, execution_id, script_name, task_name, step_index,
                  message, step_type="info", detail=None, profile_id=None):
        """记录执行步骤到数据库。"""
        detail_str = json.dumps(detail, ensure_ascii=False) if detail else None
        try:
            log = ScriptRunLog(
                execution_id=execution_id,
                script_name=script_name,
                task_name=task_name,
                step_index=int(step_index),
                step_name=message,
                step_type=step_type,
                message=message,
                detail=detail_str,
                profile_id=profile_id,
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            logger.error(f"写入步骤日志失败: {e}")

    # ============================================================
    # 执行记录查询
    # ============================================================

    def get_execution_log(self, execution_id: str) -> list:
        """获取指定执行批次的所有步骤日志。"""
        logs = (ScriptRunLog.query
                .filter_by(execution_id=execution_id)
                .order_by(ScriptRunLog.step_index, ScriptRunLog.created_at)
                .all())
        return [{
            "step_index": l.step_index,
            "step_name": l.step_name,
            "step_type": l.step_type,
            "message": l.message,
            "detail": l.detail,
            "profile_id": l.profile_id,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs]

    def get_execution_status(self, execution_id: str) -> list:
        """获取指定执行批次的所有线程状态。"""
        records = (ExecutionStatus.query
                   .filter_by(execution_id=execution_id)
                   .order_by(ExecutionStatus.thread_index)
                   .all())
        return [{
            "id": r.id,
            "execution_id": r.execution_id,
            "script_name": r.script_name,
            "script_type": r.script_type,
            "thread_index": r.thread_index,
            "profile_id": r.profile_id,
            "env_name": r.env_name,
            "status": r.status,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in records]

    def list_execution_batches(
        self, page: int = 1, limit: int = 50,
        script_type: Optional[str] = None,
    ) -> dict:
        """分页列出所有执行批次（按执行ID分组）。"""
        query = db.session.query(ExecutionStatus.execution_id)
        if script_type:
            query = query.filter(ExecutionStatus.script_type == script_type)

        total_query = db.session.query(
            db.func.count(db.func.distinct(ExecutionStatus.execution_id))
        )
        if script_type:
            total_query = total_query.filter(ExecutionStatus.script_type == script_type)
        total = total_query.scalar() or 0

        subq = (db.session.query(
            ExecutionStatus.execution_id,
            db.func.max(ExecutionStatus.created_at).label("max_created")
        ))
        if script_type:
            subq = subq.filter(ExecutionStatus.script_type == script_type)
        subq = subq.group_by(ExecutionStatus.execution_id)
        subq = subq.order_by(db.desc("max_created"))
        subq = subq.offset((page - 1) * limit).limit(limit).subquery()

        records = (ExecutionStatus.query
                    .filter(ExecutionStatus.execution_id.in_(
                        db.session.query(subq.c.execution_id)
                    ))
                    .order_by(ExecutionStatus.execution_id, ExecutionStatus.thread_index)
                    .all())

        from collections import OrderedDict
        groups = OrderedDict()
        for r in records:
            eid = r.execution_id
            if eid not in groups:
                groups[eid] = {
                    "execution_id": eid, "script_name": r.script_name,
                    "script_type": r.script_type, "total_threads": 0,
                    "completed_count": 0, "failed_count": 0,
                    "created_at": None, "started_at": None, "completed_at": None,
                }
            g = groups[eid]
            g["total_threads"] += 1
            if r.status == "completed": g["completed_count"] += 1
            if r.status == "failed": g["failed_count"] += 1
            if not g["created_at"] or (r.created_at and r.created_at < g["created_at"]):
                g["created_at"] = r.created_at
            if not g["started_at"] or (r.started_at and r.started_at < g["started_at"]):
                g["started_at"] = r.started_at
            if not g["completed_at"] or (r.completed_at and r.completed_at > g["completed_at"]):
                g["completed_at"] = r.completed_at

        batches = []
        for eid in [r[0] for r in db.session.query(subq.c.execution_id).all()]:
            if eid not in groups: continue
            g = groups[eid]
            status = "completed"
            if g["failed_count"] and g["failed_count"] > 0 and g["completed_count"] == 0:
                status = "failed"
            elif g["failed_count"] and g["failed_count"] > 0:
                status = "partial"
            batches.append({
                "execution_id": g["execution_id"], "script_name": g["script_name"],
                "script_type": g["script_type"], "total_threads": g["total_threads"],
                "completed_count": g["completed_count"], "failed_count": g["failed_count"],
                "status": status,
                "created_at": g["created_at"].isoformat() if g["created_at"] else None,
                "started_at": g["started_at"].isoformat() if g["started_at"] else None,
                "completed_at": g["completed_at"].isoformat() if g["completed_at"] else None,
            })

        return {"batches": batches, "total": total, "page": page, "limit": limit}
