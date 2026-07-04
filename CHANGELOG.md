# 更新日志 (CHANGELOG)

本文档记录三星事业部管理平台的所有重要变更。

---

## [v2.1.0] - 2026-06-05

### ✨ 新增
- **配置管理模块** (`backend/config.py`)：支持环境变量覆盖所有配置项
- **统一日志管理** (`backend/logger.py`)：彩色控制台输出、文件轮转、请求追踪
- **全局中间件** (`backend/middleware.py`)：请求日志记录、统一异常处理
- **依赖注入** (`backend/dependencies.py`)：认证/权限校验标准化
- **数据分析 API** (`backend/api/analytics.py`)：业务总览、门店对比、趋势分析
- **健康检查端点** (`/api/health`)：服务状态监控
- **系统信息端点** (`/api/system/info`)：运行时配置查看
- **密码修改功能** (`POST /api/auth/change-password`)：用户自助修改密码
- **数据库迁移工具** (`scripts/migrate.py`)：版本化数据库结构升级
- **数据库备份工具** (`scripts/backup.py`)：手动备份/恢复/检查
- **系统监控脚本** (`scripts/monitor.py`)：API/数据库/磁盘/错误日志检查
- **Docker 部署支持**：Dockerfile + docker-compose.yml
- **Nginx 反向代理配置**：HTTPS/SSL/静态资源缓存
- **Windows 服务注册脚本** (`deploy/run_as_service.ps1`)：开机自启
- **一键安装脚本** (`deploy/install.bat`)：自动配置环境

### 🔧 改进
- `main.py` 重构：使用配置模块、添加中间件、增强异常处理
- `auth.py` 重构：使用依赖注入替代手动 token 解析
- `database.py` 优化：使用配置管理、添加日志记录
- `scheduler_service.py` 优化：使用配置模块消除硬编码
- `eboss_parser.py` 优化：使用配置管理 eBoss 目录路径
- `launch.bat` 增强：环境检查、自动修复、`.env` 加载
- API 错误信息更加友好和统一

### 📝 文档
- 新增 `README.md`：完整的项目说明文档
- 新增 `docs/店长操作手册.md`：店长使用指南
- 新增 `docs/管理员手册.md`：管理员配置维护指南
- 新增 `CHANGELOG.md`：版本更新记录
- 新增 `.env.example`：环境变量配置模板
- 新增 `.gitignore`：版本控制排除规则
- 新增 `requirements.txt`：标准化依赖管理

---

## [v2.0.0] - 2026-05-XX

### ✨ 新增
- 会员管理模块（完整 CRM）
  - 会员档案管理（增删改查）
  - 购机记录追踪
  - 会员等级自动升级（普通→银卡→金卡→钻石）
  - 标签管理系统（自定义标签 + 多对多关联）
  - 重点客户跟进（跟进记录 + 下次跟进提醒）
- eBoss 零售明细解析（xlsx 格式，最准确的订单数据）
- 桌面 Excel 月度进度表自动生成
- PWA 支持（Service Worker + Manifest，可离线访问）

### 🔧 改进
- 销售数据支持双数据源（钉钉 + eBoss）
- 库存预警规则引擎优化（四系列差异化）
- 价格监控增加自动更新数据库
- 前端响应式布局优化
- 移动端汉堡菜单 + 遮罩层

---

## [v1.0.0] - 2026-04-XX

### ✨ 初始版本
- 销售进度管理（月度报表、目标设置、趋势图）
- 库存监控（四系列热力图、预警规则、eBoss 导入）
- 价格看板（多平台价格对比、公司售价管理）
- 知识库（分类管理、文章 CRUD、搜索）
- 交流社区（帖子、回复、点赞、问题解决）
- 通知系统（系统通知 + 钉钉推送）
- 后台管理（用户/门店管理）
- 定时任务（eBoss 扫描、库存预警、价格检查、数据库备份）
