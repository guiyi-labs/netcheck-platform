# 面向中小型网络的自动化巡检与故障诊断平台

第 0 批目标是搭建 Docker 优先的基础环境，提供后端健康检查、前端入口页、Compose 演示网络和可复现的巡检目标服务。

后端和 Python 演示服务使用 `mcr.microsoft.com/devcontainers/python:3.11-bookworm` 作为基础镜像。这样可以避开部分网络环境下 Docker Hub 拉取 `python:3.11-slim` 不稳定的问题。

## 服务组成

| 服务 | 说明 | 访问地址 |
|---|---|---|
| `netcheck-backend` | FastAPI 后端 API | `http://localhost:8000` |
| `netcheck-frontend` | Nginx 前端入口 | `http://localhost:8080` |
| `demo-web-ok` | 正常 HTTP 演示服务 | `http://localhost:18080` |
| `demo-web-error` | HTTP 500 异常演示服务 | `http://localhost:18081` |
| `demo-web-slow` | 慢响应演示服务 | `http://localhost:18082` |

Compose 内部网络名为 `netcheck-lab`。后续巡检任务可以优先使用以下容器服务名作为演示资产：

- `demo-web-ok:80`
- `demo-web-error:80`
- `demo-web-slow:80`

## Docker 启动

安装 Docker Desktop 或 Docker Engine 后，在项目根目录执行：

```powershell
docker compose up -d --build
```

查看服务状态：

```powershell
docker compose ps
```

验证接口：

```powershell
curl http://localhost:8000/health
curl http://localhost:8080/api/health
curl http://localhost:18080
curl http://localhost:18081
curl http://localhost:18082
```

## 默认账号、资产管理、巡检、诊断、报告、告警与扩展能力

第 1 批起新增登录鉴权与资产台账，第 2 批新增巡检任务、手动执行和结果查看，第 3 批新增故障诊断与资产状态自动回写，第 4 批新增仪表盘、全局结果查询和 Excel 报告导出，第 5 批新增告警生成、确认、恢复和策略配置，第 6 批新增 DNS 检测、定时巡检、资产发现和逻辑拓扑。默认账号（见 `backend/app/seed.py`，首次启动自动写入）：

- 用户名 `admin`，密码 `admin123`

浏览器访问 `http://localhost:8080/login.html` 登录后进入后台：

- 「仪表盘」：查看资产状态、巡检趋势、故障类型分布、告警统计和最近异常。
- 「资产管理」：维护资产台账，可进行资产增删改查。
- 「巡检任务」：创建任务，选择资产与 Ping/端口/HTTP/DNS 检测类型，配置手动或定时执行。
- 「巡检结果」：全局查询巡检结果，也可从任务运行详情进入查看某次运行结果。
- 「故障诊断」：查看自动生成的故障类型、等级、诊断依据和处理建议。
- 「告警中心」：查看告警列表，配置策略，确认和恢复告警。
- 「资产发现」：在授权小范围内扫描主机和端口，并将发现结果导入资产台账。
- 「逻辑拓扑」：按资产状态和类型展示网络逻辑拓扑。
- 「报告管理」：生成、下载和删除 Excel 巡检报告。
- 「审计日志」：查看登录、资产、任务、告警、报告等关键操作记录（阶段 A 新增）。
- 「用户管理」：管理员创建账号，分配 admin/operator/viewer 角色（阶段 B 新增）。
- 「资产变更历史」：资产新增/更新（字段级 diff）/删除全程可追溯（阶段 B 新增）。

阶段 A（工程加固）新增能力：token 过期与登录失败限流、修改密码、巡检异步执行（后台队列 +
前端轮询）、关键表组合索引、MySQL 可选部署、`.env.example` 配置外置、审计日志、备份脚本
（`scripts/backup.sh` / `scripts/backup.ps1`）。

阶段 B（业务补强）新增能力：邮件 SMTP / Webhook 告警通知（含等级阈值）、资产 CSV 批量导入导出、
任务取消 / 失败重试 / Cron 调度、多用户与角色权限（admin/operator/viewer）、TLS 证书检测器
（有效期预警）、资产变更日志与历史查询。

阶段 C（真实网络能力）新增能力：容器网络适配验证（frontend Dockerfile 补齐页面 +
`scripts/verify-container-network.sh`）、Traceroute 网络诊断（`diag.html` / `POST /api/diagnostics/traceroute`）、
Nmap 增强发现与 SNMP 基础采集（可选依赖，自动回落）、局域网验证脚本 `scripts/verify-lan.sh`。

阶段 D（进阶扩展）新增能力：AI 辅助诊断（OpenAI 兼容接口，`POST /api/diagnosis/{id}/ai-suggestion`）、
Prometheus 指标导出（`GET /metrics`，零依赖 text format）、K8s 巡检脚本 `scripts/k8s-inspect.sh`、
分布式执行锁（多实例防重复）、有界执行队列（`run_queue_maxsize` 防堆积）。

