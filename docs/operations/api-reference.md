# API 参考

> 全部端点、鉴权规则、统一包络与示例。运行时自动文档：`http://localhost:8000/docs`（Swagger）。

## 1. 通用约定

### 统一响应包络

```json
{ "code": 0, "message": "ok", "data": { ... } }
```

- `code == 0` 表示成功；非 0 时 `message` 给原因，HTTP 状态码同步体现（401/403/404 等）。
- 分页列表统一：`data = { "total", "page", "page_size", "items": [... ] }`。

### 鉴权

- 全部 `/api/*` 业务端点（除 `login`、`/health`、`/metrics`）需要请求头：
  ```
  Authorization: Bearer <token>
  ```
- token 来源：`POST /api/auth/login` 返回 `data.token`；默认有效期 24h。
- 角色：admin（全部）、operator（写操作）、viewer（只读，写操作 403）。
- WebSocket：`/ws/runs?token=<token>`。

## 2. 认证 `/api/auth`

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | /api/auth/login | 登录，返回 token + 用户信息 | 无 |
| POST | /api/auth/logout | 登出（使 token 失效） | 登录 |
| POST | /api/auth/change-password | 修改密码 | 登录 |
| GET | /api/auth/me | 当前用户信息 | 登录 |

登录示例：

```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}'
```

## 3. 资产 `/api/assets`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/assets | 资产分页列表（支持 status/type/搜索/分页） |
| POST | /api/assets | 新建资产（201） |
| GET | /api/assets/{asset_id} | 资产详情 |
| PUT | /api/assets/{asset_id} | 更新资产（记录变更日志，字段级 diff） |
| DELETE | /api/assets/{asset_id} | 删除资产（记录变更日志） |
| GET | /api/assets/{asset_id}/changes | 该资产的变更历史 |
| GET | /api/assets/export | 导出 CSV（带 BOM） |
| POST | /api/assets/import | 批量导入 CSV（`multipart/form-data`，跳过重复 IP） |
| GET | /api/assets/meta/types | 资产类型元数据 |

导入示例：

```bash
curl -s -X POST http://localhost:8000/api/assets/import \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@assets.csv"
# 返回 {"imported": 3, "skipped": 1, "errors": []}
```

## 4. 巡检任务 `/api/tasks`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/tasks | 任务分页列表 |
| POST | /api/tasks | 新建任务（201；含 check_types、asset_ids、schedule_cron） |
| GET | /api/tasks/{task_id} | 任务详情 |
| PUT | /api/tasks/{task_id} | 更新任务 |
| POST | /api/tasks/{task_id}/enable | 启用 |
| POST | /api/tasks/{task_id}/disable | 停用 |
| GET | /api/tasks/{task_id}/runs | 任务运行记录分页 |
| POST | /api/tasks/{task_id}/run | 手动触发运行 |

## 5. 运行与结果 `/api/tasks/runs` · `/api/results`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/tasks/runs/{run_id} | 运行详情（前端轮询/落库） |
| POST | /api/tasks/runs/{run_id}/cancel | 取消进行中的运行 |
| POST | /api/tasks/runs/{run_id}/retry | 失败/取消后重试 |
| GET | /api/results | 全局检测结果分页 |
| GET | /api/results/runs/{run_id}/results | 某运行的检测结果 |
| POST | /api/results/{result_id}/import | 将发现结果转资产 |

## 6. 诊断 `/api/diagnosis` · `/api/diagnostics`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/diagnosis | 诊断记录分页（run_id/asset_id/severity 筛选） |
| GET | /api/diagnosis/runs/{run_id} | 某运行的所有诊断 |
| POST | /api/diagnosis/runs/{run_id}/generate | 重新生成诊断 |
| GET | /api/diagnosis/{diagnosis_id} | 诊断详情 |
| POST | /api/diagnosis/{diagnosis_id}/ai-suggestion | AI 增强建议（需配置） |
| POST | /api/diagnostics/traceroute | Traceroute 诊断（body: target, max_hops?, wait?） |

Traceroute 示例：

```bash
curl -s -X POST "http://localhost:8000/api/diagnostics/traceroute?target=8.8.8.8&max_hops=10" \
  -H "Authorization: Bearer $TOKEN"
```

## 7. 设备采集（N1）`/api/devices`

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | /api/devices/credentials | 创建设备凭据（SNMPv3/SSH，AES-256-GCM 加密存储） | admin |
| GET | /api/devices/credentials | 凭据列表（只返回状态与算法，不返回密钥） | 登录 |
| DELETE | /api/devices/credentials/{id} | 删除凭据 | admin |
| POST | /api/devices | 新增设备（管理 IP、厂商平台、凭据引用） | 写 |
| GET | /api/devices | 设备分页（vendor 筛选） | 登录 |
| GET | /api/devices/{id} | 设备详情（含采集状态、设备事实） | 登录 |
| PUT | /api/devices/{id} | 更新设备 | 写 |
| DELETE | /api/devices/{id} | 删除设备（连带接口指标） | 写 |
| GET | /api/devices/{id}/interfaces | 接口指标（速率、计数器、状态） | 登录 |
| POST | /api/devices/collect | 批量触发采集（≤ 8 台，同步） | 写 |
| POST | /api/devices/{id}/collect | 触发单台采集 | 写 |

