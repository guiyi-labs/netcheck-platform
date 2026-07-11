# 第 3 批实施计划：诊断与结果闭环

> 日期：2026-07-11
> 前置：第 2 批巡检任务、手动执行、原始结果落库和前端结果查看已闭环。
> 目标：基于巡检结果自动生成故障诊断记录，给出故障类型、等级和处理建议，并根据最新结果回写资产状态。

## 范围

- 新增诊断记录模型，关联巡检运行、巡检结果和资产。
- 新增规则化诊断服务，根据 Ping、端口、HTTP、慢响应结果生成诊断。
- 巡检任务执行完成后自动生成诊断记录。
- 巡检任务执行完成后按资产维度回写资产状态。
- 新增诊断记录查询接口，支持分页和按运行、资产、等级、检测类型、故障类型筛选。
- 新增故障诊断前端页面。
- 在运行详情页和巡检结果页增加“查看诊断”入口。

## 诊断规则

| 条件 | 故障类型 | 等级 | 建议 |
|---|---|---|---|
| Ping 失败 | 主机离线或链路异常 | critical | 检查主机连通性、网络链路及设备电源状态 |
| 端口失败 | 服务未启动或防火墙拦截 | major | 确认服务已启动，并检查防火墙和安全组放行规则 |
| HTTP 4xx | 请求路径或访问权限异常 | minor | 检查请求路径、访问权限及认证配置 |
| HTTP 5xx | Web应用内部错误 | major | 检查 Web 应用日志、依赖服务和应用配置 |
| warning 或响应时间超过阈值 | 网络拥塞或服务性能下降 | warning | 检查网络带宽、链路质量及服务资源使用情况 |
| 其它 HTTP 失败 | Web服务访问异常 | major | 检查 Web 服务进程、网络连接及访问配置 |

## 资产状态回写规则

- 存在 Ping 失败：`offline`
- 否则存在任意失败：`warning`
- 否则存在任意警告：`warning`
- 否则有结果且全部成功：`online`
- 无结果：`unknown`

## 暂缓

- 告警生成、确认、恢复。
- 连续失败阈值和告警降噪。
- 报告导出。
- 仪表盘趋势图。
- 可视化规则编辑器。
- AI 自动诊断。

## 文件清单

后端：
- `backend/app/models/inspection.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/services/diagnosis.py`
- `backend/app/api/diagnosis.py`
- `backend/app/api/inspection.py`
- `backend/app/main.py`
- `backend/tests/test_inspection.py`

前端：
- `frontend/diagnosis.html`
- `frontend/js/diagnosis.js`
- `frontend/task-run.html`
- `frontend/js/task-run.js`
- `frontend/results.html`
- `frontend/js/results.js`
- `frontend/js/auth.js`
- `frontend/css/app.css`
- `frontend/Dockerfile`

文档：
- `README.md`
- `docs/batches/2026-07-11-batch-3/plan.md`
- `docs/batches/2026-07-11-batch-3/archive.md`

## 完成标准

- 执行巡检任务后，系统自动为 failed/warning 结果生成诊断记录。
- 每条诊断记录包含故障类型、故障等级、诊断依据和处理建议。
- 故障诊断页面可查看和筛选诊断记录。
- 运行详情页和巡检结果页可跳转到对应运行的诊断结果。
- 资产状态可随最新巡检结果自动更新。
- 自动化测试全部通过。
- Docker 演示环境端到端验证通过。
