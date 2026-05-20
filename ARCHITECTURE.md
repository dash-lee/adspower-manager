# AdsPower Manager 项目架构与开发规范

> **版本**: v1.0　|　**最后更新**: 2026-05-21　|　**技术栈**: Flask 3.0 + SQLAlchemy + APScheduler + 原生 JS

---

## 目录

1. [项目概览](#1-项目概览)
2. [目录结构](#2-目录结构)
3. [架构分层](#3-架构分层)
4. [模块详解](#4-模块详解)
5. [数据库设计](#5-数据库设计)
6. [API 端点全景](#6-api-端点全景)
7. [前端架构](#7-前端架构)
8. [编码规范](#8-编码规范)
9. [配置管理](#9-配置管理)
10. [部署方案](#10-部署方案)
11. [扩展路线图](#11-扩展路线图)

---

## 1. 项目概览

**AdsPower Manager** 是一个基于 Flask 的 AdsPower 浏览器环境管理后台，提供 Web UI 对 AdsPower Local API 的完整操控能力。

### 核心功能

| 功能模块 | 说明 |
|----------|------|
| 🔌 **API 全功能封装** | 20+ AdsPower v2 API 端点，覆盖环境 CRUD、浏览器控制、代理/分组管理 |
| 🎲 **随机指纹生成** | 从配置池中按权重随机选取 7 类指纹参数（分辨率/CPU/内存/字体/等） |
| ⚙️ **后台配置管理** | Web 界面操作 4 类配置（通用/代理/指纹池/保留环境），修改即时生效 |
| 📋 **任务队列** | 支持 create/delete/update/check 四种任务类型，带优先级和重试机制 |
| ⏰ **定时调度** | 3 个周期任务：队列处理(30s)、状态检查(1h)、日志清理(每日3:00) |
| 📊 **双轨日志** | 操作日志（按级别/模块过滤）+ 环境运行日志（按事件类型过滤），持久化存储 |

### 技术选型

```
后端: Flask 3.0  (工厂模式 + Blueprint 蓝图)
ORM:  Flask-SQLAlchemy 3.1.1
任务调度: APScheduler 3.10.4 (BackgroundScheduler)
数据库: SQLite (开发/小规模) → PostgreSQL (VPS 部署，改环境变量即可)
前端: Jinja2 模板 + 原生 JS（零框架，零构建工具）
日志: loguru（控制台 + 文件轮转）
```

### 设计原则

- **即时生效**：配置从 DB 实时读取，从不缓存
- **最小依赖**：前端零框架，后端仅 8 个 pip 包
- **VPS 就绪**：数据库切换只需改一个环境变量 `DATABASE_URL`
- **API 优先**：所有功能先以 REST API 暴露，前端页面为 API 的消费者

---

## 2. 目录结构

```
adspower-manager/
├── run.py                          # 应用入口：argparse + loguru + 优雅关闭
├── requirements.txt                # pip 依赖清单（8个包）
├── README.md                       # 用户手册
├── ARCHITECTURE.md                 # 本文档：架构与规范
├── data/                           # 运行时数据（自动创建，不纳入版本控制）
│   ├── adspower_manager.db         # SQLite 数据库文件
│   └── app.log                     # 应用日志（10MB轮转，保留7天）
└── backend/
    ├── __init__.py                 # 包标识
    ├── app.py                      # Flask 工厂函数 + 页面路由 + 系统API
    ├── database.py                 # SQLAlchemy 实例 + DB URI 构建
    ├── models.py                   # 7 个 ORM 模型（约 274 行）
    ├── routes/                     # API 路由层（3 个 Blueprint）
    │   ├── __init__.py             # Blueprint 集中导出
    │   ├── config_routes.py        # 配置管理 API（4 类 CRUD + 初始化）
    │   ├── env_routes.py           # 环境管理 API（CRUD + 浏览器 + 任务队列）
    │   └── log_routes.py           # 日志查询 API（操作日志 + 环境日志 + 统计）
    ├── services/                   # 业务逻辑层
    │   ├── __init__.py
    │   ├── adspower_client.py      # AdsPower API 客户端（652行，20+端点）
    │   ├── env_manager.py          # 环境管理业务逻辑（741行）
    │   └── scheduler.py            # APScheduler 定时任务调度（210行）
    ├── templates/                  # Jinja2 前端页面
    │   ├── base.html               # 布局骨架：侧边导航 + 主内容 + Toast
    │   ├── dashboard.html          # 仪表盘：统计卡片 + 快速操作
    │   ├── environments.html       # 环境管理：列表 + 批量操作 + 模态框
    │   ├── config.html             # 配置管理：Tab 切换 4 类配置
    │   └── logs.html               # 日志查看：Tab + 过滤器 + 分页
    └── static/
        ├── css/style.css           # 暗色主题样式（CSS变量，421行）
        └── js/app.js               # 通用 JS 工具（toast/escape/formatTime/apiGet/apiPost）
```

---

## 3. 架构分层

```
┌─────────────────────────────────────────────────────┐
│                    浏览器层                          │
│    Jinja2 模板 (base → 4 页面) + 原生 JS (fetch)     │
│    POST /api/*  ←→  JSON {code, data, msg}          │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP
┌─────────────────▼───────────────────────────────────┐
│                路由层 (routes/)                      │
│    config_bp  /api/config/*   配置 CRUD             │
│    env_bp     /api/env/*      环境管理 + 任务队列     │
│    log_bp     /api/logs/*     日志查询 + 统计        │
│    职责：参数校验 → 调用服务层 → 返回 JSON            │
└─────────────────┬───────────────────────────────────┘
                  │ Python 调用
┌─────────────────▼───────────────────────────────────┐
│              服务层 (services/)                      │
│    EnvManager      业务编排：创建/删除/更新/初始化检查 │
│    AdsPowerClient  API 通信：HTTP请求+频率控制+错误处理│
│    TaskScheduler   定时调度：任务消费+健康检查+日志清理 │
│    职责：业务逻辑 → DB读写 → 调用第三方API → 记录日志  │
└─────────────────┬───────────────────────────────────┘
                  │ SQLAlchemy ORM
┌─────────────────▼───────────────────────────────────┐
│              数据层 (models.py + database.py)        │
│    GeneralConfig   ProxyConfig   FingerprintPool     │
│    PreservedEnv    TaskQueue     OperationLog        │
│    EnvRuntimeLog                                    │
│    职责：ORM 映射 → SQLite/PostgreSQL               │
└─────────────────────────────────────────────────────┘
```

### 数据流示例：「创建环境」

```
1. 用户点击「创建环境」按钮
2. 前端 POST /api/env/create  {count: 5, group_id: "0"}
3. env_routes.py → _get_manager() → EnvManager(client)
4. EnvManager.create_environment():
   a. _select_proxy() → 从 ProxyConfig 随机选一个启用的代理
   b. generate_fingerprint() → 从 FingerprintPool 按权重随机采样 7 类参数
   c. client.create_profile(...) → POST AdsPower API
   d. _log_operation() → 写入 OperationLog 表
   e. _log_env_runtime() → 写入 EnvRuntimeLog 表
5. 返回 JSON {code: 0, data: {results: [...]}}
6. 前端 showToast("创建完成: 5/5 成功") + 刷新列表
```

---

## 4. 模块详解

### 4.1 run.py — 应用入口

```
职责：命令行参数解析 → 日志初始化 → 创建 Flask 应用 → 启动 → 优雅关闭
```

**启动方式**：
```bash
python run.py                          # 默认 0.0.0.0:5000
python run.py --port 8080 --debug      # 指定端口 + 调试模式
PORT=8000 python run.py               # 环境变量覆盖
```

**日志配置**：
- 控制台：`HH:mm:ss | LEVEL | module | message`（INFO 级别）
- 文件：`data/app.log`，10MB 轮转，保留 7 天（DEBUG 级别）

**优雅关闭**：捕获 `KeyboardInterrupt` → 停止 APScheduler → 正常退出

### 4.2 app.py — Flask 工厂

```
create_app() → 配置 → 数据库 → AdsPower客户端 → 调度器 → 注册蓝图 → 页面路由
```

**关键设计**：
- **工厂模式**：`create_app()` 返回配置好的 Flask 实例，便于测试
- **应用上下文内读取配置**：启动时从 DB 读取 `adspower_api_url` / `adspower_api_key`
- **全局实例注入**：`ADSPOWER_CLIENT` 和 `SCHEDULER` 存储在 `app.config` 中
- **蓝图注册**：3 个 Blueprint 分别处理配置/环境/日志 API
- **页面路由**：`/dashboard`, `/config`, `/environments`, `/logs` 返回 Jinja2 模板
- **系统 API**：`/api/status`（整体状态）, `/api/scheduler/*`（调度器控制）

### 4.3 database.py — 数据库初始化

```
db = SQLAlchemy()          # 全局实例
get_database_uri()          # 默认 SQLite，支持 DATABASE_URL 覆盖
init_db(app)                # 绑定 Flask 应用 + 创建所有表
```

**默认数据库路径**：`data/adspower_manager.db`（项目根目录下）

**切换 PostgreSQL**：
```bash
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
python run.py
```

### 4.4 models.py — 数据模型 (7 个表)

详见 [第 5 节：数据库设计](#5-数据库设计)。

### 4.5 services/adspower_client.py — AdsPower API 客户端

```
AdsPowerClient(api_url, api_key)
├── _get() / _post()           # 内部 HTTP 方法（含频率控制）
├── _rate_limit_wait()          # 自动限速（默认 0.5s，部分接口 1s）
├── _is_success()               # 判断 code == 0
├── check_status()              # GET /status
├── list_profiles()             # POST /api/v2/browser-profile/list
├── get_all_profiles()          # 自动分页获取全部
├── create_profile()            # POST /api/v2/browser-profile/create
├── update_profile()            # POST /api/v2/browser-profile/update
├── delete_profiles()           # POST /api/v2/browser-profile/delete (批量≤100)
├── start_browser()             # POST /api/v2/browser-profile/start
├── stop_browser()              # POST /api/v2/browser-profile/stop
├── stop_all_browsers()         # POST /api/v2/browser-profile/stop-all
├── check_active()              # POST /api/v2/browser-profile/active
├── get_local_active()          # GET /api/v1/browser/local-active
├── is_profile_active()         # 便捷方法：判断是否 Active
├── list_groups()               # GET /api/v1/group/list
├── list_proxies()              # POST /api/v2/proxy-list/list
├── new_fingerprint()           # POST /api/v2/browser-profile/new-fingerprint
├── delete_cache()              # POST /api/v2/browser-profile/delete-cache
├── get_ua()                    # POST /api/v2/browser-profile/ua
└── get_cookies()               # GET /api/v2/browser-profile/cookies (单查)
```

**关键设计**：
- 全部使用 **v2 接口**（POST + JSON body），仅 `status`、`local-active`、`group/list` 用 v1 GET
- **频率控制**：`_last_request_time` 确保最小间隔，list/cookies 类接口强制 1s 间隔
- **错误容错**：`requests.RequestException` 捕获后返回 `{code: -1, msg: str(e)}`
- `UPDATEABLE_PARAMS` / `NON_UPDATEABLE_PARAMS` 常量列表，供前端参考

### 4.6 services/env_manager.py — 环境管理业务层

```
EnvManager(client)
├── 配置读取
│   ├── _get_config(key, default)           # 每次查 DB，即时生效
│   └── _get_config_int(key, default)
├── 1. 初始化检查
│   └── init_check()                         # API状态 + 环境对比 + 保留检查
├── 2. 随机指纹
│   ├── generate_fingerprint()               # 从 FingerprintPool 加权随机采样
│   └── _parse_pool_value()                  # 类型转换（fonts→list, media_devices_num→dict）
├── 3. 创建环境
│   ├── create_environment()                 # 代理选择 → 指纹生成 → API调用 → 日志
│   └── _select_proxy()                      # 从 enabled=1 的代理中随机选择
├── 4. 删除环境
│   └── delete_environments()                # 保留过滤 → 关闭活跃 → 批量删除(≤100/批)
├── 5. 更新环境
│   └── update_environment()                 # 过滤不可更新的参数 → API 调用
├── 6. 日志记录
│   ├── _log_operation()                     # 写 OperationLog 表
│   └── _log_env_runtime()                   # 写 EnvRuntimeLog 表
└── 7. 任务队列
    ├── process_task()                       # 根据 task_type 分发执行
    └── process_pending_tasks()              # 按优先级+时间顺序处理所有 pending
```

**随机指纹参数**（7 类）：

| 参数名 | 格式 | 示例 |
|--------|------|------|
| `screen_resolution` | 字符串 `"宽_高"` | `"1920_1080"` |
| `fonts` | JSON 列表 | `["Arial","Calibri","Cambria"]` |
| `hardware_concurrency` | 字符串数字 | `"8"` |
| `device_memory` | 字符串数字（GB） | `"16"` |
| `media_devices` | 字符串数字 | `"1"` (1=噪音, 2=自定义, 0=关闭) |
| `media_devices_num` | JSON 对象 | `{"audioinput_num":"1","videoinput_num":"1",...}` |

### 4.7 services/scheduler.py — 定时任务调度

```
TaskScheduler(client)
├── start()                   # 注册 3 个 job → 启动 BackgroundScheduler
├── stop()                    # shutdown(wait=True)
├── get_jobs()                # 返回任务列表
├── pause_job(job_id)         # 暂停指定任务
├── resume_job(job_id)        # 恢复指定任务
├── _process_task_queue()     # 每 30s 处理 pending 任务
├── _auto_check_status()      # 每 1h 完整健康检查
└── _cleanup_old_logs()       # 每天 03:00 删除 7 天前的日志
```

**调度器配置**：
- 时区：`Asia/Shanghai`
- `coalesce=True`：合并错过的执行
- `max_instances=1`：同一 job 不并发
- 间隔配置在 `general_config` 表中（`task_poll_interval`, `auto_check_interval`）

### 4.8 routes/ — API 路由层

#### config_routes.py → Blueprint("config", /api/config)

- `GET /general` — 所有通用配置
- `GET /general/<key>` — 单个通用配置
- `POST /general` — 创建/更新（key 存在则更新值）
- `DELETE /general/<id>` — 删除
- `GET/POST /proxy` — 代理配置 CRUD（密码脱敏返回 `***`）
- `PUT/DELETE /proxy/<id>` — 更新/删除代理
- `GET/POST /fingerprint` — 指纹池 CRUD（支持 `?param_name=` 过滤）
- `PUT/DELETE /fingerprint/<id>`
- `GET/POST /preserved` — 保留环境 CRUD
- `DELETE /preserved/<id>`
- `POST /init_defaults` — 初始化默认配置（通用配置 + 指纹候选池，不覆盖已有数据）

#### env_routes.py → Blueprint("env", /api/env)

- `GET /check` — 初始化检查
- `GET /list` — 环境列表（分页）
- `GET /list/all` — 所有环境（自动分页）
- `POST /create` — 创建（支持 `count` 批量、`use_queue` 队列模式）
- `POST /delete` — 批量删除（支持 `force` 强制）
- `POST /update` — 更新环境
- `POST /browser/start` — 启动浏览器
- `POST /browser/stop` — 关闭浏览器
- `POST /browser/stop-all` — 关闭全部
- `GET /browser/active?profile_id=` — 检查启动状态
- `GET /browser/local-active` — 本机已启动列表
- `GET /tasks` — 任务队列（支持 `?status=` 过滤）
- `POST /tasks/<id>/cancel` — 取消任务
- `POST /tasks/process` — 手动触发任务处理

#### log_routes.py → Blueprint("log", /api/logs)

- `GET /operation` — 操作日志（支持 `level`/`module`/`keyword` 过滤 + 分页）
- `GET /environment` — 环境运行日志（支持 `profile_id`/`event_type` 过滤 + 分页）
- `GET /stats` — 日志统计概览（按级别/类型汇总 + 今日计数）

---

## 5. 数据库设计

### 5.1 表结构总览

```
general_config (通用配置)           proxy_config (代理配置)
├── id PK                          ├── id PK
├── config_key UNIQUE INDEX        ├── ads_proxy_id INDEX
├── config_value                   ├── name
├── category                       ├── proxy_soft / proxy_type
├── remark                         ├── proxy_host / proxy_port
└── updated_at                     ├── proxy_user / proxy_password
                                   ├── enabled (0/1)
fingerprint_pool (指纹随机池)      ├── remark
├── id PK                          └── created_at / updated_at
├── param_name INDEX
├── param_value                    preserved_env (环境保留)
├── weight (1-10)                  ├── id PK
├── enabled (0/1)                  ├── profile_id UNIQUE INDEX
├── remark                         ├── env_name
└── created_at                     ├── remark
                                   └── created_at
task_queue (任务队列)
├── id PK                          operation_log (操作日志)
├── task_type INDEX                ├── id PK
│   (create_env/delete_env/        ├── level INDEX (INFO/WARNING/ERROR)
│    update_env/check_status)      ├── module INDEX
├── params (JSON)                  ├── message
├── status INDEX                   ├── detail (JSON)
│   (pending/running/              └── created_at INDEX
│    completed/failed/cancelled)
├── priority                       env_runtime_log (环境运行日志)
├── retry_count / max_retries      ├── id PK
├── result_msg                     ├── profile_id INDEX
├── created_at                     ├── env_name
├── started_at                     ├── event_type INDEX
└── completed_at                   │   (create/delete/start/stop/ip_check)
                                   ├── ip_address
                                   ├── duration_seconds
                                   ├── extra_data (JSON)
                                   └── created_at INDEX
```

### 5.2 配置键名约定（general_config）

| config_key | 默认值 | 说明 |
|------------|--------|------|
| `adspower_api_url` | `http://local.adspower.net:50325` | AdsPower 本地 API 地址 |
| `adspower_api_key` | `""` | API 密钥 |
| `default_group_id` | `"0"` | 默认分组 ID |
| `task_poll_interval` | `"30"` | 任务队列轮询间隔（秒） |
| `auto_check_interval` | `"3600"` | 自动状态检查间隔（秒） |
| `max_env_limit` | `"100"` | 环境数量上限 |

### 5.3 关联关系

```
任务创建流程：
  ProxyConfig (随机选取) ──→ create_profile() ──→ 写入 OperationLog + EnvRuntimeLog
  FingerprintPool (加权采样) ──┘

删除保护流程：
  PreservedEnv (白名单) ──→ EnvManager.delete_environments() 过滤保留 ID

定时任务流程：
  TaskScheduler._process_task_queue() ──→ TaskQueue(状态: pending) ──→
    EnvManager.process_task() ──→ 根据 task_type 执行对应操作
```

---

## 6. API 端点全景

### 6.1 响应格式统一

```json
// 成功
{"code": 0, "data": {...}, "msg": "success"}

// 失败
{"code": -1, "data": null, "msg": "错误描述"}
```

### 6.2 端点矩阵

| 类别 | 方法 | 路径 | 说明 | 已实现 |
|------|------|------|------|:----:|
| **系统** | GET | `/api/status` | 整体状态 | ✅ |
| | GET | `/api/scheduler/jobs` | 调度器任务列表 | ✅ |
| | POST | `/api/scheduler/pause/<id>` | 暂停任务 | ✅ |
| | POST | `/api/scheduler/resume/<id>` | 恢复任务 | ✅ |
| **配置** | GET | `/api/config/general` | 通用配置列表 | ✅ |
| | POST | `/api/config/general` | 创建/更新配置 | ✅ |
| | DELETE | `/api/config/general/<id>` | 删除配置 | ✅ |
| | GET | `/api/config/proxy` | 代理配置列表 | ✅ |
| | POST | `/api/config/proxy` | 创建代理 | ✅ |
| | PUT | `/api/config/proxy/<id>` | 更新代理 | ✅ |
| | DELETE | `/api/config/proxy/<id>` | 删除代理 | ✅ |
| | GET | `/api/config/fingerprint` | 指纹池列表 | ✅ |
| | POST | `/api/config/fingerprint` | 添加候选项 | ✅ |
| | PUT | `/api/config/fingerprint/<id>` | 更新候选项 | ✅ |
| | DELETE | `/api/config/fingerprint/<id>` | 删除候选项 | ✅ |
| | GET | `/api/config/preserved` | 保留环境列表 | ✅ |
| | POST | `/api/config/preserved` | 添加保留环境 | ✅ |
| | DELETE | `/api/config/preserved/<id>` | 移除保留环境 | ✅ |
| | POST | `/api/config/init_defaults` | 初始化默认值 | ✅ |
| **环境** | GET | `/api/env/check` | 初始化检查 | ✅ |
| | GET | `/api/env/list` | 环境列表（分页） | ✅ |
| | GET | `/api/env/list/all` | 所有环境 | ✅ |
| | POST | `/api/env/create` | 创建环境 | ✅ |
| | POST | `/api/env/delete` | 批量删除 | ✅ |
| | POST | `/api/env/update` | 更新环境 | ✅ |
| **浏览器** | POST | `/api/env/browser/start` | 启动浏览器 | ✅ |
| | POST | `/api/env/browser/stop` | 关闭浏览器 | ✅ |
| | POST | `/api/env/browser/stop-all` | 关闭全部 | ✅ |
| | GET | `/api/env/browser/active` | 检查启动状态 | ✅ |
| | GET | `/api/env/browser/local-active` | 本机活跃列表 | ✅ |
| **任务** | GET | `/api/env/tasks` | 任务队列查询 | ✅ |
| | POST | `/api/env/tasks/process` | 手动处理任务 | ✅ |
| | POST | `/api/env/tasks/<id>/cancel` | 取消任务 | ✅ |
| **日志** | GET | `/api/logs/operation` | 操作日志 | ✅ |
| | GET | `/api/logs/environment` | 环境运行日志 | ✅ |
| | GET | `/api/logs/stats` | 日志统计 | ✅ |

### 6.3 AdsPower API 客户端已封装的端点（服务层内部使用）

| 端点 | 方法 | 对应方法 |
|------|------|----------|
| `/status` | GET | `check_status()` |
| `/api/v2/browser-profile/list` | POST | `list_profiles()` |
| `/api/v2/browser-profile/create` | POST | `create_profile()` |
| `/api/v2/browser-profile/update` | POST | `update_profile()` |
| `/api/v2/browser-profile/delete` | POST | `delete_profiles()` |
| `/api/v2/browser-profile/start` | POST | `start_browser()` |
| `/api/v2/browser-profile/stop` | POST | `stop_browser()` |
| `/api/v2/browser-profile/stop-all` | POST | `stop_all_browsers()` |
| `/api/v2/browser-profile/active` | POST | `check_active()` |
| `/api/v1/browser/local-active` | GET | `get_local_active()` |
| `/api/v1/group/list` | GET | `list_groups()` |
| `/api/v2/proxy-list/list` | POST | `list_proxies()` |
| `/api/v2/browser-profile/new-fingerprint` | POST | `new_fingerprint()` |
| `/api/v2/browser-profile/delete-cache` | POST | `delete_cache()` |
| `/api/v2/browser-profile/ua` | POST | `get_ua()` |
| `/api/v2/browser-profile/cookies` | GET | `get_cookies()` |

---

## 7. 前端架构

### 7.1 技术选型

- **零框架**：原生 JavaScript，无 React/Vue/jQuery
- **零构建工具**：无需 webpack/vite，直接通过 Flask 静态文件服务
- **CSS 变量系统**：暗色主题通过 `:root` 变量实现，无需 CSS 预处理器
- **模板继承**：所有页面 `{% extends "base.html" %}`

### 7.2 页面结构

```
base.html (骨架)
├── 侧边栏 (.sidebar, 220px fixed)
│   ├── header: "🔧 AdsPower Manager"
│   ├── nav-menu: 📊仪表盘 | 🌐环境管理 | ⚙️配置管理 | 📋日志查看
│   └── footer: API 状态指示器 (● 绿色/红色)
├── 主内容区 (.main-content, margin-left: 220px)
│   └── {% block content %} (各页面填充)
└── Toast 容器 (#toast-container, fixed top-right)
```

### 7.3 通用 JS 工具 (app.js)

| 函数 | 说明 |
|------|------|
| `showToast(message, type, duration)` | 弹出通知（success/error/info/warning） |
| `escapeHtml(str)` | HTML 安全转义 |
| `formatTime(isoString)` | ISO 时间 → `YYYY-MM-DD HH:mm:ss` |
| `apiGet(url)` | fetch GET 封装（自动 JSON 解析 + 错误兜底） |
| `apiPost(url, body)` | fetch POST 封装（JSON body + 错误兜底） |
| 全局点击监听 | 点击 `.modal` 背景关闭模态框 |

### 7.4 CSS 设计系统

```css
/* 色板 */
--bg-primary: #0f172a   /* 最深背景 */
--bg-secondary: #1e293b /* 卡片/侧边栏 */
--bg-hover: #334155     /* 悬停态 */
--text-primary: #e2e8f0
--text-muted: #64748b
--accent: #3b82f6       /* 蓝色强调 */
--success: #4ade80      /* 绿色 */
--warning: #fbbf24      /* 黄色 */
--error: #f87171        /* 红色 */

/* 间距 */
--radius: 8px
--sidebar-width: 220px
```

---

## 8. 编码规范

### 8.1 Python 规范

| 规则 | 说明 |
|------|------|
| **注释语言** | 中文注释，越详细越好 |
| **Docstring 风格** | 每个模块、类、公开方法必须有详细的中文 docstring |
| **模块文档** | 开头描述模块职责 + 依赖 + 使用方法 |
| **类型注解** | 函数签名使用 `typing` 注解（`Optional`, `dict`, `list`） |
| **配置读取** | 服务层从 DB 实时读取配置，**禁止缓存** |
| **日志** | 使用 `loguru.logger`（非 Python 标准 logging） |
| **数据库操作** | 所有 DB 操作通过 SQLAlchemy ORM，不写原生 SQL |
| **响应格式** | 路由层返回 `jsonify({code, data, msg})` |
| **错误处理** | 路由层 try-catch → 返回 `code: -1`；服务层 try-catch → 记录日志 |
| **密码安全** | 代理密码在 API 响应中脱敏为 `"***"` |
| **导入顺序** | 标准库 → 第三方 → 项目内部（`backend.*`） |

### 8.2 前端规范

| 规则 | 说明 |
|------|------|
| **注释语言** | 中文注释 |
| **框架** | 零框架，纯原生 JS |
| **CSS** | CSS 变量驱动，不引入 Tailwind/Bootstrap |
| **API 调用** | 使用 `apiGet()` / `apiPost()` 封装 |
| **DOM 操作** | 数据驱动：渲染前清空容器，遍历数据拼接 HTML |
| **事件绑定** | 内联 `onclick`（简单场景）或 `addEventListener` |
| **安全** | 用户数据显示前用 `escapeHtml()` 转义 |

### 8.3 文件命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 路由模块 | `{domain}_routes.py` | `config_routes.py` |
| 服务模块 | `snake_case.py` | `adspower_client.py`, `env_manager.py` |
| 模板文件 | `snake_case.html` | `environments.html` |
| Blueprint 名称 | 简短名 | `config_bp`, `env_bp`, `log_bp` |

### 8.4 Git 约定

- `.gitignore` 内容：`data/`, `venv/`, `__pycache__/`, `*.pyc`
- `data/` 目录不纳入版本控制（数据库和日志是运行时数据）

---

## 9. 配置管理

### 9.1 配置层级

```
环境变量 (最高优先级)
    ↓ 覆盖
命令行参数 (--port, --host)
    ↓ 覆盖
数据库 general_config 表 (Web UI 可修改)
    ↓ 覆盖
代码默认值 (最低优先级)
```

### 9.2 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | Flask 绑定地址 |
| `PORT` | `5000` | Flask 监听端口 |
| `DATABASE_URL` | `sqlite:///data/adspower_manager.db` | 数据库连接 URI |
| `SECRET_KEY` | `adspower-manager-secret-change-me` | Flask 密钥 |

### 9.3 配置即时生效机制

```
用户修改配置 → POST /api/config/general → 写入 DB → 服务层下次调用时自动读取最新值
                                                        ↑
                                                  从不缓存！
```

---

## 10. 部署方案

### 10.1 本地开发

```bash
cd /mnt/e/Web/adspower-manager
pip install -r requirements.txt
python run.py --debug
# 访问 http://localhost:5000/dashboard
```

### 10.2 VPS 部署

**方案 A：systemd（推荐）**
```ini
# /etc/systemd/system/adspower-manager.service
[Unit]
Description=AdsPower Manager
After=network.target

[Service]
User=youruser
WorkingDirectory=/opt/adspower-manager
ExecStart=/usr/bin/python3 run.py --host 0.0.0.0 --port 5000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable adspower-manager
sudo systemctl start adspower-manager
```

**方案 B：nohup（快速测试）**
```bash
nohup python run.py --host 0.0.0.0 --port 5000 > data/server.log 2>&1 &
```

**方案 C：切换 PostgreSQL**
```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/adspower"
python run.py --host 0.0.0.0 --port 5000
```

### 10.3 Nginx 反向代理（可选）

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 11. 扩展路线图

### 11.1 已规划功能

| 优先级 | 功能 | 说明 | 涉及模块 |
|:---:|------|------|----------|
| P0 | **Selenium/Playwright 集成** | 启动浏览器后自动连接 WebDriver，支持远程操作 | 新建 `services/selenium_bridge.py`，新增路由 |
| P0 | **代理 IP 检测与记录** | 获取代理真实出口 IP，写入 `env_runtime_log.ip_address` | 扩展 `env_manager.py`，调用 ipapi/ip2location |
| P1 | **环境运行时长统计** | 记录 start→stop 的时间差，写入 `duration_seconds` | 扩展 `env_manager.py` 的 start/stop 流程 |
| P1 | **RPA 流程编排** | 可视化编排浏览器操作步骤（点击/填表/截图） | 新建 `models.RpaWorkflow` + `services/rpa_engine.py` |
| P2 | **多用户权限管理** | 用户登录、角色权限（管理员/操作员/查看者） | 新建 `models.User` + `routes/auth_routes.py` + Flask-Login |
| P2 | **分组管理 UI** | 在 Web 界面直接管理 AdsPower 分组 | 扩展 `adspower_client.py`（已有 `list_groups`）+ 前端页面 |
| P3 | **Cookie 管理** | 从环境导出/导入 Cookies | 已有 `get_cookies()` 方法，需要创建 UI |
| P3 | **代理池自动轮换** | 定时切换环境代理，记录历史 | 新建 `services/proxy_rotator.py` |
| P3 | **Webhook 通知** | 任务完成/异常时推送通知（钉钉/飞书/微信） | 新建 `services/notifier.py` |

### 11.2 架构扩展指南

#### 如何新增一个 API 端点？

```
1. 在 models.py 中添加新模型（如需要）
2. 在 adspower_client.py 中封装 AdsPower API 方法（如涉及）
3. 在 env_manager.py 中实现业务逻辑
4. 在 routes/env_routes.py 中添加 Flask 路由
5. 如有前端页面，在 templates/ 中添加模板
```

#### 如何新增一个定时任务？

```python
# 1. 在 scheduler.py 中添加任务方法
def _my_new_job(self):
    logger.info("===== 定时任务：我的新任务 =====")
    # 业务逻辑...

# 2. 在 start() 中注册
self._scheduler.add_job(
    self._my_new_job,
    trigger="interval",  # 或 "cron"
    minutes=30,
    id="my_new_job",
    name="我的新任务",
)

# 3. 如需配置化间隔，从 general_config 表读取
```

#### 如何新增一个配置类别？

```
1. 在 models.py 中新建 ORM 模型
2. 在 routes/config_routes.py 中新建 Blueprint 路由
3. 在 templates/config.html 中新增 Tab 页
4. 在 config_bp 中注册路由
```

### 11.3 未实现但 API 已封装的 AdsPower 端点

以下端点已在 `adspower_client.py` 中封装，但前端页面尚未提供 UI：

| 方法 | 端点 | 用途 |
|------|------|------|
| `new_fingerprint()` | `/api/v2/browser-profile/new-fingerprint` | 为已有环境重新随机指纹 |
| `delete_cache()` | `/api/v2/browser-profile/delete-cache` | 清除浏览器缓存 |
| `get_ua()` | `/api/v2/browser-profile/ua` | 查询环境 User-Agent |
| `get_cookies()` | `/api/v2/browser-profile/cookies` | 导出环境 Cookies |
| `list_groups()` | `/api/v1/group/list` | 获取分组列表 |
| `list_proxies()` | `/api/v2/proxy-list/list` | 获取 AdsPower 中的代理列表 |

### 11.4 性能优化方向

| 方向 | 说明 |
|------|------|
| **分页滚动** | 环境列表当前一次性加载，大量环境时需改为虚拟滚动或后端分页 |
| **数据库索引** | `created_at` 列已建索引，大数据量时可在 `env_name` 等过滤列加索引 |
| **缓存层** | 对不常变的配置（指纹池候选项等）可加 30s 内存缓存，减少 DB 查询 |
| **异步任务** | APScheduler 改为 Celery + Redis，支持分布式任务执行 |
| **WebSocket** | 浏览器启动进度可改为 WebSocket 实时推送替代轮询 |

---

## 附录 A：关键文件大小统计

| 文件 | 行数 | 说明 |
|------|------|------|
| `adspower_client.py` | 652 | API 客户端（最大文件） |
| `env_manager.py` | 741 | 业务逻辑层（最大文件） |
| `config_routes.py` | 514 | 配置路由 |
| `env_routes.py` | 420 | 环境路由 |
| `style.css` | 421 | 样式表 |
| `models.py` | 274 | 数据模型 |
| `scheduler.py` | 210 | 调度器 |
| `app.py` | 200 | Flask 工厂 |
| `log_routes.py` | 181 | 日志路由 |
| `run.py` | 97 | 入口脚本 |
| **总计** | **~3,710** | （不含模板页面） |

## 附录 B：依赖版本

```
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-CORS==4.0.0
APScheduler==3.10.4
requests==2.31.0
PyYAML==6.0.1
python-dotenv==1.0.0
loguru==0.7.2
```
