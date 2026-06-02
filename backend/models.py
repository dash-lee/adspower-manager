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
    # 操作人（记录谁添加/修改了此配置）
    operator = db.Column(db.String(64), nullable=False, default="", comment="操作人")
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
    # 操作人（记录谁添加/修改了此配置）
    operator = db.Column(db.String(64), nullable=False, default="", comment="操作人")
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


class Video(db.Model):
    """
    视频管理表
    ==========

    存储手动添加的视频信息。
    今日访问次数通过 VideoVisitLog 按 IP 去重统计。

    表名: videos
    """
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 视频名称
    video_name = db.Column(db.String(256), nullable=False, comment="视频名称")
    # 视频链接
    video_url = db.Column(db.Text, nullable=False, comment="视频链接")
    # 所属网站（从通用配置 video_websites 中选择）
    website = db.Column(db.String(128), nullable=False, default="", comment="所属网站")
    # 账号名称（管理此视频所使用的账号）
    account_name = db.Column(db.String(128), nullable=False, default="", comment="账号名称")
    # 今日访问次数（通过 visit_log 统计）
    today_visits = db.Column(db.Integer, nullable=False, default=0, comment="今日访问次数")
    # 操作人
    operator = db.Column(db.String(64), nullable=False, default="", comment="操作人")
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    # 更新时间
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "video_name": self.video_name,
            "video_url": self.video_url,
            "website": self.website,
            "account_name": self.account_name,
            "today_visits": self.today_visits,
            "operator": self.operator,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Video {self.video_name}>"


class VideoVisitLog(db.Model):
    """
    视频访问日志表（IP 去重统计）
    =============================

    记录每个视频的每日访问 IP，用于统计今日独立访问数。
    每日凌晨可清理过期数据。

    表名: video_visit_log
    """
    __tablename__ = "video_visit_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False, index=True, comment="关联视频ID")
    ip_address = db.Column(db.String(64), nullable=False, comment="访问者IP")
    visit_date = db.Column(db.String(16), nullable=False, index=True, comment="访问日期 (YYYY-MM-DD)")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<VideoVisitLog video={self.video_id} ip={self.ip_address} date={self.visit_date}>"


class VideoDailyStats(db.Model):
    """
    视频每日访问统计表
    ==================

    每日凌晨 0 点由定时任务统计前一天的独立访问数据（按 IP 去重）。
    数据量较大时需分页查询，该表只记录聚合后的结果。

    表名: video_daily_stats
    索引: (stats_date, video_id) 复合索引加速查询
    """
    __tablename__ = "video_daily_stats"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 统计日期
    stats_date = db.Column(db.String(16), nullable=False, index=True, comment="统计日期 (YYYY-MM-DD)")
    # 视频ID
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False, comment="视频ID")
    # 视频名称（冗余存储，避免关联查询）
    video_name = db.Column(db.String(256), nullable=False, default="", comment="视频名称")
    # 所属网站（冗余存储）
    website = db.Column(db.String(128), nullable=False, default="", comment="所属网站")
    # 独立访问次数
    visit_count = db.Column(db.Integer, nullable=False, default=0, comment="独立访问次数（按IP去重）")
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.Index("idx_stats_date_video", "stats_date", "video_id"),  # 复合索引
    )

    def to_dict(self):
        return {
            "id": self.id,
            "stats_date": self.stats_date,
            "video_id": self.video_id,
            "video_name": self.video_name,
            "website": self.website,
            "visit_count": self.visit_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<VideoDailyStats {self.stats_date} video={self.video_id} visits={self.visit_count}>"


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
    param_value = db.Column(db.Text, nullable=False, comment="候选值（逗号分隔）")
    # 各候选值对应的权重（逗号分隔，与param_value一一对应）
    param_weights = db.Column(db.Text, nullable=False, default="", comment="各候选值权重（逗号分隔，与param_value一一对应）")
    # 权重: 数值越大被选中的概率越高（保留以兼容旧逻辑）
    weight = db.Column(db.Integer, nullable=False, default=1, comment="随机权重 1-10")
    # 是否启用 (1=启用, 0=禁用)
    enabled = db.Column(db.Integer, nullable=False, default=1)
    # 备注说明
    remark = db.Column(db.Text, nullable=False, default="")
    # 操作人（记录谁添加/修改了此配置）
    operator = db.Column(db.String(64), nullable=False, default="", comment="操作人")
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
    # 操作人（记录谁添加/修改了此配置）
    operator = db.Column(db.String(64), nullable=False, default="", comment="操作人")
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
        comment="任务类型: create_env / delete_env / update_env / check_status / script"
    )
    # 关联脚本名称（当 task_type='script' 时有效）
    script_name = db.Column(db.String(128), nullable=False, default="", comment="关联脚本名称")
    # 显示任务名称
    task_name = db.Column(db.String(128), nullable=False, default="", comment="显示任务名称")
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


