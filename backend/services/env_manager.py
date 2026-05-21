"""
环境管理服务
===========

核心业务逻辑层，负责：
1. 初始化检查：验证 AdsPower API 状态、同步环境列表
2. 创建环境：从指纹池随机生成参数、调用 API 创建
3. 删除环境：批量删除（需检查是否开启）、保护保留环境
4. 更新环境：仅更新可更新的参数
5. 数据收集：记录环境运行日志（IP、运行时间等）

依赖：
- AdsPowerClient: API 通信层
- 数据库模型: 读取配置、写入日志
"""

import json
import random
import datetime
from typing import Optional, Callable
from loguru import logger

from backend.models import (
    db, GeneralConfig, ProxyConfig, FingerprintPool,
    PreservedEnv, TaskQueue, OperationLog, EnvRuntimeLog,
)
from backend.services.adspower_client import AdsPowerClient


class EnvManager:
    """
    环境管理器。

    封装了所有与环境管理相关的业务逻辑，
    包括创建、删除、更新、初始化检查等。
    """

    def __init__(self, client: AdsPowerClient):
        """
        初始化环境管理器。

        Args:
            client: AdsPower API 客户端实例
        """
        self.client = client

    # ============================================================
    # 配置读取方法（从数据库读取，即时生效）
    # ============================================================

    def _get_config(self, key: str, default: str = "") -> str:
        """
        从 general_config 表读取配置值（即时生效）。

        每次调用都直接查询数据库，确保配置修改后立即生效。

        Args:
            key:     配置键名
            default: 默认值（配置不存在时返回）

        Returns:
            str: 配置值
        """
        config = GeneralConfig.query.filter_by(config_key=key).first()
        return config.config_value if config else default

    def _get_config_int(self, key: str, default: int = 0) -> int:
        """读取整数配置。"""
        try:
            return int(self._get_config(key, str(default)))
        except (ValueError, TypeError):
            return default

    # ============================================================
    # 1. 初始化检查
    # ============================================================

    def init_check(self) -> dict:
        """
        系统初始化检查。

        执行以下检查：
        1. AdsPower API 接口是否可用
        2. 对比数据库中保留的环境与 AdsPower 实际环境列表
        3. 报告：配置中有但实际不存在的环境
        4. 报告：实际存在但未标记保留的环境（可清理）

        Returns:
            dict: {
                "api_ok": bool,                      # API 是否正常
                "api_message": str,                   # API 状态消息
                "total_profiles": int,                # AdsPower 中环境总数
                "preserved_count": int,               # 配置中保留的环境数
                "missing_preserved": list,            # 配置中有但实际不存在的
                "unpreserved_profiles": list,         # 实际存在但未标记保留的
                "active_profiles": list,              # 当前已启动的环境
            }
        """
        result = {
            "api_ok": False,
            "api_message": "",
            "total_profiles": 0,
            "preserved_count": 0,
            "missing_preserved": [],
            "unpreserved_profiles": [],
            "active_profiles": [],
        }

        # 1.1 检查 API 状态
        logger.info("===== 初始化检查：API 状态 =====")
        result["api_ok"] = self.client.check_status()
        result["api_message"] = "API 接口正常" if result["api_ok"] else "API 接口不可用"

        if not result["api_ok"]:
            self._log_operation("ERROR", "init_check", "AdsPower API 不可用，无法继续检查")
            return result

        # 1.2 获取所有环境
        logger.info("===== 初始化检查：获取环境列表 =====")
        all_profiles = self.client.get_all_profiles()
        result["total_profiles"] = len(all_profiles)
        # 构建 profile_id -> profile_info 的映射
        ads_profile_map = {p.get("profile_id", ""): p for p in all_profiles if p.get("profile_id")}

        # 1.3 获取所有保留的环境配置
        preserved_envs = PreservedEnv.query.all()
        result["preserved_count"] = len(preserved_envs)

        # 1.4 检查保留环境中哪些在 AdsPower 中不存在
        for pe in preserved_envs:
            if pe.profile_id not in ads_profile_map:
                result["missing_preserved"].append({
                    "profile_id": pe.profile_id,
                    "env_name": pe.env_name,
                })
                logger.warning(f"保留环境 {pe.env_name} ({pe.profile_id}) 在 AdsPower 中不存在！")

        # 1.5 找出未标记保留的环境（可清理）
        preserved_ids = {pe.profile_id for pe in preserved_envs}
        for pid, pinfo in ads_profile_map.items():
            if pid not in preserved_ids:
                result["unpreserved_profiles"].append({
                    "profile_id": pid,
                    "env_name": pinfo.get("name", ""),
                    "group_id": pinfo.get("group_id", ""),
                })

        # 1.6 获取当前已启动的环境
        logger.info("===== 初始化检查：获取已启动环境 =====")
        active_resp = self.client.get_local_active()
        if active_resp.get("code") == 0:
            result["active_profiles"] = active_resp.get("data", {}).get("list", [])

        # 1.7 记录日志
        summary = (
            f"初始化检查完成 | API:{'正常' if result['api_ok'] else '异常'} | "
            f"环境总数:{result['total_profiles']} | "
            f"保留:{result['preserved_count']} | "
            f"缺失保留:{len(result['missing_preserved'])} | "
            f"可清理:{len(result['unpreserved_profiles'])} | "
            f"已启动:{len(result['active_profiles'])}"
        )
        self._log_operation("INFO", "init_check", summary, detail=json.dumps(result, ensure_ascii=False))

        return result

    # ============================================================
    # 2. 随机指纹生成
    # ============================================================

    def generate_fingerprint(self) -> dict:
        """
        从指纹池中随机生成 fingerprint_config 对象。

        读取 fingerprint_pool 表中所有启用的参数候选值，
        按权重随机选取，组装成完整的指纹配置。

        需要随机化的参数（用户指定）：
        - screen_resolution: 屏幕分辨率（如 "1920x1080" 格式，下划线分隔）
        - fonts: 字体列表
        - hardware_concurrency: CPU 核心数
        - device_memory: 内存大小
        - media_devices: 媒体设备数量

        其他参数使用 AdsPower 默认值。

        Returns:
            dict: fingerprint_config 对象（可直接传给 AdsPower API）
        """
        # 基础指纹配置（使用 AdsPower 推荐的默认值）
        config = {
            "automatic_timezone": "1",       # 基于IP自动时区
            "webrtc": "disabled",            # 禁用 WebRTC（防泄露）
            "location": "ask",               # 位置信息询问
            "location_switch": "1",          # 基于IP自动位置
            "language_switch": "1",          # 基于IP自动语言
            "page_language_switch": "1",     # 基于语言自动界面语言
            "canvas": "1",                   # Canvas 添加噪音
            "webgl_image": "1",              # WebGL 图像添加噪音
            "webgl": "3",                    # WebGL 随机匹配
            "audio": "1",                    # 音频添加噪音
            "do_not_track": "default",       # DNT 默认
            "flash": "block",                # Flash 禁用
            "scan_port_type": "1",           # 端口扫描保护
            "client_rects": "1",             # ClientRects 添加噪音
            "device_name_switch": "1",       # 掩盖设备名称
            "speech_switch": "1",            # SpeechVoices 添加噪音
        }

        # 从指纹池中随机选取各参数
        param_names = [
            "screen_resolution",
            "fonts",
            "hardware_concurrency",
            "device_memory",
            "media_devices",
            "media_devices_num",
        ]

        for param_name in param_names:
            # 查询该参数的所有启用候选值
            candidates = (
                FingerprintPool.query
                .filter_by(param_name=param_name, enabled=1)
                .all()
            )
            if not candidates:
                continue

            # 按权重随机选择
            if len(candidates) == 1:
                chosen = candidates[0]
            else:
                # 构建加权选择列表
                # 重复每个候选项 weight 次，然后随机抽取
                weighted_pool = []
                for c in candidates:
                    weighted_pool.extend([c] * max(1, c.weight))
                chosen = random.choice(weighted_pool)

            # 根据参数类型解析值
            value = self._parse_pool_value(param_name, chosen.param_value)
            if value is not None:
                config[param_name] = value

        logger.info(f"生成随机指纹配置: screen={config.get('screen_resolution')}, "
                     f"cpu={config.get('hardware_concurrency')}, "
                     f"mem={config.get('device_memory')}")

        return config

    def _parse_pool_value(self, param_name: str, raw_value: str):
        """
        解析指纹池中的值，转换为对应类型。

        Args:
            param_name: 参数名称
            raw_value:  数据库中存储的原始字符串值

        Returns:
            解析后的值（str/list/dict/...）
        """
        # 字体是列表类型，在数据库中以 JSON 数组存储
        if param_name == "fonts":
            try:
                parsed = json.loads(raw_value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                # 如果解析失败，当作逗号分隔的字符串处理
                return [f.strip() for f in raw_value.split(",") if f.strip()]
            return [raw_value]

        # media_devices_num 是 JSON 对象
        if param_name == "media_devices_num":
            try:
                parsed = json.loads(raw_value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            return raw_value

        # 其他参数直接使用字符串
        return raw_value

    # ============================================================
    # 3. 创建环境
    # ============================================================

    def create_environment(
        self,
        env_name: Optional[str] = None,
        group_id: str = "0",
        proxy_id: Optional[str] = None,
        use_random_fingerprint: bool = True,
        custom_fingerprint: Optional[dict] = None,
        open_url: Optional[str] = None,
    ) -> dict:
        """
        创建单个浏览器环境。

        流程：
        1. 如果没有指定代理ID，从数据库中选择一个启用的代理
        2. 生成随机指纹配置（或使用指定配置）
        3. 调用 AdsPower API 创建环境
        4. 记录创建日志

        Args:
            env_name:              环境名称
            group_id:              分组ID（默认 "0"）
            proxy_id:              代理ID（可选，未指定则从代理配置中选择）
            use_random_fingerprint: 是否使用随机指纹（默认 True）
            custom_fingerprint:     自定义指纹配置（可选）
            open_url:               初始打开URL（可选）

        Returns:
            dict: {
                "success": bool,
                "profile_id": str,    # 创建成功时返回
                "profile_no": str,    # 创建成功时返回
                "fingerprint": dict,  # 使用的指纹配置
                "error": str,         # 失败时的错误信息
            }
        """
        # 3.0 检查环境数量上限
        max_limit = self._get_config_int("max_env_limit", 100)
        all_profiles = self.client.get_all_profiles()
        current_count = len(all_profiles)
        if current_count >= max_limit:
            error_msg = f"环境数量已达上限 ({current_count}/{max_limit})，无法创建新环境。请在配置管理中调高 max_env_limit。"
            logger.warning(error_msg)
            return {
                "success": False,
                "profile_id": None,
                "profile_no": None,
                "fingerprint": {},
                "error": error_msg,
            }

        # 3.1 读取默认分组ID（如果未指定）
        if not group_id or group_id == "0":
            default_group = self._get_config("default_group_id", "0")
            if default_group and default_group != "0":
                group_id = default_group

        # 3.2 选择代理
        if not proxy_id:
            proxy = self._select_proxy()
            if proxy:
                if proxy.ads_proxy_id:
                    proxy_id = proxy.ads_proxy_id
                else:
                    # 如果没有 ads_proxy_id，直接使用代理配置
                    pass  # 下面会构建 user_proxy_config

        # 3.3 生成指纹配置
        if use_random_fingerprint and not custom_fingerprint:
            fingerprint = self.generate_fingerprint()
        elif custom_fingerprint:
            fingerprint = custom_fingerprint
        else:
            fingerprint = self.generate_fingerprint()

        # 3.4 构建创建请求
        # 构建环境名称
        if not env_name:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            env_name = f"Auto_{timestamp}"

        # 构建打开URL
        open_urls = [open_url] if open_url else None

        # 获取代理配置
        user_proxy_config = None
        if not proxy_id and proxy:
            user_proxy_config = proxy.to_api_payload()

        # 3.5 调用 API 创建
        resp = self.client.create_profile(
            group_id=group_id,
            fingerprint_config=fingerprint,
            name=env_name,
            proxy_id=proxy_id,
            user_proxy_config=user_proxy_config,
            open_urls=open_urls,
        )

        # 3.6 处理结果
        result = {
            "success": False,
            "profile_id": None,
            "profile_no": None,
            "fingerprint": fingerprint,
            "error": None,
        }

        if resp.get("code") == 0:
            data = resp.get("data", {})
            result["success"] = True
            result["profile_id"] = data.get("profile_id", "")
            result["profile_no"] = data.get("profile_no", "")
            logger.info(f"环境创建成功: {env_name} (profile_id={result['profile_id']})")
            self._log_operation(
                "INFO", "create_env",
                f"创建环境成功: {env_name}",
                detail=json.dumps({
                    "profile_id": result["profile_id"],
                    "profile_no": result["profile_no"],
                    "fingerprint": fingerprint,
                }, ensure_ascii=False)
            )
            # 记录环境运行日志
            self._log_env_runtime(result["profile_id"], env_name, "create")
        else:
            result["error"] = resp.get("msg", "未知错误")
            logger.error(f"环境创建失败: {resp.get('msg')}")
            self._log_operation(
                "ERROR", "create_env",
                f"创建环境失败: {resp.get('msg')}",
                detail=json.dumps({"name": env_name, "error": resp}, ensure_ascii=False)
            )

        return result

    def _select_proxy(self) -> Optional[ProxyConfig]:
        """
        从数据库中随机选择一个启用的代理。

        Returns:
            ProxyConfig 或 None（无可用的代理）
        """
        proxies = ProxyConfig.query.filter_by(enabled=1).all()
        if not proxies:
            logger.warning("没有可用的代理配置！")
            return None
        return random.choice(proxies)

    # ============================================================
    # 4. 删除环境
    # ============================================================

    def delete_environments(
        self,
        profile_ids: list,
        force: bool = False,
    ) -> dict:
        """
        批量删除环境。

        流程：
        1. 过滤掉保留环境（force=True 时跳过）
        2. 检查每个环境是否正在运行
        3. 先关闭正在运行的环境
        4. 调用 API 批量删除（每批最多 100 个）

        Args:
            profile_ids: 要删除的环境ID列表
            force:       是否强制删除（包括保留环境）

        Returns:
            dict: {
                "success": bool,
                "deleted_count": int,           # 成功删除数
                "failed_count": int,            # 删除失败数
                "skipped_preserved": list,      # 被跳过的保留环境
                "skipped_active": list,         # 因运行中被跳过（关闭后重试）
                "errors": list,                 # 错误信息列表
            }
        """
        result = {
            "success": True,
            "deleted_count": 0,
            "failed_count": 0,
            "skipped_preserved": [],
            "skipped_active": [],
            "errors": [],
        }

        # 4.1 过滤保留环境
        if not force:
            preserved_ids = {pe.profile_id for pe in PreservedEnv.query.all()}
            valid_ids = []
            for pid in profile_ids:
                if pid in preserved_ids:
                    result["skipped_preserved"].append(pid)
                    logger.warning(f"跳过保留环境: {pid}")
                else:
                    valid_ids.append(pid)
        else:
            valid_ids = list(profile_ids)

        if not valid_ids:
            result["success"] = False
            result["errors"].append("所有环境都是保留环境或列表为空")
            return result

        # 4.2 检查运行状态并关闭
        ids_to_delete = []
        for pid in valid_ids:
            if self.client.is_profile_active(pid):
                logger.info(f"环境 {pid} 正在运行，尝试关闭...")
                stop_resp = self.client.stop_browser(pid)
                if stop_resp.get("code") == 0:
                    logger.info(f"环境 {pid} 已关闭")
                    ids_to_delete.append(pid)
                else:
                    result["skipped_active"].append(pid)
                    logger.error(f"环境 {pid} 关闭失败: {stop_resp.get('msg')}")
            else:
                ids_to_delete.append(pid)

        # 4.3 批量删除（每批100个）
        for i in range(0, len(ids_to_delete), 100):
            batch = ids_to_delete[i:i + 100]
            resp = self.client.delete_profiles(batch)
            if resp.get("code") == 0:
                result["deleted_count"] += len(batch)
                logger.info(f"批量删除成功: {len(batch)} 个环境")
                for pid in batch:
                    self._log_env_runtime(pid, "", "delete")
            else:
                result["failed_count"] += len(batch)
                result["errors"].append(f"删除失败 ({len(batch)}个): {resp.get('msg')}")
                logger.error(f"批量删除失败: {resp.get('msg')}")

        self._log_operation(
            "INFO", "delete_env",
            f"批量删除完成: 成功{result['deleted_count']}, 失败{result['failed_count']}",
            detail=json.dumps(result, ensure_ascii=False)
        )

        return result

    # ============================================================
    # 5. 更新环境
    # ============================================================

    def update_environment(
        self,
        profile_id: str,
        fingerprint_updates: Optional[dict] = None,
        proxy_id: Optional[str] = None,
        name: Optional[str] = None,
        remark: Optional[str] = None,
    ) -> dict:
        """
        更新环境配置。

        只会更新传入的非 None 参数。不传的参数保持不变。

        注意：以下参数不能更新——
        - webgl=3（随机匹配）
        - random_ua

        Args:
            profile_id:          环境ID（必填）
            fingerprint_updates: 要更新的指纹参数（可选，只传要修改的字段）
            proxy_id:            新代理ID（可选）
            name:                新名称（可选）
            remark:              新备注（可选）

        Returns:
            dict: {
                "success": bool,
                "error": str,
                "updated_fields": list,  # 实际更新的字段列表
            }
        """
        result = {
            "success": False,
            "error": None,
            "updated_fields": [],
        }

        # 过滤掉不可更新的参数
        if fingerprint_updates:
            non_updatable = ["webgl", "random_ua"]
            for key in non_updatable:
                if key in fingerprint_updates:
                    logger.warning(f"跳过不可更新的参数: {key}")
                    fingerprint_updates.pop(key, None)

        # 构建更新请求
        resp = self.client.update_profile(
            profile_id=profile_id,
            fingerprint_config=fingerprint_updates,
            proxy_id=proxy_id,
            name=name,
            user_proxy_config=None,
            remark=remark,
        )

        if resp.get("code") == 0:
            result["success"] = True
            if fingerprint_updates:
                result["updated_fields"].extend(fingerprint_updates.keys())
            if proxy_id:
                result["updated_fields"].append("proxy_id")
            if name:
                result["updated_fields"].append("name")
            if remark:
                result["updated_fields"].append("remark")
            logger.info(f"环境 {profile_id} 更新成功: {result['updated_fields']}")
            self._log_operation("INFO", "update_env", 
                                f"更新环境 {profile_id}: {result['updated_fields']}")
        else:
            result["error"] = resp.get("msg", "未知错误")
            logger.error(f"环境 {profile_id} 更新失败: {resp.get('msg')}")

        return result

    # ============================================================
    # 6. 日志记录
    # ============================================================

    def _log_operation(self, level: str, module: str, message: str, detail: Optional[str] = None):
        """
        记录操作日志到数据库。

        Args:
            level:   日志级别 (INFO/WARNING/ERROR)
            module:  来源模块
            message: 日志消息
            detail:  详细数据（JSON字符串）
        """
        try:
            log_entry = OperationLog(
                level=level,
                module=module,
                message=message,
                detail=detail,
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            logger.error(f"写入操作日志失败: {e}")

    def _log_env_runtime(
        self,
        profile_id: str,
        env_name: str,
        event_type: str,
        ip_address: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        extra_data: Optional[str] = None,
    ):
        """
        记录环境运行日志。

        Args:
            profile_id:       环境ID
            env_name:         环境名称
            event_type:       事件类型 (create/delete/start/stop/ip_check)
            ip_address:       IP地址
            duration_seconds: 运行时长
            extra_data:       额外数据
        """
        try:
            log_entry = EnvRuntimeLog(
                profile_id=profile_id,
                env_name=env_name,
                event_type=event_type,
                ip_address=ip_address,
                duration_seconds=duration_seconds,
                extra_data=extra_data,
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            logger.error(f"写入环境运行日志失败: {e}")

    # ============================================================
    # 7. 任务队列执行
    # ============================================================

    def process_task(self, task: TaskQueue) -> dict:
        """
        处理单个任务。

        根据 task_type 调用对应的处理方法。

        Args:
            task: TaskQueue 实例

        Returns:
            dict: 执行结果
        """
        task.status = "running"
        task.started_at = datetime.datetime.utcnow()
        db.session.commit()

        result = {}
        try:
            if task.task_type == "create_env":
                params = json.loads(task.params)
                result = self.create_environment(
                    env_name=params.get("env_name"),
                    group_id=params.get("group_id", "0"),
                    proxy_id=params.get("proxy_id"),
                    open_url=params.get("open_url"),
                )
            elif task.task_type == "delete_env":
                params = json.loads(task.params)
                profile_ids = params.get("profile_ids", [])
                force = params.get("force", False)
                result = self.delete_environments(profile_ids, force=force)
            elif task.task_type == "update_env":
                params = json.loads(task.params)
                result = self.update_environment(
                    profile_id=params.get("profile_id"),
                    fingerprint_updates=params.get("fingerprint_updates"),
                    proxy_id=params.get("proxy_id"),
                    name=params.get("name"),
                )
            elif task.task_type == "check_status":
                result = self.init_check()
            else:
                result = {"success": False, "error": f"未知任务类型: {task.task_type}"}

            # 更新任务状态
            if result.get("success", False):
                task.status = "completed"
            else:
                task.status = "failed"
                task.result_msg = result.get("error", "未知错误")

        except Exception as e:
            logger.error(f"任务执行异常: {e}")
            task.status = "failed"
            task.result_msg = str(e)
            result = {"success": False, "error": str(e)}

        task.completed_at = datetime.datetime.utcnow()
        task.result_msg = json.dumps(result, ensure_ascii=False)
        db.session.commit()

        return result

    def process_pending_tasks(self) -> int:
        """
        处理所有待处理的任务。

        按优先级排序，依次执行。

        Returns:
            int: 处理的任务数量
        """
        tasks = (
            TaskQueue.query
            .filter_by(status="pending")
            .order_by(TaskQueue.priority.asc(), TaskQueue.created_at.asc())
            .all()
        )

        count = 0
        for task in tasks:
            logger.info(f"执行任务 #{task.id}: {task.task_type}")
            self.process_task(task)
            count += 1

        return count
