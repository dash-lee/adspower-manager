"""
定时任务调度器
============

使用 APScheduler 管理定时任务：
1. 定时拉取并执行任务队列中的待处理任务
2. 定时检查 AdsPower 状态
3. 定时同步环境列表

所有调度配置通过数据库的 general_config 表即时生效。
每次执行时动态读取配置，无需重启。
"""

import datetime
import time
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from backend.models import db, GeneralConfig, TaskQueue
from backend.services.adspower_client import AdsPowerClient
from backend.services.env_manager import EnvManager


class TaskScheduler:
    """
    任务调度器。

    关键设计：
    - APScheduler 以固定频率触发（每秒一次）
    - 每次触发时从数据库读取间隔配置，决定是否真正执行
    - 这样配置修改后无需重启即可生效

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
            timezone="Asia/Shanghai",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
            },
        )
        # 上次执行时间（用于动态间隔控制）
        self._last_task_run = 0.0
        self._last_check_run = 0.0

    def _get_config_int(self, key: str, default: int) -> int:
        """从数据库读取配置（整数），即时生效。"""
        try:
            config = GeneralConfig.query.filter_by(config_key=key).first()
            if config and config.config_value:
                return int(config.config_value)
        except (ValueError, TypeError):
            pass
        return default

    def _get_config_str(self, key: str, default: str) -> str:
        """从数据库读取配置（字符串），即时生效。"""
        try:
            config = GeneralConfig.query.filter_by(config_key=key).first()
            if config and config.config_value:
                return config.config_value
        except Exception:
            pass
        return default

    def _should_run_task_queue(self) -> bool:
        """
        检查是否应该执行任务队列处理。
        根据数据库中的 task_poll_interval 配置决定。
        """
        interval = self._get_config_int("task_poll_interval", 30)
        now = time.time()
        if now - self._last_task_run >= interval:
            self._last_task_run = now
            return True
        return False

    def _should_run_auto_check(self) -> bool:
        """
        检查是否应该执行自动状态检查。
        根据数据库中的 auto_check_interval 配置决定。
        """
        interval = self._get_config_int("auto_check_interval", 3600)
        now = time.time()
        if now - self._last_check_run >= interval:
            self._last_check_run = now
            return True
        return False

    def _process_task_queue(self):
        """
        定时执行：处理任务队列中的待处理任务。
        会先检查动态间隔。
        """
        if not self._should_run_task_queue():
            return
        # 读取当前 max_env_limit 配置
        limit = self._get_config_int("max_env_limit", 100)
        logger.info(f"===== 定时任务：处理任务队列（上限={limit}）=====")
        try:
            count = self.env_manager.process_pending_tasks()
            logger.info(f"任务队列处理完成：{count} 个任务")
        except Exception as e:
            logger.error(f"处理任务队列异常: {e}")

    def _auto_check_status(self):
        """
        定时执行：检查 AdsPower 状态和环境同步。
        会先检查动态间隔。
        """
        if not self._should_run_auto_check():
            return
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
        定时执行：清理旧日志。
        根据 log_retention_days 配置决定保留天数。
        """
        retention_days = self._get_config_int("log_retention_days", 7)
        logger.info(f"===== 定时任务：清理旧日志（保留{retention_days}天）=====")
        try:
            from backend.models import OperationLog, EnvRuntimeLog
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)

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
        所有任务以固定频率触发，内部通过动态间隔控制。
        """
        # 任务队列处理：固定每秒检查一次，内部按配置间隔跳过
        self._scheduler.add_job(
            self._process_task_queue,
            trigger="interval",
            seconds=1,  # 高频检查，实际间隔由 _should_run_task_queue 控制
            id="process_tasks",
            name="处理任务队列",
            next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=5),
        )

        # 自动状态检查：固定每60秒检查一次，内部按配置间隔跳过
        self._scheduler.add_job(
            self._auto_check_status,
            trigger="interval",
            seconds=60,
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

        # 读取当前配置用于日志
        task_int = self._get_config_int("task_poll_interval", 30)
        check_int = self._get_config_int("auto_check_interval", 3600)
        log_days = self._get_config_int("log_retention_days", 7)

        logger.info("===== 定时任务调度器已启动 =====")
        logger.info(f"  - 任务队列处理: 每 {task_int} 秒（配置键: task_poll_interval）")
        logger.info(f"  - 自动状态检查: 每 {check_int} 秒（配置键: auto_check_interval）")
        logger.info(f"  - 日志清理: 每天 03:00，保留 {log_days} 天（配置键: log_retention_days）")
        logger.info(f"  ℹ️  以上间隔可通过「配置管理 → 通用配置」即时修改，无需重启")

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
