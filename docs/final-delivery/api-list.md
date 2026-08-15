# API 清单

> 统一响应包络：`{code, message, data}`
> 除登录和健康检查外，业务接口均需 `Authorization: Bearer {token}`。

## 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 后端健康检查 |
| GET | /api/health | 前端代理健康检查 |

## 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/auth/login | 登录并获取 token |
| POST | /api/auth/logout | 登出 |
| GET | /api/auth/me | 获取当前用户 |

## 资产管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/assets | 资产分页列表 |
| POST | /api/assets | 新增资产 |
| GET | /api/assets/{id} | 资产详情 |
| PUT | /api/assets/{id} | 更新资产 |
| DELETE | /api/assets/{id} | 删除资产 |
| GET | /api/assets/meta/types | 资产类型元数据 |

## 巡检任务与运行

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/tasks | 巡检任务列表 |
| POST | /api/tasks | 创建巡检任务 |
| GET | /api/tasks/{id} | 巡检任务详情 |
| PUT | /api/tasks/{id} | 更新巡检任务 |
| POST | /api/tasks/{id}/enable | 启用任务 |
| POST | /api/tasks/{id}/disable | 停用任务 |
| POST | /api/tasks/{id}/run | 手动执行任务 |
| GET | /api/tasks/{id}/runs | 查询任务运行记录 |
| GET | /api/tasks/runs/{run_id}/results | 查询某次运行结果 |

支持检测类型：

- `ping`
- `port`
- `http`
- `dns`

## 全局结果查询

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/results | 全局巡检结果分页查询 |

筛选条件：

- `run_id`
- `task_id`
- `asset_id`
- `check_type`
- `status`
- `start_date`
- `end_date`

## 故障诊断

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/diagnosis | 诊断记录分页列表 |
| GET | /api/diagnosis/{id} | 诊断详情 |
| GET | /api/diagnosis/runs/{run_id} | 查询某次运行诊断 |
| POST | /api/diagnosis/runs/{run_id}/generate | 重新生成某次运行诊断 |

## 仪表盘

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/dashboard/summary | 核心指标统计 |
| GET | /api/dashboard/asset-status | 资产状态分布 |
| GET | /api/dashboard/trend | 巡检和异常趋势 |
| GET | /api/dashboard/fault-types | 故障类型分布 |
| GET | /api/dashboard/recent-abnormal | 最近异常结果 |

## 报告管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/reports/generate | 生成 Excel 报告 |
| GET | /api/reports | 报告列表 |
| GET | /api/reports/{id}/download | 下载报告 |
| DELETE | /api/reports/{id} | 删除报告 |

报告类型：

- `run`：按运行 ID 生成。
- `daily`：按日期生成。

## 告警中心

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/alerts/summary | 告警统计 |
| GET | /api/alerts | 告警分页列表 |
| GET | /api/alerts/{id} | 告警详情 |
| POST | /api/alerts/{id}/confirm | 确认告警 |
| POST | /api/alerts/{id}/recover | 手动恢复告警 |
| POST | /api/alerts/evaluate/runs/{run_id} | 重新评估某次运行告警 |

## 告警策略

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/alert-policy | 获取默认告警策略 |
| PUT | /api/alert-policy | 更新默认告警策略 |

## 调度器

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/scheduler/status | 获取定时调度器状态 |

## 资产发现

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/discovery/scans | 创建并执行发现扫描 |
| GET | /api/discovery/scans | 查询扫描历史 |
| GET | /api/discovery/scans/{id}/results | 查询扫描结果 |
| POST | /api/discovery/results/{id}/import | 导入发现结果为资产 |

## 逻辑拓扑

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/topology | 获取逻辑拓扑节点和链路 |

## 网络设备（N1 采集 + N2 配置备份）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /api/devices | 设备分页列表 | 登录 |
| POST | /api/devices | 新增设备 | operator/admin |
| GET | /api/devices/{id} | 设备详情 | 登录 |
| PUT | /api/devices/{id} | 更新设备 | operator/admin |
| DELETE | /api/devices/{id} | 删除设备（级联清理采集指标与配置快照） | operator/admin |
| POST | /api/devices/credentials | 新建凭据（AES-256-GCM 加密存储） | admin |
| GET | /api/devices/credentials | 凭据列表（仅返回摘要，不含明文） | admin |
| DELETE | /api/devices/credentials/{id} | 删除凭据 | admin |
| POST | /api/devices/collect | 批量触发采集（SNMPv3 + SSH） | operator/admin |
| GET | /api/devices/{id}/snmp/interface | 接口指标（速率等） | 登录 |
| POST | /api/devices/{id}/configs/collect | 触发配置备份采集（同步） | operator/admin |
| GET | /api/devices/{id}/configs | 配置快照元数据列表（hash/时间/source/truncated/changed） | 登录 |
| GET | /api/devices/{id}/configs/latest | 最新配置脱敏全文 | operator/admin（viewer 403） |
| GET | /api/devices/{id}/configs/diff | 快照 diff（`from_snapshot_id`/`to_snapshot_id`/`context_lines` 可选；行数超 `config_diff_max_rows` 标记 `capped`；`from` 必须早于 `to`） | operator/admin（viewer 403） |

配置快照模型（`device_config_snapshots`）：
- `config_full_hash`：内容 SHA-256（truncated 时代表已读部分；唯一约束 `(device_id, config_full_hash)`）
- `config_text_redacted`：脱敏文本（密钥行/PEM 私钥块/crypto isakmp key/WireGuard）
- `truncated`：采集输出超限截断标记
- `changed`：与上一快照内容是否变化
- 每台设备保留最新 `NETCHECK_CONFIG_SNAPSHOT_RETENTION`（默认 20）份
