# 第 5 批实施计划：告警与策略闭环

> 日期：2026-07-11
> 前置：第 1-4 批已完成登录、资产、巡检、诊断、看板和报告 MVP 闭环。
> 目标：把异常诊断升级为告警闭环，支持阈值策略、告警去重、确认、恢复和历史追踪。

## 范围

- 新增告警模型和告警策略模型。
- 巡检任务执行完成后，根据诊断记录和阈值策略自动评估告警。
- 支持连续失败次数阈值。
- 支持连续恢复次数阈值。
- 支持未恢复同类告警去重。
- 支持管理员确认告警。
- 支持管理员手动恢复告警。
- 支持连续正常后自动恢复告警。
- 新增告警中心页面。
- 新增告警策略配置。
- 首页仪表盘展示活跃告警、未确认告警和今日恢复告警。

## 暂缓

- 邮件通知。
- 短信通知。
- 企业微信、钉钉通知。
- 告警升级策略。
- 多用户订阅。
- 复杂规则引擎。

## 默认策略

- 连续失败阈值：3。
- 连续恢复阈值：2。
- 慢响应阈值：2000ms。
- 未恢复同类告警去重：启用。
- 策略默认启用。

## 状态流转

- `active`：活跃未确认。
- `confirmed`：已确认但未恢复。
- `recovered`：已恢复。

流程：

```text
巡检结果 -> 诊断记录 -> 告警评估 -> active -> confirmed -> recovered
                                  \-> 连续正常自动 recovered
```

## 后端接口

### 告警

- `GET /api/alerts/summary`
- `GET /api/alerts`
- `GET /api/alerts/{id}`
- `POST /api/alerts/{id}/confirm`
- `POST /api/alerts/{id}/recover`
- `POST /api/alerts/evaluate/runs/{run_id}`

### 策略

- `GET /api/alert-policy`
- `PUT /api/alert-policy`

### 看板增强

`GET /api/dashboard/summary` 新增：

- `active_alerts`
- `unconfirmed_alerts`
- `recovered_alerts_today`

## 文件清单

后端：

- `backend/app/models/alert.py`
- `backend/app/schemas/alert.py`
- `backend/app/services/alerts.py`
- `backend/app/api/alerts.py`
- `backend/app/api/inspection.py`
- `backend/app/api/dashboard.py`
- `backend/app/schemas/dashboard.py`
- `backend/app/core/database.py`
- `backend/app/main.py`
- `backend/tests/test_alerts.py`

前端：

- `frontend/alerts.html`
- `frontend/js/alerts.js`
- `frontend/index.html`
- `frontend/js/dashboard.js`
- `frontend/js/auth.js`
- `frontend/css/app.css`
- `frontend/Dockerfile`

文档：

- `README.md`
- `docs/batches/2026-07-11-batch-5/plan.md`
- `docs/batches/2026-07-11-batch-5/archive.md`

## 完成标准

- 异常巡检达到连续失败阈值后自动生成告警。
- 同一资产、检测类型和故障类型在未恢复前不重复生成新告警。
- 告警包含等级、状态、依据、建议、触发次数、首次和最近触发时间。
- 管理员可确认告警。
- 管理员可手动恢复告警。
- 连续正常达到恢复阈值后自动恢复告警。
- 告警中心支持分页、筛选和详情查看。
- 告警策略可查看和修改。
- 首页仪表盘展示告警统计。
- 自动化测试和 Docker 端到端验证通过。
