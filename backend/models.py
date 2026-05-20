"""
数据模型定义
===========

包含所有数据库表的结构定义，按功能分为以下几类：
1. 通用配置表 (general_config)        - 系统级别的全局参数
2. 代理配置表 (proxy_config)          - 代理服务器的配置信息
3. 指纹随机池表 (fingerprint_pool)    - 创建环境时可随机选取的指纹参数池
4. 环境保留表 (preserved_env)         - 需要保留不被删除的环境
5. 任务队列表 (task_queue)            - 待执行/已执行的任务记录
6. 操作日志表 (operation_log)         - 系统操作日志（API调用、错误等）
7. 环境运行日志表 (env_runtime_log)   - 单个环境的运行记录（IP、运行时间等）
"""

import datetime
from backend.database import db


class GeneralConfig(db.Model):
    """
    通用配置表
    ==========

    存储系统级别的全局参数，以 key-value 形式保存。
    所有配置修改后即时生效（服务层每次读取最新值）。

    表名: general_config
    """
    __tablename__ = "general_config"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 配置键名，例如 "adspower_api_url"
    config_key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    # 配置值，所有值以字符串形式存储，使用时按需转换
    config_value = db.Column(db.Text, nullable=False, default="")
    # 配置说明/备注
    remark = db.Column(db.Text, nullable=False, default="")
    # 配置类别：general, proxy, fingerprint, environment
    category = db.Column(db.String(64), nullable=False, default="general")
    # 更新时间
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<GeneralConfig {self.config_key}={self.config_value}>"


class ProxyConfig(db.Model):
    """
    代理配置表
    ==========

    存储代理服务器的连接信息。
    创建环境时，proxyid 是必填选项，从该表中选取。

    表名: proxy_config
    """
    __tablename__ = "proxy_config"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 代理在 AdsPower 中的 proxy_id（通过 API 创建代理后获取）
    ads_proxy_id = db.Column(db.String(64), nullable=True, index=True, comment="AdsPower 中的代理ID")
    # 代理名称（便于识别）
    name = db.Column(db.String(128), nullable=False, default="")
    # 代理软件类型: brightdata, oxylabsauto, other, no_proxy 等
    proxy_soft = db.Column(db.String(64), nullable=False, default="other")
    # 代理类型: http, https, socks5
    proxy_type = db.Column(db.String(16), nullable=False, default="socks5")
    # 代理主机地址
    proxy_host = db.Column(db.String(256), nullable=False, default="")
    # 代理端口
    proxy_port = db.Column(db.String(16), nullable=False, default="")
    # 代理用户名
    proxy_user = db.Column(db.String(256), nullable=False, default="")
    # 代理密码
    proxy_password = db.Column(db.String(256), nullable=False, default="")
    # 是否启用此代理 (1=启用, 0=禁用)
    enabled = db.Column(db.Integer, nullable=False, default=1)
    # 备注
    remark = db.Column(db.Text, nullable=False, default="")
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    # 更新时间
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<ProxyConfig {self.name} ({self.proxy_host}:{self.proxy_port})>"

    def to_api_payload(self) -> dict:
        """
        将代理配置转换为 AdsPower API 的 user_proxy_config 格式。

        Returns:
            dict: 符合 AdsPower API 格式的代理配置对象
        """
        return {
            "proxy_soft": self.proxy_soft,
            "proxy_type": self.proxy_type,
            "proxy_host": self.proxy_host,
            "proxy_port": self.proxy_port,
            "proxy_user": self.proxy_user,
            "proxy_password": self.proxy_password,
        }


class FingerprintPool(db.Model):
    """
    指纹随机池表
    ============

    存储创建环境时可随机选取的指纹参数候选值。
    创建环境时，系统从各参数的候选池中随机抽取一个值，
    组装成 fingerprint_config 传给 AdsPower API。

    表名: fingerprint_pool
    """
    __tablename__ = "fingerprint_pool"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 参数名称: screen_resolution, fonts, hardware_concurrency, device_memory, media_devices
    param_name = db.Column(db.String(64), nullable=False, index=True, comment="指纹参数名称")
    # 候选值 (字符串形式)
    param_value = db.Column(db.Text, nullable=False, comment="候选值")
    # 权重: 数值越大被选中的概率越高（1-10）
    weight = db.Column(db.Integer, nullable=False, default=1, comment="随机权重 1-10")
    # 是否启用 (1=启用, 0=禁用)
    enabled = db.Column(db.Integer, nullable=False, default=1)
    # 备注说明
    remark = db.Column(db.Text, nullable=False, default="")
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<FingerprintPool {self.param_name}={self.param_value}>"


