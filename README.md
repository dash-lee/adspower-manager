# AdsPower 环境管理后台

基于 Flask 的 AdsPower 浏览器环境管理系统，提供：
- 🔌 **AdsPower API 全功能封装** - 使用 v2 接口，支持环境 CRUD、浏览器控制
- 🎲 **随机指纹生成** - 从配置池中按权重随机选取指纹参数
- ⚙️ **后台配置管理** - Web 界面操作，修改即时生效
- 📋 **任务队列** - 支持创建/删除任务的排队处理
- ⏰ **定时调度** - 自动处理任务、状态检查、日志清理
- 📊 **数据统计** - 操作日志、环境运行日志持久化存储
- 🚀 **VPS 就绪** - 轻量 SQLite，迁移只需改数据库 URL

## 快速开始

### 1. 安装依赖

```bash
cd adspower-manager
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python run.py
```

默认访问地址: http://localhost:5000/dashboard

### 3. 初始化配置

1. 打开 http://localhost:5000/config → 通用配置
2. 设置 `adspower_api_url`（默认 http://local.adspower.net:50325）
3. 设置 `adspower_api_key`（在 AdsPower 客户端 → 自动化 → API 中获取）
4. 点击「初始化默认值」自动填充指纹池候选项
5. 添加代理配置（如需要）

### 4. 使用

- **仪表盘** - 查看系统状态，执行初始化检查
- **环境管理** - 创建/删除/启动/关闭浏览器环境
- **配置管理** - 调整所有系统参数
- **日志查看** - 查看操作日志和环境运行记录

## 项目结构

```
adspower-manager/
├── backend/
│   ├── app.py                      # Flask 主应用
│   ├── database.py                 # 数据库初始化
│   ├── models.py                   # ORM 数据模型（7个表）
│   ├── routes/
│   │   ├── config_routes.py        # 配置管理 API
│   │   ├── env_routes.py           # 环境管理 API
│   │   └── log_routes.py           # 日志 API
│   ├── services/
│   │   ├── adspower_client.py      # AdsPower API 客户端（20+端点）
│   │   ├── env_manager.py          # 环境业务逻辑
│   │   └── scheduler.py            # APScheduler 定时调度
│   ├── templates/                  # Jinja2 前端页面
│   │   ├── base.html               # 基础布局
│   │   ├── dashboard.html          # 仪表盘
│   │   ├── config.html             # 配置管理
│   │   ├── environments.html       # 环境管理
│   │   └── logs.html               # 日志查看
│   └── static/
│       ├── css/style.css           # 暗色主题样式
│       └── js/app.js               # 通用 JS 工具
├── data/                           # SQLite 数据库和日志文件
├── requirements.txt
├── run.py                          # 启动脚本
└── README.md
```

## 数据库表

| 表名 | 说明 |
|------|------|
| `general_config` | 通用配置（API地址、密钥、轮询间隔等） |
| `proxy_config` | 代理配置（主机、端口、用户名、密码） |
| `fingerprint_pool` | 指纹随机池（屏幕分辨率、CPU、内存等候选值） |
| `preserved_env` | 环境保留列表（不被自动删除） |
| `task_queue` | 任务队列（创建/删除/更新） |
| `operation_log` | 操作日志（API调用、错误等） |
| `env_runtime_log` | 环境运行日志（IP、运行时长等） |

## API 端点概览

### 配置管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/config/general` | 通用配置 |
| GET/POST | `/api/config/proxy` | 代理配置 |
| GET/POST | `/api/config/fingerprint` | 指纹随机池 |
| GET/POST | `/api/config/preserved` | 环境保留 |
| POST | `/api/config/init_defaults` | 初始化默认值 |

### 环境管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/env/check` | 初始化检查 |
| GET | `/api/env/list` | 环境列表（分页） |
| POST | `/api/env/create` | 创建环境 |
| POST | `/api/env/delete` | 批量删除 |
| POST | `/api/env/update` | 更新环境 |
| POST | `/api/env/browser/start` | 启动浏览器 |
| POST | `/api/env/browser/stop` | 关闭浏览器 |

### 日志
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs/operation` | 操作日志 |
| GET | `/api/logs/environment` | 环境运行日志 |
| GET | `/api/logs/stats` | 日志统计 |

## VPS 部署

```bash
# 1. 上传代码到 VPS
scp -r adspower-manager/ user@vps:/opt/

# 2. 安装依赖
cd /opt/adspower-manager
pip install -r requirements.txt

# 3. 后台运行（使用 systemd 或 supervisor）
# systemd 示例 (/etc/systemd/system/adspower-manager.service):
# [Unit]
# Description=AdsPower Manager
# After=network.target
#
# [Service]
# User=youruser
# WorkingDirectory=/opt/adspower-manager
# ExecStart=/usr/bin/python3 run.py --host 0.0.0.0 --port 5000
# Restart=always
#
# [Install]
# WantedBy=multi-user.target

# 或者直接使用 nohup
nohup python run.py --host 0.0.0.0 --port 5000 > data/server.log 2>&1 &
```

## 后续计划

- [ ] Selenium 自动化集成（模拟操作环境）
- [ ] RPA 流程编排
- [ ] 代理 IP 检测与记录
- [ ] 环境运行时长统计
- [ ] 多用户权限管理
