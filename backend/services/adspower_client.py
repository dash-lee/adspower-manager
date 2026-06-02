"""
AdsPower Local API 客户端
========================

封装 AdsPower Local API 的全部操作，使用 v2 接口（推荐）。

支持的接口：
- 状态检查:           GET /status
- 环境列表:           POST /api/v2/browser-profile/list
- 创建环境:           POST /api/v2/browser-profile/create
- 更新环境:           POST /api/v2/browser-profile/update
- 删除环境:           POST /api/v2/browser-profile/delete
- 启动浏览器:         POST /api/v2/browser-profile/start
- 关闭浏览器:         POST /api/v2/browser-profile/stop
- 关闭所有浏览器:     POST /api/v2/browser-profile/stop-all
- 检查启动状态:       GET /api/v2/browser-profile/active
- 查询本地已启动:     GET /api/v1/browser/local-active
- 分组列表:           GET /api/v1/group/list
- 代理列表:           POST /api/v2/proxy-list/list
- 生成新指纹:         POST /api/v2/browser-profile/new-fingerprint
- 清除缓存:           POST /api/v2/browser-profile/delete-cache
- 查询UA:             POST /api/v2/browser-profile/ua
- 查询Cookies:        GET /api/v2/browser-profile/cookies

请求频率限制（自动处理）：
- 环境数 0~200:   2次/秒
- 环境数 200~5000: 5次/秒
- 环境数 5000+:   10次/秒
- 部分接口固定 1次/秒（list, cookies, download-kernel）
"""

import time
import json
import requests
from typing import Optional, Any
from loguru import logger


