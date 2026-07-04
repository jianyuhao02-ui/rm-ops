# 三星事业部统一管理平台 v2.1

**贵州沣范通讯设备有限公司** - 三星事业部运营管理平台

---

## 📋 系统概述

本系统是三星事业部的核心运营管理平台，覆盖以下业务模块：

| 模块 | 功能 |
|------|------|
| 📊 **数据总览** | 销售统计卡片、趋势图表、门店排名、库存预警、价格异常 |
| 💰 **销售进度** | 月度销售报表、完成率热力图、目标管理、Excel 导出 |
| 📦 **库存监控** | 四系列库存热力图、预警规则引擎、eBoss 自动导入 |
| 💲 **价格看板** | 各平台价格对比、公司售价管理、价格变动监控 |
| 👥 **会员管理** | 会员档案、购机记录、等级自动升级、标签管理、跟进记录 |
| 📚 **店长百事通** | 产品知识、销售话术、SOP 流程、竞品分析知识库 |
| 💬 **交流社区** | 帖子发布、回复互动、点赞、问题解决标记 |
| ⚙️ **后台管理** | 用户管理、门店管理、系统设置、eBoss 同步状态 |

### 🔄 自动化功能

- **eBoss 自动同步**：每小时扫描 eBoss 导出目录，自动导入销售/库存数据
- **库存预警**：每周一/四 9:30 自动检查四系列库存，推送钉钉通知
- **价格监控**：每日 10:00 爬取九机网价格，检测变动并通知
- **数据库备份**：每日凌晨 3:00 自动备份，保留 7 天

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- Windows 10/11 或 Linux

### 一键安装部署

```bash
# 1. 双击运行安装脚本
deploy\install.bat

# 2. 或手动安装
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r requirements.txt

# 3. 启动服务
launch.bat
```

> 跨平台提示：macOS / Linux 下将 `backend\.venv\Scripts\pip` 替换为 `backend/.venv/bin/pip`，将 `launch.bat` 替换为 `python main.py`。

访问地址：**http://localhost:9527**

### 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | `admin` | `admin123` |
| 店长 | `store1` ~ `store10` | `store123` |

---

## 📁 项目结构

```
samsung-ops/
├── main.py                    # FastAPI 主入口
├── launch.bat                 # 一键启动脚本
├── requirements.txt           # Python 依赖
├── .env.example               # 环境变量模板
├── backend/
│   ├── config.py              # 配置管理（环境变量）
│   ├── logger.py              # 日志管理
│   ├── middleware.py           # 中间件（请求日志、异常处理）
│   ├── dependencies.py        # 依赖注入（认证、权限）
│   ├── api/                   # API 路由
│   │   ├── auth.py            # 认证（JWT）
│   │   ├── sales.py           # 销售数据
│   │   ├── inventory.py       # 库存监控
│   │   ├── prices.py          # 价格看板
│   │   ├── knowledge.py       # 知识库
│   │   ├── community.py       # 交流社区
│   │   ├── notify.py          # 通知系统
│   │   ├── eboss.py           # eBoss 同步
│   │   ├── member.py          # 会员管理
│   │   └── analytics.py       # 数据分析（新增）
│   ├── models/
│   │   └── database.py        # SQLite 数据库
│   └── services/
│       ├── scheduler_service.py  # 定时任务
│       ├── eboss_parser.py       # eBoss 解析
│       └── dingtalk_service.py   # 钉钉推送
├── frontend/                  # 前端页面（原生 HTML/CSS/JS）
│   ├── index.html
│   ├── css/style.css
│   ├── js/app.js              # 公共模块
│   ├── pages/                 # 业务页面
│   └── icons/                 # PWA 图标
├── scripts/                   # 工具脚本
│   ├── backup.py              # 数据库备份/恢复
│   └── migrate.py             # 数据库迁移
├── deploy/                    # 部署配置
│   ├── install.bat            # 一键安装
│   ├── Dockerfile             # Docker 镜像
│   ├── docker-compose.yml     # Docker Compose
│   ├── nginx.conf             # Nginx 配置
│   └── run_as_service.ps1     # Windows 服务注册
├── data/                      # 数据库文件
└── logs/                      # 日志文件
```