class PreservedEnv(db.Model):
    """
    环境保留表
    ==========

    存储需要保留不被自动删除的环境ID和名称。
    初始化脚本会检查：
    1. 表中配置的环境是否在 AdsPower 中实际存在
    2. AdsPower 中未被标记保留的环境是否可以被清理

    表名: preserved_env
    """
    __tablename__ = "preserved_env"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # AdsPower 环境ID（profile_id）
    profile_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    # 环境名称（用于识别）
    env_name = db.Column(db.String(256), nullable=False, default="")
    # 备注
    remark = db.Column(db.Text, nullable=False, default="")
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<PreservedEnv {self.env_name} ({self.profile_id})>"


class TaskQueue(db.Model):
    """
    任务队列表
    ==========

    存储待执行的任务，支持按顺序处理。
    任务类型: create_env（创建环境）, delete_env（删除环境）, 
             update_env（更新环境）, check_status（检查状态）

    表名: task_queue
    """
    __tablename__ = "task_queue"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 任务类型
    task_type = db.Column(
        db.String(32),
        nullable=False,
        index=True,
        comment="任务类型: create_env / delete_env / update_env / check_status"
    )
    # 任务参数（JSON 字符串）
    params = db.Column(db.Text, nullable=False, default="{}", comment="任务参数 JSON")
    # 任务状态: pending / running / completed / failed / cancelled
    status = db.Column(
        db.String(16),
        nullable=False,
        default="pending",
        index=True,
        comment="任务状态"
    )
    # 优先级: 数值越小优先级越高
    priority = db.Column(db.Integer, nullable=False, default=0)
    # 失败重试次数
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    # 最大重试次数
    max_retries = db.Column(db.Integer, nullable=False, default=3)
    # 执行结果/错误信息
    result_msg = db.Column(db.Text, nullable=True)
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    # 开始执行时间
    started_at = db.Column(db.DateTime, nullable=True)
    # 完成时间
    completed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<TaskQueue {self.task_type} [{self.status}]>"


class OperationLog(db.Model):
    """
    操作日志表
    ==========

    记录系统级别的操作日志，包括 API 调用、错误信息、系统事件等。
    支持按级别（INFO/WARNING/ERROR）和模块进行过滤。

    表名: operation_log
    """
    __tablename__ = "operation_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 日志级别: INFO / WARNING / ERROR / DEBUG
    level = db.Column(db.String(16), nullable=False, default="INFO", index=True)
    # 日志来源模块: adspower_client / env_manager / scheduler / system
    module = db.Column(db.String(64), nullable=False, default="system", index=True)
    # 日志消息内容
    message = db.Column(db.Text, nullable=False)
    # 详细数据（JSON 格式，用于记录 API 请求/响应等）
    detail = db.Column(db.Text, nullable=True)
    # 记录时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    def __repr__(self):
        return f"<OperationLog [{self.level}] {self.module}: {self.message[:50]}>"


class EnvRuntimeLog(db.Model):
    """
    环境运行日志表
    ==============

    记录单个环境的运行信息，包括：
    - 从代理获取的 IP 地址
    - 浏览器运行时间
    - 启动/停止时间

    表名: env_runtime_log
    """
    __tablename__ = "env_runtime_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # AdsPower 环境ID
    profile_id = db.Column(db.String(64), nullable=False, index=True)
    # 环境名称
    env_name = db.Column(db.String(256), nullable=False, default="")
    # 事件类型: start / stop / error / ip_check
    event_type = db.Column(db.String(32), nullable=False, default="start", index=True)
    # 检测到的 IP 地址
    ip_address = db.Column(db.String(64), nullable=True, comment="检测到的IP地址")
    # 运行时长（秒），在 stop 事件时记录
    duration_seconds = db.Column(db.Integer, nullable=True, comment="运行时长(秒)")
    # 额外数据（JSON格式）
    extra_data = db.Column(db.Text, nullable=True)
    # 事件时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    def __repr__(self):
        return f"<EnvRuntimeLog {self.profile_id} [{self.event_type}]>"
