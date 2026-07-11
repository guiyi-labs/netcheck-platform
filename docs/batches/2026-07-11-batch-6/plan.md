# 第 6 批实施计划：定时巡检与网络可视化扩展闭环

> 日期：2026-07-11
> 前置：第 1-5 批已完成登录、资产、巡检、诊断、看板、报告和告警闭环。
> 目标：补齐自动化巡检和网络工程展示能力，新增 DNS 检测、定时巡检、轻量资产发现和逻辑拓扑。

## 范围

- 新增 DNS 检测类型，纳入巡检任务、结果、诊断、报告与查询链路。
- 巡检任务支持定时配置，后端通过 APScheduler 自动执行。
- 新增调度器状态接口。
- 新增轻量资产发现能力，支持授权范围内 IP 列表和小 CIDR 扫描。
- 发现结果支持导入资产台账，并防止重复 IP 导入。
- 新增逻辑拓扑接口和页面，基于资产状态展示网络拓扑。
- 前端任务页支持 DNS 和定时配置。
- 新增资产发现页和逻辑拓扑页。

## 暂缓

- Nmap 集成。
- 大网段高速扫描。
- MAC 地址、厂商、服务指纹识别。
- SNMP、LLDP、CDP 自动拓扑发现。
- Traceroute 拓扑推断。
- 拓扑拖拽编辑和版本管理。
- 分布式调度、Celery、Redis、Cron 表达式编辑器。
- TLS、Docker API、Kubernetes、Prometheus 扩展。

## 后端接口

### 调度器

- `GET /api/scheduler/status`

### 巡检任务增强

任务请求和响应新增：

- `schedule_enabled`
- `schedule_interval_minutes`
- `next_run_at`
- `last_scheduled_run_at`

运行记录新增：

- `trigger_type`：`manual` 或 `scheduled`

检测类型新增：

- `dns`

### 资产发现

- `POST /api/discovery/scans`
- `GET /api/discovery/scans`
- `GET /api/discovery/scans/{id}/results`
- `POST /api/discovery/results/{id}/import`

### 逻辑拓扑

- `GET /api/topology`

## 数据模型

### inspection_tasks 新增字段

- `schedule_enabled`
- `schedule_interval_minutes`
- `next_run_at`
- `last_scheduled_run_at`

### inspection_runs 新增字段

- `trigger_type`

### discovery_scans

- id
- target_range
- scan_mode
- ports
- status
- total_targets
- discovered_count
- error_message
- started_at
- finished_at

### discovery_results

- id
- scan_id
- ip
- hostname
- open_ports
- status
- already_exists
- matched_asset_id
- imported_asset_id
- created_at

## 文件清单

后端：

- `backend/requirements.txt`
- `backend/app/models/inspection.py`
- `backend/app/models/discovery.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/discovery.py`
- `backend/app/schemas/topology.py`
- `backend/app/services/checkers.py`
- `backend/app/services/diagnosis.py`
- `backend/app/services/scheduler.py`
- `backend/app/services/discovery.py`
- `backend/app/api/inspection.py`
- `backend/app/api/scheduler.py`
- `backend/app/api/discovery.py`
- `backend/app/api/topology.py`
- `backend/app/main.py`
- `backend/app/core/database.py`
- `backend/tests/test_inspection.py`
- `backend/tests/test_discovery.py`
- `backend/tests/test_topology.py`

前端：

- `frontend/tasks.html`
- `frontend/js/tasks.js`
- `frontend/discovery.html`
- `frontend/js/discovery.js`
- `frontend/topology.html`
- `frontend/js/topology.js`
- `frontend/js/auth.js`
- `frontend/css/app.css`
- `frontend/Dockerfile`

文档：

- `README.md`
- `docs/batches/2026-07-11-batch-6/plan.md`
- `docs/batches/2026-07-11-batch-6/archive.md`

## 完成标准

- 巡检任务可选择 DNS 检测。
- DNS 检测结果能够落库并进入结果查询。
- DNS 异常能够生成诊断记录。
- 巡检任务可配置定时执行。
- 调度器启动后可加载定时任务。
- 定时执行可复用诊断、告警和资产状态回写流程。
- 资产发现支持授权小范围扫描。
- 发现结果可导入资产台账。
- 拓扑页可按资产状态展示节点颜色。
- 自动化测试全部通过。
- Docker 环境页面和接口端到端验证通过。
