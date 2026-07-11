# 第 4 批完成归档：看板与报告闭环

> 完成日期：2026-07-11
> 状态：已闭环，自动化与端到端验证通过

## 1. 功能说明

本批在第 1-3 批资产、巡检、结果、诊断能力基础上，补齐仪表盘、全局结果查询和 Excel 报告导出，形成从登录、资产查看、巡检执行、结果查询、故障诊断到报告生成下载的 MVP 演示闭环。

完成能力：

- 首页仪表盘展示资产、任务、运行、异常和诊断核心指标。
- ECharts 展示资产状态分布、最近 7 天巡检/异常趋势、故障类型分布。
- 首页展示最近异常结果列表。
- 巡检结果页从单次运行结果扩展为全局结果查询。
- 报告管理页支持生成运行报告和日报。
- 报告列表支持筛选、下载和删除。
- 后端使用 `openpyxl` 生成 Excel 文件，并保存到 `/app/reports`。

## 2. 接口清单

统一响应包络 `{code, message, data}`，文件下载接口除外。业务接口均需 `Authorization: Bearer {token}`。

### 看板接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/dashboard/summary | 核心指标 |
| GET | /api/dashboard/asset-status | 资产状态分布 |
| GET | /api/dashboard/trend?days=7 | 最近巡检与异常趋势 |
| GET | /api/dashboard/fault-types?days=7 | 故障类型分布 |
| GET | /api/dashboard/recent-abnormal?limit=10 | 最近异常列表 |

### 结果接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/results | 全局巡检结果分页查询 |

支持筛选：`run_id`、`task_id`、`asset_id`、`check_type`、`status`、`start_date`、`end_date`。

### 报告接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/reports/generate | 生成 Excel 报告 |
| GET | /api/reports | 报告列表 |
| GET | /api/reports/{id}/download | 下载报告文件 |
| DELETE | /api/reports/{id} | 删除报告 |

## 3. 数据库变化

新增表：

**reports**

- id
- report_name
- report_type
- report_date
- run_id
- task_id
- file_name
- file_path
- file_size
- created_at

新增配置：

- `NETCHECK_REPORTS_DIR`
- 默认：`/app/reports`

新增依赖：

- `openpyxl==3.1.5`

## 4. 页面与交互

### 首页仪表盘

`index.html` 改造为真实看板：

- 资产总数、在线、离线、警告、未知。
- 任务总数、运行总数、今日巡检、今日异常、诊断总数。
- 资产状态分布图。
- 最近 7 天巡检/异常趋势图。
- 故障类型分布图。
- 最近异常列表。

### 巡检结果页

`results.html` 支持全局结果查询：

- 运行 ID。
- 任务 ID。
- 资产 ID。
- 检测类型。
- 结果状态。
- 开始日期。
- 结束日期。

仍兼容 `results.html?run_id=...`，并提供“查看本次诊断”入口。

### 报告管理页

新增 `reports.html`：

- 生成运行报告。
- 生成日报。
- 报告列表。
- 下载 Excel。
- 删除报告。

### 导航

顶部导航新增「报告管理」。

## 5. Excel 报告内容

Excel 报告包含：

- 巡检概况。
- 异常资产。
- 故障类型。
- 处理建议。

端到端验证中生成并下载文件：

```text
REPORT_ID=1
REPORT_FILE=run_3_20260711064533.xlsx
DOWNLOAD_SIZE=5717
```

## 6. 测试结果

### 自动化测试

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
26 passed in 81.35s
```

覆盖内容：

- 看板接口鉴权和数据聚合。
- 故障类型和最近异常统计。
- 全局巡检结果查询与筛选。
- 报告生成、列表、下载、删除。
- Excel 文件内容校验。
- 第 1-3 批既有功能不回退。

### 容器验证

已重建：

```powershell
docker compose up -d --build netcheck-backend netcheck-frontend
```

页面访问：

```text
index.html=200
results.html=200
reports.html=200
```

看板与结果接口：

```text
ASSET_TOTAL=12
TODAY_RUNS=3
DIAGNOSIS_TOTAL=2
FAULT_TYPES=2
RESULT_TOTAL=27
```

报告生成与下载：

```text
RUN_ID=3
REPORT_ID=1
REPORT_FILE=run_3_20260711064533.xlsx
DOWNLOADED=True
DOWNLOAD_SIZE=5717
```

## 7. MVP 功能清单

截至第 4 批，已完成最小可答辩 MVP：

- 登录鉴权。
- 资产台账管理。
- 手动巡检任务。
- Ping、端口、HTTP 检测。
- 巡检运行记录。
- 巡检结果留痕。
- 规则化故障诊断。
- 资产状态自动回写。
- 首页仪表盘。
- 全局巡检结果查询。
- Excel 报告生成、下载和删除。

## 8. 已知问题与边界

- 当前趋势图基于巡检结果聚合，不是资产状态历史快照。
- 当前报告模板为固定模板，不支持可视化自定义。
- PDF 报告不在本批范围。
- 告警确认、恢复、通知和阈值策略不在本批范围。
- 报告文件保存在 Docker volume 中，容器删除但 volume 保留时文件可持久化。

## 9. 下一批建议

下一阶段建议进入「告警与策略闭环」：

- 告警生成。
- 告警确认与恢复。
- 连续失败阈值。
- 告警级别和通知策略。
- 告警列表与详情页面。
