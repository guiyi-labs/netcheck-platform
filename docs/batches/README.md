# 分批开发归档规范

本目录是「面向中小型网络的自动化巡检与故障诊断平台」分批开发的统一归档入口，规范每批的开发文件、接口契约与验收材料。

总体路线与批次划分见 `obsidian_notes/面向中小型网络的自动化巡检与故障诊断平台_分批开发归档.md`。

## 目录结构

```
docs/batches/
├── README.md                          # 本文件：归档与开发规范
└── YYYY-MM-DD-batch-N/                 # 每批一个目录，按完成日期命名
    ├── plan.md                         # 实施计划（开发前写）
    └── archive.md                      # 完成归档（开发后写，七段式）
```

历史第 0 批计划位于 `docs/superpowers/plans/2026-07-10-docker-batch-0.md`，自第 1 批起统一迁入本结构。

## 每批归档七段式（archive.md 必须包含）

1. **功能说明**：本批交付了什么能力，用户能完成什么操作。
2. **接口清单**：新增/变更的 HTTP 接口，含方法、路径、鉴权、请求体、响应示例。
3. **数据库表与字段变化**：新增表、字段、索引、种子数据。
4. **页面与交互**：新增/变更的前端页面与关键交互。
5. **测试结果**：pytest 用例数与结果、端到端验证命令与输出。
6. **已知问题与边界**：本批未做、暂缓、待后续批次依赖的内容。
7. **下一批依赖**：本批为后续批次提供了哪些基础，下一批应做什么。

## 开发文件规范

### 后端（backend/app/）

```
app/
├── main.py            # FastAPI 入口，路由注册 + lifespan 初始化
├── core/
│   ├── config.py      # 环境配置（NETCHECK_ 前缀）
│   ├── database.py    # engine/SessionLocal/get_db/init_db
│   ├── security.py    # 密码哈希、token 生成
│   └── deps.py        # 公共依赖（鉴权等）
├── models/            # SQLAlchemy ORM 模型，每模型一个文件
├── schemas/           # Pydantic 请求/响应模型
│   └── common.py      # Response[T]/PageData[T] 统一包络
├── api/               # 路由，按资源拆分（auth.py、assets.py...）
├── seed.py            # 演示数据，幂等写入
└── checkers/          # 第 2 批起新增：巡检检测器
```

- 业务接口统一响应包络：`{code:0, message:"ok", data:any}`，`code!==0` 表示业务错误。
- 健康检查 `/health`、`/api/health` 保持直接返回字典，不包络。
- 鉴权：HTTP Bearer，token 存 `users.api_token`，登出清空。
- 配置走环境变量，前缀 `NETCHECK_`（如 `NETCHECK_DATABASE_URL`）。

### 前端（frontend/）

- 原生 JS + Bootstrap 5 CDN，无构建工具。
- 每个页面一个 HTML，公共逻辑抽到 `js/`（`api.js` 封装 fetch 与包络解析，`auth.js` 鉴权与导航）。
- 静态资源由 Nginx 提供，`/api/*` 反代到后端。
- token 存 `localStorage.netcheck_token`，401 自动跳 `login.html`。

### Docker

- `docker-compose.yml` 管理全部服务，内部网络 `netcheck-lab`。
- 数据库、报告、日志用命名 volume（`db_data`、`report_data`、`backend_logs`）。
- 演示资产优先使用 Compose 内部服务名（`demo-web-ok` 等），保证可复现。

## 测试与验收规范

- 每批必须通过 `python -m pytest -q`，用例覆盖新增接口的正常与异常路径。
- 每批必须重建受影响容器并完成端到端验证（curl + 页面可访问）。
- 验证结果记录在 `archive.md` 的「测试结果」段。

## 默认账号

- 用户名 `admin`，密码 `admin123`（仅演示，见 `backend/app/seed.py`）。
