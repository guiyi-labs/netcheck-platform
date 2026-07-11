# 第 2 批实施计划：巡检执行闭环

> 日期：2026-07-11
> 前置：第 1 批登录鉴权与资产台账闭环已完成，Docker Compose 演示网络包含正常、异常、慢响应 Web 服务。
> 目标：完成「创建巡检任务 → 手动执行 → 保存原始结果 → 前端查看结果」闭环。

## 范围

- 巡检任务管理：新增、编辑、查询、启用、停用。
- 任务可关联多个资产，可选择 Ping、TCP 端口、HTTP 检测类型。
- 手动立即执行巡检任务，同步返回运行记录。
- 检测结果逐项落库，包含资产、检测类型、目标、状态、响应耗时、消息、错误信息、检测时间。
- 支持查看任务运行历史和某次运行的结果列表。
- 前端新增巡检任务页、运行详情页、巡检结果页。
- Docker 演示环境验证正常 HTTP、HTTP 500、慢响应场景。

## 暂缓

- 定时调度与周期任务。
- 诊断规则、根因分析与告警。
- 报告导出。
- 任务取消、失败重试、并发队列。
- DNS、TLS 等扩展检测。
- 根据巡检结果自动回写资产状态。

## 文件清单

后端：
- `backend/app/models/inspection.py`
- `backend/app/schemas/inspection.py`
- `backend/app/services/checkers.py`
- `backend/app/api/inspection.py`
- `backend/app/core/config.py`
- `backend/app/core/database.py`
- `backend/app/main.py`
- `backend/Dockerfile`
- `backend/tests/test_inspection.py`

前端：
- `frontend/tasks.html`
- `frontend/task-run.html`
- `frontend/results.html`
- `frontend/js/tasks.js`
- `frontend/js/task-run.js`
- `frontend/js/results.js`
- `frontend/js/auth.js`
- `frontend/css/app.css`
- `frontend/Dockerfile`

文档：
- `README.md`
- `docs/batches/2026-07-11-batch-2/plan.md`
- `docs/batches/2026-07-11-batch-2/archive.md`

## 完成标准

- 登录后可进入「巡检任务」页面创建任务。
- 可选择 1 个或多个资产，以及 Ping、端口、HTTP 检测类型。
- 已启用任务可手动执行，已停用任务禁止执行。
- 执行后生成运行记录和逐项巡检结果。
- 运行详情页可查看结果并按检测类型、状态筛选。
- Docker 演示资产可复现：HTTP 200 成功、HTTP 500 失败、慢响应警告。
- `python -m pytest -q` 全部通过。
- 受影响容器重建后端到端验证通过。