---

## ⚙️ 环境变量配置

复制 `.env.example` 为 `.env` 并修改：

```bash
# 服务器端口
SAMSUNG_PORT=9527

# JWT 密钥（生产环境必须修改！）
SAMSUNG_SECRET_KEY=your-random-secret-key

# 钉钉通知（可选）
SAMSUNG_DINGTALK_ACCESS_TOKEN=your-token

# eBoss 目录
SAMSUNG_EBOSS_DIR=C:\eBoss\Local
```

---

## 🐳 Docker 部署

```bash
# 构建并启动
cd deploy
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

---

## 📊 数据库

### 表结构（17 张表）

| 表名 | 说明 |
|------|------|
| `users` | 用户表 |
| `stores` | 门店表 |
| `monthly_targets` | 月度目标 |
| `daily_sales` | 每日销售 |
| `inventory` | 库存 |
| `price_records` | 价格记录 |
| `kb_categories` / `kb_articles` | 知识库 |
| `community_posts` / `community_comments` | 社区 |
| `notifications` | 通知 |
| `alert_rules` | 预警规则 |
| `members` / `member_purchases` | 会员 |
| `member_tag_defs` / `member_tags` | 标签 |
| `member_followups` | 跟进记录 |
| `eboss_sync_log` | 同步日志 |

### 备份与恢复

```bash
# 手动备份
python scripts/backup.py backup

# 查看备份列表
python scripts/backup.py list

# 从备份恢复
python scripts/backup.py restore --file <备份文件路径>

# 数据库检查
python scripts/backup.py check
```

---

## 🔧 维护指南

### 日常维护

1. **检查服务状态**：访问 http://localhost:9527 确认页面正常加载
2. **查看日志**：`logs/` 目录下查看各模块日志
3. **数据库备份**：每日凌晨 3:00 自动备份到桌面 `samsung_ops_backup/`

### 常见问题

| 问题 | 解决方案 |
|------|----------|
| 服务无法启动 | 运行 `deploy/install.bat` 重装依赖 |
| 数据库错误 | 运行 `fix_and_start.py` 修复 |
| eBoss 不自动同步 | 检查 `C:\eBoss\Local\` 目录是否有新文件 |
| 钉钉通知不发送 | 检查 `SAMSUNG_DINGTALK_ACCESS_TOKEN` 配置 |
| 端口被占用 | 修改 `.env` 中的 `SAMSUNG_PORT` |

### 升级步骤

```bash
# 1. 停止服务（Ctrl+C）
# 2. 备份数据库
python scripts/backup.py backup

# 3. 拉取新代码
git pull

# 4. 更新依赖
backend\.venv\Scripts\pip install -r requirements.txt

# 5. 运行数据库迁移
python scripts/migrate.py

# 6. 重启服务
launch.bat
```

---

## 🔐 安全建议

1. **生产环境务必修改** `SAMSUNG_SECRET_KEY`
2. **修改默认管理员密码**（登录后在后台管理页面操作）
3. **使用 HTTPS**（通过 Nginx 反向代理配置 SSL）
4. **定期备份数据库**
5. **限制 CORS 来源**（`.env` 中配置 `SAMSUNG_CORS_ORIGINS`）

---

## 📝 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v2.1 | 2026-06 | 配置管理模块、统一异常处理、数据分析 API、Docker 部署、文档完善 |
| v2.0 | 2026-05 | 会员管理模块、eBoss 明细解析、Excel 自动生成、PWA 支持 |
| v1.0 | 2026-04 | 初始版本：销售/库存/价格/知识库/社区/通知 |

---

## 📧 技术支持

贵州沣范通讯设备有限公司 - 三星事业部
