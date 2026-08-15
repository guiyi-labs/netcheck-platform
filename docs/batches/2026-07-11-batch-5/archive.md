# 第 5 批完成归档：告警与策略闭环

> 完成日期：2026-07-11
> 状态：已闭环，自动化与端到端验证通过

## 1. 功能说明

本批在第 1-4 批资产、巡检、诊断、看板和报告基础上，新增告警与策略闭环能力。系统在巡检完成并生成诊断后，会根据告警策略判断是否触发告警；同一资产、同一检测类型、同一故障类型在未恢复前不会重复生成新告警；管理员可以确认和手动恢复告警；系统也支持连续正常后自动恢复。

完成能力：

- 告警模型与告警策略模型。
- 巡检完成后自动评估告警。
- 连续失败阈值触发。
- 连续恢复阈值自动恢复。
- 未恢复同类告警去重。
- 告警确认。
- 手动恢复。
- 告警分页与筛选。
- 告警详情。
- 告警策略查看和修改。
- 告警中心前端页面。
- 首页仪表盘展示告警统计。

## 2. 接口清单

统一响应包络 `{code, message, data}`，业务接口均需 `Authorization: Bearer {token}`。

### 告警接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/alerts/summary | 告警统计 |
| GET | /api/alerts | 告警分页列表 |
| GET | /api/alerts/{id} | 告警详情 |
| POST | /api/alerts/{id}/confirm | 确认告警 |
| POST | /api/alerts/{id}/recover | 手动恢复告警 |
| POST | /api/alerts/evaluate/runs/{run_id} | 手动重新评估某次运行告警 |

列表支持筛选：

- `alert_status`
- `alert_level`
- `asset_id`
- `check_type`
- `fault_type`

### 策略接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/alert-policy | 获取默认策略 |
| PUT | /api/alert-policy | 更新默认策略 |

策略字段：

- `enabled`
- `slow_response_threshold`
- `failure_threshold`
- `recovery_threshold`
- `deduplicate_enabled`

## 3. 数据库变化

新增表：

**alerts**

- id
- asset_id
- run_id
- result_id
- diagnosis_id
- alert_title
- alert_level
- alert_status
- alert_key
- check_type
- fault_type
- evidence
- suggestion
- first_triggered_at
- last_triggered_at
- trigger_count
- consecutive_failures
- consecutive_successes
- confirmed_by
- confirmed_at
- recovered_at
- recovery_reason
- created_at
- updated_at

**alert_policies**

- id
- name
- enabled
- slow_response_threshold
- failure_threshold
- recovery_threshold
- deduplicate_enabled
- created_at
- updated_at

默认策略：

```text
failure_threshold=3
recovery_threshold=2
slow_response_threshold=2000
deduplicate_enabled=true
enabled=true
```

## 4. 告警规则与状态流转

### 触发逻辑

- 基于诊断记录生成告警。
- 告警去重键：`asset_id:check_type:fault_type`。
- 若未恢复同类告警已存在，则更新触发次数和最近触发时间，不新增告警。
- 若未恢复同类告警不存在，且连续异常次数达到策略阈值，则创建 `active` 告警。

### 恢复逻辑

- 同一资产和检测类型连续成功次数达到恢复阈值后，自动恢复未恢复告警。
- 管理员也可手动恢复告警。

### 状态

- `active`：活跃未确认。
- `confirmed`：已确认未恢复。
- `recovered`：已恢复。

## 5. 页面与交互

### 告警中心 `alerts.html`

包含：

- 活跃告警、未确认告警、今日恢复、告警总数统计卡片。
- 告警策略配置折叠卡片。
- 筛选栏：状态、等级、资产 ID、检测类型、故障类型。
- 告警列表。
- 告警详情弹窗。
- 确认告警按钮。
- 手动恢复按钮。

### 首页仪表盘增强

新增展示：

- 活跃告警。
- 未确认告警。
- 今日恢复告警。

### 导航

顶部导航新增「告警中心」。

## 6. 测试结果

### 自动化测试

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
31 passed in 135.39s
```

覆盖内容：

- 告警接口鉴权。
- 策略读取和更新。
- 连续失败阈值触发。
- 未恢复同类告警去重。
- 告警确认。
- 自动恢复。
- 手动恢复。
- 告警筛选。
- 首页看板告警统计。
- 第 1-4 批既有功能不回退。

### 容器验证

已重建：

```powershell
docker compose up -d --build netcheck-backend netcheck-frontend
```

页面访问：

```text
alerts.html=200
index.html=200
```

### 端到端验证

为便于演示，将策略临时设置为：

```text
failure_threshold=1
recovery_threshold=1
```

执行异常巡检后验证：

```text
POLICY_FAILURE=1
RUN_ID=4
ALERT_ID=1
ALERT_LEVEL=major
ALERT_STATUS=active
CONFIRMED_STATUS=confirmed
RECOVERED_STATUS=recovered
ACTIVE_ALERTS=0
RECOVERED_TODAY=1
```

验证完成后已恢复默认策略：

```text
POLICY_FAILURE=3
POLICY_RECOVERY=2
```

## 7. 已知问题与边界

- 当前告警仅为系统内告警，不包含邮件、短信、企业微信、钉钉通知。
- 当前策略为全局默认策略，不支持按资产、任务或检测类型配置多策略。
- 当前告警恢复基于连续成功次数，不做复杂维护窗口或告警抑制。
- 当前未实现告警升级、通知订阅和多用户分派。

## 8. 项目闭环状态

截至第 5 批，系统已具备：

- 登录鉴权。
- 资产台账。
- 巡检任务。
- Ping、端口、HTTP 检测。
- 巡检结果留痕。
- 规则化故障诊断。
- 资产状态回写。
- 仪表盘。
- 全局结果查询。
- Excel 报告。
- 告警生成、确认、恢复和策略配置。

## 9. 后续建议

后续可作为扩展或文档展望：

- 邮件 / 企业微信 / 钉钉通知。
- 告警升级和分派。
- 按资产或服务类型配置多策略。
- 巡检定时调度。
- 拓扑展示和资产发现。
