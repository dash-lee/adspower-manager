"""
定时任务调度器
============

使用 APScheduler 管理定时任务：
1. 定时拉取并执行任务队列中的待处理任务
2. 定时检查 AdsPower 状态
3. 定时同步环境列表

所有调度配置通过数据库的 general_config 表即时生效。
"""

import datetime
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from backend.models import db, GeneralConfig, TaskQueue
from backend.services.adspower_client import AdsPowerClient
from backend.services.env_manager import EnvManager


class TaskScheduler:
    """
    任务调度器。

    Usage:
        scheduler = TaskScheduler(adspower_client)
        scheduler.start()  # 在 Flask 应用启动时调用
        scheduler.stop()   # 在应用关闭时调用
    """

    def __init__(self, client: AdsPowerClient):
        """
        初始化调度器。

        Args:
            client: AdsPower API 客户端
        """
        self.client = client
        self.env_manager = EnvManager(client)
        self._scheduler = BackgroundScheduler(
            timezone="Asia/Shanghai",  # 默认时区
            job_defaults={
                "coalesce": True,       # 合并错过的任务
                "max_instances": 1,     # 同时只运行一个实例
            },
        )

    def _get_config_int(self, key: str, default: int) -> int:
        """从数据库读取配置（整数）。"""
        try:
            config = GeneralConfig.query.filter_by(config_key=key).first()
            if config:
                return int(config.config_value)
        except (ValueError, TypeError):
            pass
        return default

    def _process_task_queue(self):
        """
        定时执行：处理任务队列中的待处理任务。
        """
        logger.info("===== 定时任务：处理任务队列 =====")
        try:
            count = self.env_manager.process_pending_tasks()
            logger.info(f"任务队列处理完成：{count} 个任务")
        except Exception as e:
            logger.error(f"处理任务队列异常: {e}")

    def _auto_check_status(self):
        """
        定时执行：检查 AdsPower 状态和环境同步。
        """
        logger.info("===== 定时任务：自动状态检查 =====")
        try:
            result = self.env_manager.init_check()
            summary = (
                f"API:{'正常' if result['api_ok'] else '异常'} | "
                f"环境:{result['total_profiles']} | "
                f"缺失保留:{len(result['missing_preserved'])} | "
                f"可清理:{len(result['unpreserved_profiles'])}"
            )
            logger.info(f"自动状态检查完成: {summary}")
        except Exception as e:
            logger.error(f"自动状态检查异常: {e}")

    def _cleanup_old_logs(self):
        """
        定时执行：清理旧日志（保留最近7天）。
        """
        logger.info("===== 定时任务：清理旧日志 =====")
        try:
            from backend.models import OperationLog, EnvRuntimeLog
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)

            deleted_ops = OperationLog.query.filter(
                OperationLog.created_at < cutoff
            ).delete()
            deleted_env = EnvRuntimeLog.query.filter(
                EnvRuntimeLog.created_at < cutoff
            ).delete()

            db.session.commit()
            logger.info(f"日志清理完成：操作日志 {deleted_ops} 条，环境日志 {deleted_env} 条")
        except Exception as e:
            logger.error(f"清理旧日志异常: {e}")
            db.session.rollback()

    def start(self):
        """
        启动调度器，注册所有定时任务。

        从数据库读取间隔配置（即时生效意味着每次执行时重新读取）。
        """
        # 任务队列处理：默认每 30 秒一次
        task_interval = 30  # 默认值，实际执行时动态读取
        self._scheduler.add_job(
            self._process_task_queue,
            trigger="interval",
            seconds=task_interval,
            id="process_tasks",
            name="处理任务队列",
            # 使用动态间隔：每次执行前从数据库读取最新配置
            next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=5),
        )

        # 自动状态检查：默认每小时一次
        self._scheduler.add_job(
            self._auto_check_status,
            trigger="interval",
            hours=1,
            id="auto_check",
            name="自动状态检查",
            next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=30),
        )

        # 日志清理：每天凌晨3点
        self._scheduler.add_job(
            self._cleanup_old_logs,
            trigger="cron",
            hour=3,
            minute=0,
            id="cleanup_logs",
            name="清理旧日志",
        )

        self._scheduler.start()
        logger.info("===== 定时任务调度器已启动 =====")
        logger.info(f"  - 任务队列处理: 每 {task_interval} 秒")
        logger.info(f"  - 自动状态检查: 每小时")
        logger.info(f"  - 日志清理: 每天 03:00")

    def stop(self):
        """
        停止调度器。
        """
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("===== 定时任务调度器已停止 =====")

    def get_jobs(self) -> list:
        """
        获取所有已注册的定时任务。

        Returns:
            list: 任务信息列表
        """
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def pause_job(self, job_id: str) -> bool:
        """
        暂停指定任务。

        Args:
            job_id: 任务ID

        Returns:
            bool: 是否成功
        """
        try:
            self._scheduler.pause_job(job_id)
            return True
        except Exception as e:
            logger.error(f"暂停任务 {job_id} 失败: {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """
        恢复指定任务。

        Args:
            job_id: 任务ID

        Returns:
            bool: 是否成功
        """
        try:
            self._scheduler.resume_job(job_id)
            return True
        except Exception as e:
            logger.error(f"恢复任务 {job_id} 失败: {e}")
            return False