采集示例（登录后）:

```bash
# 1) 创建凭据（响应不回显密钥）
curl -s -X POST http://localhost:8000/api/devices/credentials \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"core-snmp","protocol":"snmp_v3","username":"monitor",
       "auth_key":"...","priv_key":"...","auth_algorithm":"SHA-256","priv_algorithm":"AES-128"}'

# 2) 新增设备并绑定凭据
curl -s -X POST http://localhost:8000/api/devices \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"core-router-01","management_ip":"10.0.0.1","vendor_platform":"linux","snmp_config_id":1}'

# 3) 触发采集
curl -s -X POST http://localhost:8000/api/devices/1/collect \
  -H "Authorization: Bearer $TOKEN"

# 4) 查看接口指标
curl -s http://localhost:8000/api/devices/1/interfaces \
  -H "Authorization: Bearer $TOKEN"
```

> 采集状态：`idle/collecting/success/failed` + 失败分类 `auth_failed/priv_failed/timeout/host_key_unknown/host_key_mismatch/conn_refused`。
> 空样本显示 `unknown`，不显示 0 或健康。

## 8. 告警 `/api/alerts` · `/api/alert-policy`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/alerts | 告警分页（level/status 筛选） |
| GET/POST | /api/alert-policy/status | 策略与启停（以 OpenAPI 为准） |

## 9. 报告 `/api/reports`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/reports | 报告分页 |
| POST | /api/reports/generate | 生成报告（201） |
| GET | /api/reports/{report_id} | 报告详情 |
| GET | /api/reports/{report_id}/download | 下载报告文件 |
| DELETE | /api/reports/{report_id} | 删除报告 |

## 10. 发现与拓扑 `/api/discovery` · `/api/topology`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/discovery/scans | 扫描记录 |
| POST | /api/discovery/scans | 发起扫描（201；target_range、scan_mode=ping/port/ping_port） |
| GET | /api/discovery/scans/{scan_id}/results | 扫描结果 |
| GET | /api/topology | 连通拓扑（资产 IP 间关系） |

## 11. 统计与仪表盘

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/dashboard/summary | 仪表盘统计卡片 |
| GET | /api/dashboard/asset-status | 资产状态分布 |
| GET | /api/dashboard/trend | 近 N 天运行/异常趋势 |
| GET | /api/dashboard/fault-types | 故障类型分布 |
| GET | /api/dashboard/recent-abnormal | 最近异常列表 |
| GET | /api/stats/assets | 趋势页资产下拉 |
| GET | /api/stats/rtt-trend?asset_id&days | 每日 RTT 平均/最大 |
| GET | /api/stats/availability?asset_id&days | 每日可用率 % |
| GET | /api/stats/run-durations?days&limit | 最近运行耗时 |

## 12. 系统与可观测

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 健康检查（无鉴权） |
| GET | /metrics | Prometheus 指标（无鉴权，text format v0.0.4） |
| GET | /api/scheduler/status | 调度器状态 |
| GET | /api/audit-logs | 审计日志分页 |
| GET | /api/users | 用户管理（admin）——list/create/update/delete |
| WS | /ws/runs?token= | 运行状态实时推送 |

## 13. 数据模型要点

- 资产 `Asset`：name/ip/hostname/ports/check_types/status（online/offline/warning/unknown）
- 任务 `InspectionTask`：check_types + assets(m2m) + schedule_cron + enabled
- 运行 `InspectionRun`：status（pending/running/completed/failed/cancelled）+ trigger_type
- 结果 `InspectionResult`：asset_id + check_type + status（success/warning/failed）+ response_time
- 告警 `Alert`：level（minor/warning/major/critical）+ status（active/recovered）
- 诊断 `DiagnosisRecord`：fault_type + severity + suggestion + evidence
- **设备 `Device`**（N1）：management_ip + vendor_platform + snmp_config_id/ssh_config_id + collect_status + sys_name/sys_uptime/os_version
- **凭据 `DeviceCredential`**（N1）：protocol（snmp_v3/ssh）+ username + 加密字段 + auth/priv 算法
- **接口指标 `SnmpInterfaceMetric`**（N1）：interface_index/name + admin/oper_status + if_in/out_octets（64 位）+ in/out_rate_bps + status
- 完整建表脚本见 `docs/final-delivery/database-schema.md`（历史快照，字段以实际 ORM 为准）