演示出彩增强（docs/demo-improvements/archive.md）：WebSocket 实时推送（`/ws/runs`，运行状态
秒级刷新，`js/ws.js` 自动重连）、ECharts 趋势页（`trends.html`：RTT 曲线 / 可用率 SLA / 运行耗时，
后端 `GET /api/stats/*`）、Prometheus + Grafana 一键大屏（`scripts/demo-stack.sh up`，仪表盘自动
供给）、告警渠道适配器（钉钉 / 企微 / 飞书，`NETCHECK_WEBHOOK_SCHEME`）。

接口示例：

```powershell
# 登录取 token
$login = curl.exe -s -X POST http://localhost:8000/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"admin\",\"password\":\"admin123\"}'
$token = ($login | ConvertFrom-Json).data.token

# 列出资产
curl.exe -s http://localhost:8000/api/assets -H "Authorization: Bearer $token"
```

当前业务接口统一响应包络 `{code, message, data}`，需 `Authorization: Bearer {token}`：

- `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`
- `POST /api/auth/change-password`（验证原密码、强制密码长度、改密后旧 token 失效）
- `GET/POST /api/users`、`PUT/DELETE /api/users/{id}`（用户管理，仅 admin）
- `GET/POST /api/assets`、`GET/PUT/DELETE /api/assets/{id}`、`GET /api/assets/meta/types`
- `GET /api/assets/{id}/changes`（资产字段级变更历史）
- `POST /api/assets/import`（CSV 批量导入）、`GET /api/assets/export`（CSV 导出）
- `GET/POST /api/tasks`、`GET/PUT /api/tasks/{id}`
- `POST /api/tasks/{id}/enable`、`POST /api/tasks/{id}/disable`、`POST /api/tasks/{id}/run`（异步提交）
- `GET /api/tasks/{id}/runs`、`GET /api/tasks/runs/{run_id}`（轮询状态）、`GET /api/tasks/runs/{run_id}/results`
- `POST /api/tasks/runs/{run_id}/cancel`（取消执行）、`POST /api/tasks/runs/{run_id}/retry`（失败重试）
- `GET /api/diagnosis`、`GET /api/diagnosis/{id}`、`GET /api/diagnosis/runs/{run_id}`
- `POST /api/diagnosis/runs/{run_id}/generate`
- `POST /api/diagnosis/{id}/ai-suggestion`（AI 辅助诊断建议，可选）
- `GET /api/dashboard/summary`、`GET /api/dashboard/asset-status`
- `GET /api/dashboard/trend`、`GET /api/dashboard/fault-types`、`GET /api/dashboard/recent-abnormal`
- `GET /api/results`
- `POST /api/reports/generate`、`GET /api/reports`、`GET /api/reports/{id}/download`、`DELETE /api/reports/{id}`
- `GET /api/alerts/summary`、`GET /api/alerts`、`GET /api/alerts/{id}`
- `POST /api/alerts/{id}/confirm`、`POST /api/alerts/{id}/recover`、`POST /api/alerts/evaluate/runs/{run_id}`
- `GET /api/alert-policy`、`PUT /api/alert-policy`
- `GET /api/scheduler/status`
- `POST /api/discovery/scans`、`GET /api/discovery/scans`、`GET /api/discovery/scans/{id}/results`
- `POST /api/discovery/results/{id}/import`
- `GET /api/topology`
- `GET /api/audit-logs`（审计日志查询，支持用户/动作/对象/日期筛选）
- `POST /api/diagnostics/traceroute`（Traceroute 网络诊断）
- `GET /metrics`（Prometheus 指标导出，无鉴权）

巡检演示建议选择资产 `demo-web-ok`、`demo-web-error`、`demo-web-slow`，检测类型选择 Ping、端口、HTTP、DNS，可复现 HTTP 200、HTTP 500、慢响应警告和 Docker 服务名 DNS 解析，并自动生成故障诊断、告警与资产状态回写结果。随后可在「仪表盘」查看统计图表，在「资产发现」扫描授权地址，在「逻辑拓扑」查看资产拓扑，在「报告管理」按运行 ID 生成并下载 Excel 报告。

停止环境：

```powershell
docker compose down
```

## 设备采集（N1：SNMPv3 与 SSH 只读）+ 配置备份（N2）

N1 新增网络设备只读采集链路（`frontend/devices.html` → `/api/devices/*`）：

- **设备资产模型**：管理地址、厂商平台（linux / cisco_ios / generic）、SNMP/SSH 能力与采集状态；
- **SNMPv3 authPriv**：显式算法 allowlist（SHA-256/SHA + AES-128/AES-256），OID 固定 allowlist，带 sysName/sysDescr/sysUpTime、接口名称/状态/64 位计数器，速率基于相邻样本与真实时间间隔计算（处理计数器回绕、重启、缺样本）；
- **SSH 只读**：固定厂商适配器 + 只读命令 allowlist，host key 校验（首次未知/不匹配显式报错），原始输出长度上限 + 脱敏，不做配置下发；
- **凭据安全**：AES-256-GCM 加密存储（`NETCHECK_SECRET_KEY`），API/日志/前端只返回 `configured`/`has_secret`/算法摘要；空样本显示 `unknown`，不显示为 0 或健康。

