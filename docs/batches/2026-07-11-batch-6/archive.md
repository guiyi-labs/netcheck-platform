# 第 6 批完成归档：定时巡检、DNS 检测、资产发现与逻辑拓扑闭环

> 完成日期：2026-07-11
> 状态：已闭环，自动化与端到端验证通过

## 1. 功能说明

本批在第 1-5 批登录、资产、巡检、诊断、看板、报告和告警基础上，新增高分扩展能力：DNS 检测、定时巡检、轻量资产发现和逻辑拓扑展示。系统从手动巡检进一步扩展为具备自动调度、网络检测扩展、资产变化感知和拓扑可视化能力的平台。

完成能力：

- 巡检任务新增 DNS 检测类型。
- DNS 检测结果进入巡检结果、诊断、查询和报告链路。
- DNS 异常生成故障诊断。
- 巡检任务支持启用定时和设置执行间隔。
- 后端启动 APScheduler 并加载定时任务。
- 定时执行复用既有巡检、诊断、告警、资产状态回写流程。
- 新增调度器状态接口。
- 新增轻量资产发现。
- 支持授权 IP 列表或小 CIDR 扫描。
- 支持端口探测和发现结果导入资产。
- 新增逻辑拓扑接口和拓扑页面。
- 拓扑节点按资产状态区分颜色。

## 2. 接口清单

统一响应包络 `{code, message, data}`，业务接口均需 `Authorization: Bearer {token}`。

### 调度器

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/scheduler/status | 获取调度器运行状态和已注册任务 |

### 巡检任务增强

任务接口继续使用：

- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{id}`
- `PUT /api/tasks/{id}`
- `POST /api/tasks/{id}/run`

新增字段：

- `schedule_enabled`
- `schedule_interval_minutes`
- `next_run_at`
- `last_scheduled_run_at`

运行记录新增字段：

- `trigger_type`：`manual` 或 `scheduled`

检测类型新增：

- `dns`

### 资产发现

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/discovery/scans | 创建并执行发现扫描 |
| GET | /api/discovery/scans | 查询扫描历史 |
| GET | /api/discovery/scans/{id}/results | 查询扫描结果 |
| POST | /api/discovery/results/{id}/import | 导入发现结果为资产 |

### 逻辑拓扑

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/topology | 获取逻辑拓扑节点和链路 |

## 3. 数据库变化

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

## 4. 页面与交互

### 巡检任务页

`tasks.html` 增强：

- 检测类型新增 DNS。
- 新建/编辑任务支持启用定时巡检。
- 支持设置执行间隔分钟。
- 任务表格展示调度状态、间隔、下次执行时间、最近定时执行时间。

### 资产发现页

新增 `discovery.html`：

- 输入扫描范围。
- 选择扫描模式。
- 输入端口列表。
- 展示授权扫描提示。
- 查看扫描历史。
- 查看扫描结果。
- 导入发现结果为资产。

### 逻辑拓扑页

新增 `topology.html`：

- ECharts Graph 展示核心网络和资产节点。
- 节点颜色按资产状态区分。
- 支持刷新拓扑。
- 点击节点显示详情。
- ECharts 不可用时降级为文本列表。

### 导航

顶部导航新增：

- 资产发现。
- 逻辑拓扑。

## 5. 测试结果

### 自动化测试

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
37 passed in 230.70s
```

覆盖内容：

- DNS 检测类型创建和运行。
- DNS 结果和诊断规则。
- 定时字段保存。
- 调度器状态接口。
- 运行记录 `trigger_type`。
- 资产发现扫描。
- 非法 CIDR 和超量扫描限制。
- 发现结果导入资产。
- 拓扑接口鉴权、节点和状态。
- 第 1-5 批既有功能不回退。

### 容器验证

已重建：

```powershell
docker compose up -d --build netcheck-backend netcheck-frontend
```

页面访问：

```text
tasks.html=200
discovery.html=200
topology.html=200
```

### DNS 与定时验证

```text
TASK_ID=4
SCHEDULE_ENABLED=True
SCHEDULE_INTERVAL=60
RUN_ID=5
TRIGGER_TYPE=manual
RESULT=dns|success|demo-web-ok|DNS 解析到: 172.18.0.5
SCHEDULER_RUNNING=True
```

### 资产发现与拓扑验证

```text
SCAN_ID=1
SCAN_STATUS=completed
SCAN_TOTAL=1
DISCOVERED=1
RESULT_TOTAL=1
DISCOVERY=127.0.0.1|online|8000|exists=False
TOPOLOGY_NODES=13
TOPOLOGY_LINKS=12
```

## 6. 已知问题与边界

- 定时巡检使用单进程 APScheduler，不支持多实例分布式调度锁。
- 当前只支持分钟级间隔配置，不支持 Cron 表达式。
- 资产发现限定为授权小范围扫描，最多 256 个目标。
- 资产发现不做 Nmap、MAC、厂商、服务指纹识别。
- 拓扑为逻辑拓扑，不做 SNMP、LLDP、CDP 或 Traceroute 自动拓扑发现。
- DNS 检测使用系统 DNS，不做 DNSSEC 或多 DNS 服务器策略。

## 7. 项目闭环状态

截至第 6 批，系统已具备：

- 登录鉴权。
- 资产台账。
- 巡检任务。
- Ping、端口、HTTP、DNS 检测。
- 手动巡检和定时巡检。
- 巡检结果留痕。
- 规则化故障诊断。
- 资产状态回写。
- 仪表盘。
- 全局结果查询。
- Excel 报告。
- 告警生成、确认、恢复和策略配置。
- 轻量资产发现。
- 逻辑拓扑展示。

## 8. 后续建议

第 7 批建议进入测试、部署与论文材料整理：

- 全链路回归测试。
- Docker 部署说明完善。
- 论文截图和演示流程整理。
- 数据库表结构说明。
- API 清单整理。
- 测试用例与测试报告归档。
- 项目答辩演示脚本。
