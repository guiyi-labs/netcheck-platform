# 第 3 批完成归档：诊断与结果闭环

> 完成日期：2026-07-11
> 状态：已闭环，自动化与端到端验证通过

## 1. 功能说明

本批在第 2 批巡检执行与原始结果落库基础上，新增故障诊断能力。系统在巡检任务执行完成后，会自动分析 failed/warning 巡检结果，生成诊断记录，输出故障类型、故障等级、诊断依据和处理建议，并根据本次巡检结果回写资产当前状态。

具体能力：

- 自动生成诊断记录。
- 内置规则化诊断逻辑，覆盖 Ping、端口、HTTP 4xx/5xx、慢响应等场景。
- 诊断记录支持分页和筛选。
- 支持查看诊断详情。
- 支持对某次运行手动重新生成诊断，且重复生成保持幂等。
- 巡检完成后按资产维度自动回写 `online/offline/warning/unknown` 状态。
- 前端新增「故障诊断」页面，并在运行详情、巡检结果页提供跳转入口。

## 2. 接口清单

统一响应包络 `{code, message, data}`，需 `Authorization: Bearer {token}`。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | /api/diagnosis | 是 | 诊断记录分页列表，支持 run_id、asset_id、severity、check_type、fault_type 筛选 |
| GET | /api/diagnosis/{diagnosis_id} | 是 | 诊断详情 |
| GET | /api/diagnosis/runs/{run_id} | 是 | 查询某次运行的诊断记录 |
| POST | /api/diagnosis/runs/{run_id}/generate | 是 | 手动重新生成某次运行的诊断记录 |

诊断记录字段：

```json
{
  "id": 1,
  "run_id": 3,
  "result_id": 12,
  "asset_id": 2,
  "check_type": "http",
  "fault_type": "Web应用内部错误",
  "severity": "major",
  "suggestion": "检查Web应用日志、依赖服务和应用配置",
  "evidence": "HTTP 500",
  "created_at": "2026-07-11T..."
}
```

第 2 批接口 `POST /api/tasks/{task_id}/run` 已增强：巡检结果保存后会自动调用诊断服务并回写资产状态。

## 3. 数据库表与字段变化

在 `inspection.py` 中新增模型：

**diagnosis_records**
- id
- run_id：关联 `inspection_runs.id`
- result_id：关联 `inspection_results.id`
- asset_id：关联 `assets.id`
- check_type
- fault_type
- severity
- suggestion
- evidence
- created_at

诊断记录由 `generate_diagnoses(run_id, db)` 生成。生成前会删除同一运行的旧诊断，避免重复堆积。

本批没有新增资产状态枚举，继续使用第 1 批已有状态：

- `online`
- `offline`
- `warning`
- `unknown`

## 4. 页面与交互

### `diagnosis.html`

新增故障诊断页面，包含：

- 统计卡片：诊断总数、严重、重要、警告。
- 筛选表单：运行 ID、资产、检测类型、故障等级、故障类型。
- 诊断表格：资产、检测类型、故障类型、等级、依据、建议、时间。
- 详情弹窗：展示 run_id、result_id、asset_id、故障类型、等级、建议、诊断依据等完整信息。
- 当 URL 带 `run_id` 时，自动筛选该运行，并显示“重新生成”按钮。

### 运行详情页增强

`task-run.html` 新增“查看本次诊断”入口，随当前选中的 `run_id` 跳转到：

```text
diagnosis.html?run_id={run_id}
```

### 巡检结果页增强

`results.html` 在 URL 带 `run_id` 时显示“查看本次诊断”按钮。

### 导航与样式

- 顶部导航新增「故障诊断」。
- 新增 critical、major、minor、warning 等诊断等级样式。
- 动态内容均做 HTML 转义。

## 5. 测试结果

### 自动化测试

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
22 passed in 41.48s
```

覆盖内容：

- 诊断接口鉴权。
- 巡检执行后自动生成 HTTP 500 诊断。
- 巡检执行后自动生成慢响应诊断。
- 资产状态自动回写。
- 诊断列表筛选。
- 诊断详情 404。
- 手动重新生成诊断的幂等性。
- 第 1、2 批既有登录、资产、巡检任务测试不回退。

### 容器重建

已重建：

```powershell
docker compose up -d --build netcheck-backend netcheck-frontend
```

### 页面验证

```text
diagnosis.html=200
task-run.html=200
results.html=200
```

### 端到端验证

使用 Docker 演示资产 `demo-web-ok`、`demo-web-error`、`demo-web-slow` 执行 Ping、端口、HTTP 巡检后：

```text
RUN_STATUS=completed
DIAGNOSIS_TOTAL=2
```

诊断结果：

- `demo-web-error`：HTTP 500，生成 `Web应用内部错误`，等级 `major`。
- `demo-web-slow`：HTTP 慢响应，生成 `网络拥塞或服务性能下降`，等级 `warning`。

资产状态回写：

```text
ASSET_1_STATUS=online
ASSET_2_STATUS=warning
ASSET_3_STATUS=warning
```

## 6. 已知问题与边界

- 当前诊断规则为内置规则，不支持页面配置规则。
- 当前诊断记录只针对 failed/warning 结果生成，success 不生成正常诊断。
- 告警、确认、恢复、通知不在本批范围。
- 报告导出和趋势图不在本批范围。
- 资产状态回写基于单次运行结果，不做连续多次失败判定。

## 7. 下一批依赖

本批为后续能力提供：

- 诊断记录表与诊断接口。
- 故障类型、等级和建议数据。
- 资产状态自动回写能力。
- 诊断页面与运行结果关联入口。

下一批建议进入「看板与报告闭环」：

- 首页展示巡检/诊断统计。
- 最近异常、等级分布、资产状态分布。
- 巡检结果和诊断结果的汇总报表。
- Excel 或 CSV 报告导出。