N2 新增只读配置备份与差异（`/api/devices/{id}/configs/*`）：

- **配置采集**：复用 SSH 只读通道，从 `CONFIG_READ_COMMANDS` allowlist 读取配置；**SSH 密码已解密后实时传入采集器**（auth_key_encrypted → password）；
- **流式有界读取**：stdout/stderr 读取阶段按 `ssh_max_output_bytes` 字节上限截断（禁止先读全量再截断），截断按字节计数并保持 UTF-8 完整字符边界；截断后响应显式标记 `truncated: true`，哈希为已读部分内容哈希（非完整配置哈希）；
- **脱敏存储**：密钥行值替换为 `********`；**PEM 私钥块**（RSA/EC/OPENSSH，含 BEGIN/END 头尾）多行状态机遮蔽；`crypto isakmp key`、WireGuard `PrivateKey`/`PresharedKey` 覆盖；缩进行正确处理；非密钥行（接口名、描述、路由、BGP）不误伤；仅存内容 SHA-256 哈希（去重/变更检测），不保存明文密钥；
- **DB 去重**：`(device_id, config_full_hash)` 唯一约束；并发写冲突快速失败回退为 unchanged；
- **保留上限**：每台设备最多保留 `config_snapshot_retention`（默认 20）份快照，超出自动清理最旧；
- **设备删除级联**：删除设备时级联清理 `device_config_snapshots` 关联快照；
- **权限控制**：配置全文（latest）与 diff 要求 operator/admin（viewer 403）；快照元数据列表（hash/时间）要求登录；
- **差异对比**：相邻快照行级 unified diff，支持 `context_lines`（每侧保留上下文行数）；diff 结果有 `config_diff_max_rows`（默认 2000）行上限，超出标记 `capped: true`；`from` 必须早于 `to`（按时间+ID 排序）；
- **变更审计**：配置变化自动标记并写入 `OperationLog`（action = `device_config_backup`，含 truncated 标记）；审计日志与快照写入为独立事务（审计失败不影响快照）。

实验入口：`./scripts/n1-lab.sh mock`（确定性 mock 演示）｜ `lab-up`（containerlab/FRRouting 实验）。
凭据/采集配置：`.env.example` 中 `NETCHECK_*` N1 段。

## 本地后端测试

如果当前机器还没有 Docker，可以先验证后端基础代码：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

当前健康检查接口：

- `GET /health`
- `GET /api/health`

## 数据与日志

Docker Compose 使用命名 volume 保存运行数据：

- `db_data`：SQLite 数据库。
- `report_data`：巡检报告文件。
- `backend_logs`：后端日志。

本地 `volumes/` 目录用于后续需要直接挂载文件时使用，默认被 `.gitignore` 和 `.dockerignore` 排除。

## 📚 文档导航

完整操作与说明文档见 [`docs/operations/`](docs/operations/README.md)：

- [快速开始](docs/operations/quickstart.md) · [部署手册](docs/operations/deployment.md) · [用户操作手册](docs/operations/user-guide.md)
- [答辩演示指南](docs/operations/demo-guide.md) · [排障 FAQ](docs/operations/troubleshooting.md)
- [API 参考](docs/operations/api-reference.md) · [开发指南](docs/operations/development.md)

## 最终交付材料

最终阶段已整理以下交付文档：

- [部署说明](docs/final-delivery/deployment-guide.md)
- [测试报告](docs/final-delivery/test-report.md)
- [答辩演示脚本](docs/final-delivery/demo-script.md)
- [API 清单](docs/final-delivery/api-list.md)
- [数据库表结构说明](docs/final-delivery/database-schema.md)
- [论文截图清单](docs/final-delivery/screenshot-checklist.md)
- [最终交付清单](docs/final-delivery/delivery-checklist.md)
- [本地备份与 GitHub 推送说明](docs/final-delivery/github-backup-push-note.md)
- [GitHub 成功推送操作留存文档](docs/final-delivery/github-success-push-guide.md)
- [第 7 批计划](docs/batches/2026-07-11-batch-7/plan.md)
- [第 7 批归档](docs/batches/2026-07-11-batch-7/archive.md)

最终验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
docker compose up -d --build
docker compose ps
```

## Windows Docker 网络说明

Docker Desktop 在 Windows 上运行于虚拟化网络中，容器访问真实局域网时可能与宿主机行为不同。答辩演示优先使用 Compose 内部演示网络，保证正常、异常、慢响应、DNS 解析、资产发现和拓扑展示场景稳定可复现。

真实局域网扫描建议在后续扩展阶段使用 Linux 虚拟机或宿主机网络单独验证，并在论文中说明 Docker 演示网络与真实网络验证的边界。资产发现只应扫描授权范围，系统默认限制最多 256 个目标。
