"""
定时任务调度器
============

使用 APScheduler 管理定时任务：
1. 定时检查 AdsPower 状态
2. 定时清理过期日志

所有调度配置通过数据库的 general_config 表即时生效。
每次执行时动态读取配置，无需重启。
"""

import datetime
import time
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from backend.models import db, GeneralConfig, VideoDailyStats, Video
from backend.services.adspower_client import AdsPowerClient
from backend.services.env_manager import EnvManager


class TaskScheduler:
    """
    任务调度器。

    关键设计：
    - APScheduler 以固定频率触发
    - 每次触发时从数据库读取间隔配置，决定是否真正执行
    - 这样配置修改后无需重启即可生效

    Usage:
        scheduler = TaskScheduler(adspower_client)
        scheduler.start()  # 在 Flask 应用启动时调用
        scheduler.stop()   # 在应用关闭时调用
    """

    def __init__(self, client: AdsPowerClient, app=None):
        """
        初始化调度器。

        Args:
            client: AdsPower API 客户端
            app: Flask 应用实例（用于在后台线程中访问数据库）
        """
        self.client = client
        self._app = app
        self.env_manager = EnvManager(client, app=app)
        self._scheduler = BackgroundScheduler(
            timezone="Asia/Shanghai",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
            },
        )
        self._last_task_run = 0.0
        self._last_check_run = 0.0

    def _get_config_int(self, key: str, default: int) -> int:
        """从数据库读取配置（整数），即时生效。"""
        try:
            with self._app.app_context():
                config = GeneralConfig.query.filter_by(config_key=key).first()
                if config and config.config_value:
                    return int(config.config_value)
        except (ValueError, TypeError):
            pass
        return default

    def _get_config_str(self, key: str, default: str) -> str:
        """从数据库读取配置（字符串），即时生效。"""
        try:
            with self._app.app_context():
                config = GeneralConfig.query.filter_by(config_key=key).first()
                if config and config.config_value:
                    return config.config_value
        except Exception:
            pass
        return default

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

    def _auto_check_status(self):
        """
        定时执行：检查 AdsPower 状态和环境同步。
        会先检查动态间隔。
        """
        if not self._should_run_auto_check():
            return
        logger.info("===== 定时任务：自动状态检查 =====")
        try:
            with self._app.app_context():
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
            with self._app.app_context():
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
            try:
                with self._app.app_context():
                    db.session.rollback()
            except Exception:
                pass

    def _aggregate_video_daily_stats(self):
        """
        视频每日访问统计（定时任务）。

        在每天凌晨 0:10 执行，统计前一天的独立 IP 访问数据，
        聚合后写入 video_daily_stats 表。
        """
        try:
            with self._app.app_context():
                from backend.models import VideoVisitLog
                from sqlalchemy import func

                yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                logger.info(f"===== 视频每日统计：{yesterday} =====")

                # 查询前一天所有视频的去重访问记录
                stats = (
                    db.session.query(
                        VideoVisitLog.video_id,
                        func.count(VideoVisitLog.id).label("visit_count"),
                    )
                    .filter(VideoVisitLog.visit_date == yesterday)
                    .group_by(VideoVisitLog.video_id)
                    .all()
                )

                if not stats:
                    logger.info(f"  {yesterday} 无访问记录")
                    return

                count = 0
                for row in stats:
                    video = Video.query.get(row.video_id)
                    if not video:
                        continue
                    # 检查是否已存在该日期的统计
                    existing = VideoDailyStats.query.filter_by(
                        stats_date=yesterday, video_id=row.video_id
                    ).first()
                    if existing:
                        existing.visit_count = row.visit_count
                    else:
                        record = VideoDailyStats(
                            stats_date=yesterday,
                            video_id=row.video_id,
                            video_name=video.video_name,
                            website=video.website,
                            visit_count=row.visit_count,
                        )
                        db.session.add(record)
                    count += 1

                db.session.commit()
                logger.info(f"  ✅ 已统计 {count} 个视频的 {yesterday} 访问数据")

        except Exception as e:
            logger.error(f"视频每日统计异常: {e}")
            try:
                with self._app.app_context():
                    db.session.rollback()
            except Exception:
                pass

    def start(self):
        """
        启动调度器，注册所有定时任务。
        所有任务以固定频率触发，内部通过动态间隔控制。
        """
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

        # 视频每日统计：每天凌晨0点10分统计前一天数据
        self._scheduler.add_job(
            self._aggregate_video_daily_stats,
            trigger="cron",
            hour=0,
            minute=10,
            id="video_daily_stats",
            name="视频每日统计",
        )

        self._scheduler.start()

        check_int = self._get_config_int("auto_check_interval", 3600)
        log_days = self._get_config_int("log_retention_days", 7)

        logger.info("===== 定时任务调度器已启动 =====")
        logger.info(f"  - 自动状态检查: 每 {check_int} 秒（配置键: auto_check_interval）")
        logger.info(f"  - 日志清理: 每天 03:00，保留 {log_days} 天（配置键: log_retention_days）")

    def stop(self):
        """停止调度器。"""
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
        """暂停指定任务。"""
        try:
            self._scheduler.pause_job(job_id)
            return True
        except Exception as e:
            logger.error(f"暂停任务 {job_id} 失败: {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """恢复指定任务。"""
        try:
            self._scheduler.resume_job(job_id)
            return True
        except Exception as e:
            logger.error(f"恢复任务 {job_id} 失败: {e}")
            return False
