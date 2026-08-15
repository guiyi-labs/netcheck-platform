# 第 4 批实施计划：看板与报告闭环

> 日期：2026-07-11
> 前置：第 1-3 批已完成登录鉴权、资产台账、巡检执行、结果落库、故障诊断和资产状态回写。
> 目标：补齐仪表盘、全局结果查询和 Excel 报告导出，形成可演示 MVP 闭环。

## 范围

- 首页仪表盘增强：核心指标、资产状态分布、巡检趋势、故障类型分布、最近异常。
- 全局巡检结果查询：支持按运行、任务、资产、检测类型、状态和时间范围筛选。
- 报告管理：生成运行报告、生成日报、报告列表、下载、删除。
- Excel 报告内容包含巡检概况、异常资产、故障类型、处理建议。
- 报告文件保存到 `/app/reports`，通过 Docker volume 持久化。

## 暂缓

- PDF 报告。
- 复杂报表模板。
- 多维度历史分析。
- 告警确认、恢复和通知。
- 阈值策略配置。

## 后端接口

### 看板

- `GET /api/dashboard/summary`
- `GET /api/dashboard/asset-status`
- `GET /api/dashboard/trend?days=7`
- `GET /api/dashboard/fault-types?days=7`
- `GET /api/dashboard/recent-abnormal?limit=10`

### 巡检结果

- `GET /api/results`

支持：

- `page`
- `page_size`
- `run_id`
- `task_id`
- `asset_id`
- `check_type`
- `status`
- `start_date`
- `end_date`

### 报告

- `POST /api/reports/generate`
- `GET /api/reports`
- `GET /api/reports/{id}/download`
- `DELETE /api/reports/{id}`

## 文件清单

后端：

- `backend/app/api/dashboard.py`
- `backend/app/api/results.py`
- `backend/app/api/reports.py`
- `backend/app/schemas/dashboard.py`
- `backend/app/schemas/result.py`
- `backend/app/schemas/report.py`
- `backend/app/models/report.py`
- `backend/app/services/report.py`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/app/core/database.py`
- `backend/requirements.txt`
- `backend/tests/test_dashboard_results_reports.py`

前端：

- `frontend/index.html`
- `frontend/js/dashboard.js`
- `frontend/results.html`
- `frontend/js/results.js`
- `frontend/reports.html`
- `frontend/js/reports.js`
- `frontend/js/auth.js`
- `frontend/css/app.css`
- `frontend/Dockerfile`

文档：

- `README.md`
- `docs/batches/2026-07-11-batch-4/plan.md`
- `docs/batches/2026-07-11-batch-4/archive.md`

## 完成标准

- 登录后首页展示看板指标、图表和最近异常。
- 巡检结果页可进行全局查询和筛选。
- 报告管理页可生成、下载和删除 Excel 报告。
- Excel 报告包含巡检概况、异常资产、故障类型和处理建议。
- 自动化测试全部通过。
- Docker 环境端到端验证通过。