class AdsPowerClient:
    """
    AdsPower Local API 客户端。
    
    所有方法遵循 AdsPower 通用响应格式：
    成功: {"code": 0, "data": {...}, "msg": "success"}
    失败: {"code": -1, "data": {}, "msg": "error_message"}
    
    Usage:
        client = AdsPowerClient(api_url="http://local.adspower.net:50325", api_key="xxx")
        result = client.check_status()
        profiles = client.list_profiles()
    """

    def __init__(self, api_url: str = "http://local.adspower.net:50325", api_key: str = ""):
        """
        初始化 AdsPower 客户端。

        Args:
            api_url: AdsPower Local API 地址（默认 http://local.adspower.net:50325）
            api_key: API 密钥（在 AdsPower 客户端 → 自动化 → API 中获取）
        """
        # 确保 URL 不以斜杠结尾
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        # 请求头
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # 上次请求时间（用于频率控制）
        self._last_request_time = 0
        # 默认请求间隔（秒）
        self._rate_limit = 0.5  # 默认 2次/秒

    # ============================================================
    # 内部工具方法
    # ============================================================

    def _rate_limit_wait(self):
        """
        频率限制控制。
        
        确保两次请求之间至少间隔 _rate_limit 秒，
        避免触发 AdsPower API 的频率限制。
        """
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """
        发送 GET 请求到 AdsPower API。

        Args:
            endpoint: API 端点路径（例如 "/status"）
            params: URL 查询参数字典

        Returns:
            dict: API 响应 JSON
            
        Raises:
            requests.RequestException: 网络请求失败
        """
        self._rate_limit_wait()
        url = f"{self.api_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"AdsPower GET {endpoint} 请求失败: {e}")
            return {"code": -1, "data": {}, "msg": str(e)}

    def _post(self, endpoint: str, body: Optional[dict] = None) -> dict:
        """
        发送 POST 请求到 AdsPower API（v2 推荐方式）。

        Args:
            endpoint: API 端点路径
            body: JSON 请求体

        Returns:
            dict: API 响应 JSON
            
        Raises:
            requests.RequestException: 网络请求失败
        """
        self._rate_limit_wait()
        url = f"{self.api_url}{endpoint}"
        try:
            resp = requests.post(url, headers=self.headers, json=body or {}, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"AdsPower POST {endpoint} 请求失败: {e}")
            return {"code": -1, "data": {}, "msg": str(e)}

    def _is_success(self, response: dict) -> bool:
        """判断 API 响应是否成功（code == 0）。"""
        return response.get("code") == 0

    # ============================================================
    # 1. 接口状态检查
    # ============================================================

    def check_status(self, verify_auth: bool = True) -> bool:
        """
        检查 AdsPower API 接口是否可用。

        GET /status

        Args:
            verify_auth: 是否同时验证 API Key 有效（默认 True）。
                         如果为 True，会额外调用一个需要鉴权的接口来确认 Key 有效。

        Returns:
            bool: True 表示接口正常且 API Key 有效，False 表示不可用或 Key 无效
        """
        # 1. 基本连通性检查（/status 不需要 API Key）
        resp = self._get("/status")
        if not self._is_success(resp):
            logger.error(f"AdsPower API 接口不可用: {resp.get('msg', '未知错误')}")
            return False

        # 2. 如果配置了 API Key，用需要鉴权的接口验证 Key 是否有效
        if verify_auth and self.api_key:
            auth_check = self._post("/api/v2/browser-profile/list", {"page": 1, "limit": 1})
            if not self._is_success(auth_check):
                err_msg = auth_check.get("msg", "未知错误")
                logger.error(f"AdsPower API Key 验证失败: {err_msg}")
                logger.error("请检查配置中的 adspower_api_key 是否正确")
                return False
            logger.info("AdsPower API 接口正常，API Key 验证通过")
        else:
            logger.info("AdsPower API 接口状态正常（未验证 API Key）")

        return True

    # ============================================================
    # 2. 环境列表与查询
    # ============================================================

    def list_profiles(
        self,
        group_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        profile_no: Optional[str] = None,
        sort_type: str = "created_time",
        sort_order: str = "desc",
        page: int = 1,
        limit: int = 100,
    ) -> dict:
        """
        查询环境列表（v2 接口，1次/秒限制）。

        POST /api/v2/browser-profile/list

        Args:
            group_id:     分组ID过滤（可选）
            profile_id:   环境ID过滤（可选）
            profile_no:   环境编号过滤（可选）
            sort_type:    排序字段: serial_number / last_open_time / created_time
            sort_order:   排序方向: asc / desc
            page:         页码，从1开始
            limit:        每页数量，最大100

        Returns:
            dict: {
                "code": 0,
                "data": {
                    "list": [...],
                    "page": 1,
                    "page_size": 100,
                    "total": 10
                }
            }
        """
        body = {
            "page": page,
            "limit": min(limit, 100),
            "sort_type": sort_type,
            "sort_order": sort_order,
        }
        if group_id:
            body["group_id"] = group_id
        if profile_id:
            body["profile_id"] = profile_id
        if profile_no:
            body["profile_no"] = profile_no

        # 此接口固定 1次/秒
        self._last_request_time = max(self._last_request_time, time.time() + 1)
        return self._post("/api/v2/browser-profile/list", body)

    def get_all_profiles(self, group_id: Optional[str] = None) -> list:
        """
        获取所有环境列表（自动分页）。

        遍历所有分页，合并返回完整的环境列表。

        Args:
            group_id: 分组ID过滤（可选）

        Returns:
            list: 所有环境的完整列表
        """
        all_profiles = []
        page = 1
        while True:
            resp = self.list_profiles(group_id=group_id, page=page, limit=100)
            if not self._is_success(resp):
                logger.error(f"获取环境列表失败(第{page}页): {resp.get('msg')}")
                break
            data = resp.get("data", {})
            profiles = data.get("list", [])
            all_profiles.extend(profiles)
            # 检查是否还有更多页面
            total = data.get("total", 0)
            page_size = data.get("page_size", 100)
            if page * page_size >= total:
                break
            page += 1
        return all_profiles

    # ============================================================
    # 3. 创建环境
    # ============================================================

    def create_profile(
        self,
        group_id: str,
        fingerprint_config: dict,
        name: Optional[str] = None,
        proxy_id: Optional[str] = None,
        user_proxy_config: Optional[dict] = None,
        domain_name: Optional[str] = None,
        open_urls: Optional[list] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        cookie: Optional[str] = None,
        remark: Optional[str] = None,
        ipchecker: Optional[str] = None,
        repeat_config: Optional[list] = None,
    ) -> dict:
        """
        创建新浏览器环境（v2 接口）。

        POST /api/v2/browser-profile/create

        Args:
            group_id:             分组ID（必填，"0"为默认分组）
            fingerprint_config:   指纹配置对象（必填，不能为空 {} ）
            name:                 环境名称（可选）
            proxy_id:             代理ID，与 user_proxy_config 二选一
            user_proxy_config:    代理配置对象，与 proxy_id 二选一
            domain_name:          平台域名（可选）
            open_urls:            额外打开的URL列表（可选）
            username:             账号（可选）
            password:             密码（可选）
            cookie:               Cookie字符串（可选）
            remark:               备注（可选）
            ipchecker:            IP查询渠道: ip2location / ipapi
            repeat_config:        去重配置: 0=允许, 2=按账密, 3=按cookie, 4=按c_user

        Returns:
            dict: {
                "code": 0,
                "data": {
                    "profile_id": "h1yynkm",
                    "profile_no": "123"
                },
                "msg": "Success"
            }
        """
        body: dict[str, Any] = {
            "group_id": group_id,
            "fingerprint_config": fingerprint_config,
        }

        if name:
            body["name"] = name
        if proxy_id:
            body["proxyid"] = proxy_id
        elif user_proxy_config:
            body["user_proxy_config"] = user_proxy_config
        # 注意：proxy_id 和 user_proxy_config 必须提供一个
        if domain_name:
            body["platform"] = domain_name
        if open_urls:
            body["tabs"] = open_urls
        if username:
            body["username"] = username
        if password:
            body["password"] = password
        if cookie:
            body["cookie"] = cookie
        if remark:
            body["remark"] = remark
        if ipchecker:
            body["ipchecker"] = ipchecker
        if repeat_config:
            body["repeat_config"] = repeat_config

        return self._post("/api/v2/browser-profile/create", body)

    # ============================================================
    # 4. 更新环境
    # ============================================================

    def update_profile(
        self,
        profile_id: str,
        fingerprint_config: Optional[dict] = None,
        name: Optional[str] = None,
        proxy_id: Optional[str] = None,
        user_proxy_config: Optional[dict] = None,
        remark: Optional[str] = None,
    ) -> dict:
        """
        更新浏览器环境（v2 接口）。

        POST /api/v2/browser-profile/update

        注意：以下参数无法通过 API 更新（只能在客户端手动修改）：
        - webgl = 3（随机匹配）仅支持新建，不支持更新
        - random_ua 仅支持新建

        可以更新的参数：
        - name, proxy_id, user_proxy_config, remark
        - fingerprint_config 中的大部分参数

        Args:
            profile_id:          环境ID（必填）
            fingerprint_config:  指纹配置（必填？文档显示必填）
            name:                新名称（可选）
            proxy_id:            新代理ID（可选）
            user_proxy_config:   新代理配置（可选）
            remark:              新备注（可选）

        Returns:
            dict: API 响应
        """
        body: dict[str, Any] = {
            "profile_id": profile_id,
        }
        if fingerprint_config:
            body["fingerprint_config"] = fingerprint_config
        if name:
            body["name"] = name
        if proxy_id:
            body["proxyid"] = proxy_id
        elif user_proxy_config:
            body["user_proxy_config"] = user_proxy_config
        if remark:
            body["remark"] = remark

        return self._post("/api/v2/browser-profile/update", body)

    # 可更新的指纹参数列表（供后台展示可选）
    UPDATEABLE_PARAMS = [
        "automatic_timezone", "timezone", "webrtc", "location",
        "location_switch", "longitude", "latitude", "accuracy",
        "language", "language_switch", "page_language_switch",
        "page_language", "ua", "screen_resolution", "fonts",
        "canvas", "webgl_image", "webgl", "webgl_config", "audio",
        "do_not_track", "hardware_concurrency", "device_memory",
        "flash", "scan_port_type", "allow_scan_ports",
        "media_devices", "media_devices_num", "client_rects",
        "device_name_switch", "device_name", "speech_switch",
        "mac_address_config", "browser_kernel_config",
    ]

    # 不可更新的参数
    NON_UPDATEABLE_PARAMS = [
        "webgl=3（随机匹配）", "random_ua",
    ]

    # ============================================================
    # 5. 删除环境
    # ============================================================

    def delete_profiles(self, profile_ids: list) -> dict:
        """
        批量删除环境（v2 接口）。

        POST /api/v2/browser-profile/delete
        单次最多删除 100 个环境。

        注意：删除前应先检查环境是否处于开启状态。

        Args:
            profile_ids: 环境ID列表，例如 ["id1", "id2"]

        Returns:
            dict: API 响应
        """
        if len(profile_ids) > 100:
            logger.warning(f"单次最多删除100个环境，当前传入 {len(profile_ids)} 个")
        body = {"profile_id": profile_ids[:100]}
        return self._post("/api/v2/browser-profile/delete", body)

    # ============================================================
    # 6. 浏览器启动/停止
    # ============================================================

    def start_browser(
        self,
        profile_id: str,
        headless: int = 0,
        last_opened_tabs: int = 1,
        proxy_detection: int = 1,
        launch_args: Optional[list] = None,
        password_filling: int = 0,
        password_saving: int = 0,
        cdp_mask: int = 1,
        delete_cache: int = 0,
        device_scale: Optional[str] = None,
    ) -> dict:
        """
        启动浏览器环境（v2 接口）。

        POST /api/v2/browser-profile/start

        Args:
            profile_id:       环境ID（必填）
            headless:         无头模式: 1=无头, 0=正常
            last_opened_tabs: 是否打开上次标签: 1=是, 0=否
            proxy_detection:  是否打开代理检测页: 1=是, 0=否
            launch_args:      浏览器启动参数列表
            password_filling: 1=启用账密填充（仅首次生效）, 0=禁用
            password_saving:  1=允许保存密码（仅Chrome）, 0=禁用
            cdp_mask:         1=屏蔽CDP检测（iOS/Android强制）, 0=不屏蔽
            delete_cache:     1=关闭后清除缓存, 0=不清除
            device_scale:     手机缩放比 0.1~2（需Chrome128+）

        Returns:
            dict: {
                "code": 0,
                "data": {
                    "ws": {"selenium": "127.0.0.1:xxxx", "puppeteer": "ws://..."},
                    "debug_port": "xxxx",
                    "webdriver": "C:\\...\\chromedriver.exe"
                }
            }
        """
        body: dict[str, Any] = {
            "profile_id": profile_id,
            "headless": str(headless),
            "last_opened_tabs": str(last_opened_tabs),
            "proxy_detection": str(proxy_detection),
            "password_filling": str(password_filling),
            "password_saving": str(password_saving),
            "cdp_mask": str(cdp_mask),
            "delete_cache": str(delete_cache),
        }
        if launch_args:
            body["launch_args"] = launch_args
        if device_scale is not None:
            body["device_scale"] = str(device_scale)

        return self._post("/api/v2/browser-profile/start", body)

    def stop_browser(self, profile_id: str) -> dict:
        """
        关闭浏览器环境（v2 接口）。

        POST /api/v2/browser-profile/stop

        Args:
            profile_id: 环境ID（必填）

        Returns:
            dict: API 响应
        """
        return self._post("/api/v2/browser-profile/stop", {"profile_id": profile_id})

    def stop_all_browsers(self) -> dict:
        """
        关闭所有浏览器环境。

        POST /api/v2/browser-profile/stop-all

        Returns:
            dict: API 响应
        """
        return self._post("/api/v2/browser-profile/stop-all", {})

    # ============================================================
    # 7. 状态检查
    # ============================================================

    def check_active(self, profile_id: str) -> dict:
        """
        检查浏览器环境是否处于启动状态。

        GET /api/v2/browser-profile/active

        Args:
            profile_id: 环境ID

        Returns:
            dict: {
                "code": 0,
                "data": {
                    "status": "Active" 或 "Inactive",
                    "ws": {...}
                }
            }
        """
        return self._post("/api/v2/browser-profile/active", {"profile_id": profile_id})

    def get_local_active(self) -> dict:
        """
        查询当前设备所有已启动的浏览器。

        GET /api/v1/browser/local-active

        Returns:
            dict: 已启动浏览器列表
        """
        return self._get("/api/v1/browser/local-active")

    def is_profile_active(self, profile_id: str) -> bool:
        """
        便捷方法：判断指定环境是否正在运行。

        Args:
            profile_id: 环境ID

        Returns:
            bool: True 表示正在运行
        """
        resp = self.check_active(profile_id)
        if self._is_success(resp):
            return resp.get("data", {}).get("status") == "Active"
        return False

    # ============================================================
    # 8. 分组管理
    # ============================================================

    def list_groups(self, page: int = 1, page_size: int = 100) -> dict:
        """
        查询分组列表（v1 接口，1次/秒限制）。

        GET /api/v1/group/list

        Args:
            page:      页码
            page_size: 每页数量，最大2000

        Returns:
            dict: 分组列表
        """
        self._last_request_time = max(self._last_request_time, time.time() + 1)
        return self._get("/api/v1/group/list", {"page": page, "page_size": page_size})

    # ============================================================
    # 9. 代理管理
    # ============================================================

    def list_proxies(self, proxy_id: Optional[list] = None, page: int = 1, limit: int = 100) -> dict:
        """
        查询代理列表。

        POST /api/v2/proxy-list/list

        Args:
            proxy_id: 代理ID过滤列表（可选）
            page:     页码
            limit:    每页数量

        Returns:
            dict: 代理列表
        """
        body = {"page": str(page), "limit": str(limit)}
        if proxy_id:
            body["proxy_id"] = proxy_id
        return self._post("/api/v2/proxy-list/list", body)

    # ============================================================
    # 10. 其他功能
    # ============================================================

    def new_fingerprint(self, profile_ids: list) -> dict:
        """
        为指定环境生成新的随机指纹。

        POST /api/v2/browser-profile/new-fingerprint

        Args:
            profile_ids: 环境ID列表

        Returns:
            dict: API 响应
        """
        return self._post("/api/v2/browser-profile/new-fingerprint", {"profile_id": profile_ids})

    def delete_cache(self, profile_ids: list, cache_types: Optional[list] = None) -> dict:
        """
        清除环境缓存。

        POST /api/v2/browser-profile/delete-cache

        Args:
            profile_ids: 环境ID列表
            cache_types: 缓存类型: local_storage, indexeddb, cookie, history, 
                        image_file, extension_cache（默认全部）

        Returns:
            dict: API 响应
        """
        body = {"profile_id": profile_ids}
        if cache_types:
            body["type"] = cache_types
        return self._post("/api/v2/browser-profile/delete-cache", body)

    def get_ua(self, profile_ids: list) -> dict:
        """
        查询环境的 User-Agent。

        POST /api/v2/browser-profile/ua

        Args:
            profile_ids: 环境ID列表

        Returns:
            dict: 包含 UA 信息的响应
        """
        return self._post("/api/v2/browser-profile/ua", {"profile_id": profile_ids})

    def get_cookies(self, profile_id: str) -> dict:
        """
        查询环境的 Cookies（1次/秒限制）。

        GET /api/v2/browser-profile/cookies

        Args:
            profile_id: 环境ID（一次只能查一个）

        Returns:
            dict: 包含 cookies JSON 字符串的响应
        """
        self._last_request_time = max(self._last_request_time, time.time() + 1)
        return self._get("/api/v2/browser-profile/cookies", {"profile_id": profile_id})