class User(db.Model):
    """
    用户表
    ====

    存储后台管理系统的用户账号信息。
    支持角色：admin（管理员，可管理用户）/ user（普通用户）

    表名: users
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 用户名（登录用）
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # 密码哈希（werkzeug.security）
    password_hash = db.Column(db.String(256), nullable=False)
    # 角色: admin / user
    role = db.Column(db.String(16), nullable=False, default="user", index=True)
    # 页面权限（JSON数组字符串，如 '["dashboard","proxy"]'，admin 忽略此字段拥有全部权限）
    permissions = db.Column(db.Text, nullable=False, default="[]", comment="页面权限 JSON数组")
    # 是否启用 (1=启用, 0=禁用)
    is_active = db.Column(db.Integer, nullable=False, default=1)
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    # 更新时间
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"


class ScriptTask(db.Model):
    """
    脚本任务定义表
    ==============

    存储 scripts/ 目录下每个脚本的元信息，
    由 ScriptManager.list_scripts() 扫描时自动同步。

    表名: script_tasks
    """
    __tablename__ = "script_tasks"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 脚本名称（文件夹名）
    script_name = db.Column(db.String(128), unique=True, nullable=False, index=True, comment="脚本名称（文件夹名）")
    # 显示名称（UI展示用）
    display_name = db.Column(db.String(256), nullable=False, default="", comment="显示名称")
    # 功能描述
    description = db.Column(db.Text, nullable=False, default="", comment="脚本描述")
    # 版本号
    version = db.Column(db.String(16), nullable=False, default="1.0", comment="版本号")
    # 分类：environment / monitor / general
    category = db.Column(db.String(64), nullable=False, default="general", comment="分类")
    # 参数定义 JSON（对应 config.json 的 params 字段）
    param_schema = db.Column(db.Text, nullable=False, default="[]", comment="参数定义JSON")
    # 是否启用
    enabled = db.Column(db.Integer, nullable=False, default=1)
    # 创建/更新时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<ScriptTask {self.script_name} v{self.version}>"


class ScriptRunLog(db.Model):
    """
    脚本运行日志表
    ==============

    记录每次脚本执行的每一步详细信息，
    取代原 EnvRuntimeLog（标记为 deprecated）。

    表名: script_run_logs
    """
    __tablename__ = "script_run_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 执行批次ID（每次运行时生成UUID前8位）
    execution_id = db.Column(db.String(64), nullable=False, index=True, comment="执行批次ID")
    # 脚本名称
    script_name = db.Column(db.String(128), nullable=False, index=True, comment="脚本名称")
    # 任务名称
    task_name = db.Column(db.String(128), nullable=False, default="", comment="任务名称")
    # 步骤序号
    step_index = db.Column(db.Integer, nullable=False, default=0, comment="步骤序号")
    # 步骤名称
    step_name = db.Column(db.String(256), nullable=False, default="", comment="步骤名称")
    # 步骤类型: info/success/warning/error/api_call/start/end
    step_type = db.Column(db.String(32), nullable=False, default="info", comment="步骤类型")
    # 步骤消息（展示给用户看）
    message = db.Column(db.Text, nullable=False, default="", comment="步骤消息")
    # 详细数据（JSON格式）
    detail = db.Column(db.Text, nullable=True, comment="详细JSON数据")
    # 关联环境ID（可选）
    profile_id = db.Column(db.String(64), nullable=True, comment="关联环境ID")
    # 记录时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    def __repr__(self):
        return f"<ScriptRunLog {self.execution_id} ({self.step_type}) {self.message[:40]}>"


class ExecutionStatus(db.Model):
    """
    执行状态表
    ==========

    记录组合脚本/标准脚本中每个线程的执行状态。
    每个线程（一个环境）对应一条记录，包含开始/结束时间、状态、异常信息。

    表名: execution_status
    """
    __tablename__ = "execution_status"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 执行批次ID（每次执行时生成）
    execution_id = db.Column(db.String(64), nullable=False, index=True, comment="执行批次ID")
    # 脚本名称
    script_name = db.Column(db.String(128), nullable=False, index=True, comment="脚本名称")
    # 脚本类型: standard / combo
    script_type = db.Column(db.String(16), nullable=False, default="standard", comment="脚本类型: standard/combo")
    # 线程序号
    thread_index = db.Column(db.Integer, nullable=False, default=0, comment="线程序号")
    # 关联环境ID
    profile_id = db.Column(db.String(64), nullable=True, comment="关联环境ID")
    # 环境名称
    env_name = db.Column(db.String(256), nullable=False, default="", comment="环境名称")
    # 执行状态: pending / running / completed / failed
    status = db.Column(db.String(16), nullable=False, default="pending", index=True, comment="执行状态")
    # 执行参数（JSON）
    params = db.Column(db.Text, nullable=True, comment="执行参数JSON")
    # 错误信息
    error_message = db.Column(db.Text, nullable=True, comment="错误信息")
    # 开始时间
    started_at = db.Column(db.DateTime, nullable=True, comment="开始时间")
    # 完成时间
    completed_at = db.Column(db.DateTime, nullable=True, comment="完成时间")
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<ExecutionStatus {self.execution_id} #{self.thread_index} [{self.status}]>"


class AdminLog(db.Model):
    """
    管理员操作日志表
    ================

    记录管理员在后台的所有操作，
    包括修改配置、创建/删除环境、用户管理等。

    表名: admin_log
    """
    __tablename__ = "admin_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 操作用户名
    operator_username = db.Column(db.String(64), nullable=False, index=True, comment="操作用户名")
    # 操作描述（如 "修改通用配置: adspower_api_url"）
    action = db.Column(db.String(256), nullable=False, comment="操作描述")
    # 操作对象（如配置键、环境ID等）
    target = db.Column(db.String(256), nullable=False, default="", comment="操作对象")
    # 操作者 IP 地址
    ip_address = db.Column(db.String(64), nullable=False, default="", comment="操作者IP")
    # 详细信息（JSON 格式）
    detail = db.Column(db.Text, nullable=True)
    # 操作时间
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    def __repr__(self):
        return f"<AdminLog {self.operator_username}: {self.action}>"
