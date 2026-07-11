# 第 2 批完成归档：巡检执行闭环

> 完成日期：2026-07-11
> 状态：已闭环，自动化与端到端验证通过

## 1. 功能说明

本批完成了平台的巡检执行闭环。管理员登录后可进入巡检任务页，创建可关联多个资产的巡检任务，并选择 Ping、TCP 端口、HTTP 检测类型。任务启用后可手动立即执行，系统会同步生成运行记录、保存每一项巡检结果，并在前端查看运行详情与逐项结果。

具体能力：

- 巡检任务新增、编辑、启用、停用、查询。
- 任务支持多资产、多检测类型组合。
- 手动立即执行任务，生成运行记录。
- 逐项巡检结果落库，包含目标、状态、响应耗时、消息、错误信息、检测时间。
- 前端支持巡检任务列表、运行详情页、巡检结果页。
- 演示环境可稳定复现 Ping、端口、HTTP 正常、HTTP 500、慢响应场景。

## 2. 接口清单

统一响应包络：`{code, message, data}`，除健康检查外其余接口均需 `Authorization: Bearer {token}`。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | /api/tasks | 是 | 巡检任务分页列表 |
| POST | /api/tasks | 是 | 新建巡检任务 |
| GET | /api/tasks/{task_id} | 是 | 任务详情 |
| PUT | /api/tasks/{task_id} | 是 | 更新任务 |
| POST | /api/tasks/{task_id}/enable | 是 | 启用任务 |
| POST | /api/tasks/{task_id}/disable | 是 | 停用任务 |
| POST | /api/tasks/{task_id}/run | 是 | 立即执行任务，返回运行记录 |
| GET | /api/tasks/{task_id}/runs | 是 | 任务运行历史 |
| GET | /api/tasks/runs/{run_id}/results | 是 | 某次运行的逐项结果 |

执行接口返回的运行记录包含：`id`、`task_id`、`status`、`started_at`、`finished_at`、`error_message`。

结果接口返回的结果包含：`id`、`run_id`、`asset_id`、`check_type`、`target`、`status`、`response_time`、`message`、`error_message`、`checked_at`。

## 3. 数据库表与字段变化

新增表：

**inspection_tasks**
- id, name, description, check_types, enabled, created_at, updated_at

**inspection_task_assets**
- task_id, asset_id

**inspection_runs**
- id, task_id, status, started_at, finished_at, error_message

**inspection_results**
- id, run_id, asset_id, check_type, target, status, response_time, message, error_message, checked_at

说明：

- `check_types` 使用逗号分隔字符串存储，API 层以数组交互。
- 任务与资产采用多对多关联。
- 结果关联具体运行批次，便于历史追溯。
- 后端启动时已通过 `init_db` 显式导入新增模型并建表。

种子数据：
- 复用第 1 批的 12 条资产。
- 演示任务可由管理员在前端创建并执行。

## 4. 页面与交互

### `tasks.html`

- 任务列表展示名称、检测类型、资产数、启用状态、描述和操作。
- 支持新建/编辑任务弹窗。
- 支持资产多选、检测类型多选、启用状态切换。
- 支持启用、停用、立即执行、查看运行记录。

### `task-run.html`

- 展示任务摘要与运行记录列表。
- 可查看单次运行的结果表。
- 支持按检测类型、结果状态筛选。
- 支持查看结果详情弹窗。

### `results.html`

- 通过 `run_id` 查看某次运行结果。
- 支持按检测类型、状态筛选。
- 支持结果详情弹窗。
- 无 `run_id` 时提示用户从任务执行流程进入。

### 导航与样式

- 顶部导航新增「巡检任务」「巡检结果」。
- 新增巡检状态、运行状态、结果状态样式。
- 新增多选资产列表与长文本截断样式。
- 前端动态内容已做 HTML 转义。

## 5. 测试结果

### 自动化测试

使用项目虚拟环境执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
18 passed in 25.26s
```

覆盖内容：

- 登录鉴权。
- 巡检任务创建、编辑、启停。
- 任务执行后运行记录与结果查询。
- 检查器异常时结果可落库且不阻塞整次任务。
- 停用任务不可执行（HTTP 409）。

### 容器重建

已重建受影响服务：

- `netcheck-backend`
- `netcheck-frontend`

### 端到端验证

已在 Docker 演示环境完成验证：

- `tasks.html`、`task-run.html`、`results.html` 均可访问（HTTP 200）。
- 巡检任务执行成功生成运行记录。
- 三个演示资产共 9 项巡检结果，状态分布正确。
- Ping 已在后端容器补装 `iputils-ping` 后恢复正常。
- 典型结果：
  - `demo-web-ok`：Ping 成功、端口成功、HTTP 200 成功。
  - `demo-web-error`：Ping 成功、端口成功、HTTP 500 失败。
  - `demo-web-slow`：Ping 成功、端口成功、HTTP 慢响应警告。

## 6. 已知问题与边界

- 当前巡检为手动执行，不包含定时调度。
- 未实现诊断规则、根因分析与告警。
- 未实现报告导出与任务取消。
- HTTP 慢响应阈值目前为配置项，适合演示但不是完整 SLA 引擎。
- 当前演示任务以手动选择资产为主，未做更复杂的资产分组和模板化策略。

## 7. 下一批依赖

本批为后续能力提供了基础：

- 巡检任务与结果数据模型。
- 执行记录与结果追溯能力。
- Ping、TCP、HTTP 检测器抽象。
- 运行详情与结果查看页面。
- 可复现的演示巡检目标。

下一批可在此基础上继续扩展：

- 定时巡检与周期任务。
- 诊断规则与异常分类。
- 告警与通知。
- 报告导出。
- 更细粒度的结果统计与趋势分析。
