# 部署手册

> 覆盖：环境要求、Docker 一键部署、本地开发部署、MySQL 切换、配置项说明、备份与恢复。

## 1. 环境要求

- Docker Desktop / Docker Engine（推荐）
- Windows 10/11、macOS 或 Linux
- Python 3.11+（本地开发模式）
- 端口占用：8000（后端）、8080（前端）、3000（Grafana）、9090（Prometheus）、18080-18082（demo 服务）

## 2. Docker 部署（Compose）

```bash
# 全量启停
./scripts/demo-stack.sh up      # 构建 + 启动 + 健康自检
./scripts/demo-stack.sh status  # 查看容器与健康
./scripts/demo-stack.sh verify  # 验证 Prometheus 抓取 / Grafana 访问
./scripts/demo-stack.sh down    # 停止并移除容器（数据卷保留）

# 或直接使用 compose
docker compose up -d --build
docker compose down
```

### 服务清单（docker-compose.yml）

| 服务 | 职责 | 端口 |
|---|---|---|
| netcheck-backend | FastAPI + 巡检执行 + 调度 | 8000 |
| netcheck-frontend | Nginx 托管前端静态页 | 8080 |
| prometheus | 抓取 /metrics | 9090 |
| grafana | 仪表盘大屏（自动供给数据源+面板） | 3000 |
| demo-web-ok | 正常演示站点 | 18080 |
| demo-web-error | HTTP 500 演示站点 | 18081 |
| demo-web-slow | 慢响应演示站点 | 18082 |
| netcheck-mysql（注释）| 可选 MySQL，启用见 §5 | — |

## 3. 本地开发部署

```bash
# 后端
cd backend
python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
cd ..
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 前端（另一终端）
cd frontend
python3 -m http.server 8080
```

> 前端通过 `js/api.js` 请求 `http://localhost:8000` 端口，与 Nginx 反向代理同理。

## 4. 运行测试

```bash
# 必须从项目根目录执行
.venv/bin/python -m pytest -q
# 预期: 110 passed
```

> ⚠️ 不要同时打开两个 pytest 进程——测试共享同一个临时 SQLite 文件，会互相踩踏产生大量 error。

## 5. 切换 MySQL

1. 取消 `docker-compose.yml` 中 `netcheck-mysql` 的注释。
2. 修改 backend 环境变量：

```env
NETCHECK_DATABASE_URL=mysql+pymysql://netcheck:netcheck@netcheck-mysql:3306/netcheck?charset=utf8mb4
```

3. 本地开发时对应修改 `.env` 中的 `NETCHECK_DATABASE_URL`。
4. 重新 `docker compose up -d --build netcheck-backend`。

> SQLite 迁移逻辑（`_ensure_sqlite_columns/_ensure_sqlite_indexes`）仅面向 SQLite；
> MySQL 用原生 DDL 建表（`init_db` 含 `create_all`）。

## 6. 环境变量

所有变量以 `NETCHECK_` 为前缀，可放 `.env` 或系统环境变量。完整清单见 `.env.example`。

### 核心

| 变量 | 默认 | 说明 |
|---|---|---|
| NETCHECK_DATABASE_URL | sqlite:///./data/netcheck.db | 数据库连接串 |
| NETCHECK_REPORTS_DIR | /app/reports | 报告文件目录 |
| NETCHECK_BACKUP_DIR | /app/backups | 备份目录 |
| NETCHECK_LOG_LEVEL | INFO | 日志级别 |

### 检测与执行

| 变量 | 默认 | 说明 |
|---|---|---|
| NETCHECK_PING_TIMEOUT | 3.0 | ping 超时（秒） |
| NETCHECK_TCP_TIMEOUT | 3.0 | TCP 端口超时 |
| NETCHECK_HTTP_TIMEOUT | 5.0 | HTTP 检测超时 |
| NETCHECK_SLOW_RESPONSE_THRESHOLD | 2000.0 | 慢响应判定阈值（ms） |
| NETCHECK_CHECK_CONCURRENCY | 8 | 同一运行内并行检测资产数 |
| NETCHECK_RUN_QUEUE_MAXSIZE | 1000 | 执行队列上限，满则运行标记 failed |
| NETCHECK_TLS_EXPIRY_WARNING_DAYS | 30 | TLS 证书到期预警天数 |

### 安全

| 变量 | 默认 | 说明 |
|---|---|---|
| NETCHECK_TOKEN_TTL_HOURS | 24.0 | 登录 token 有效期（小时） |
| NETCHECK_LOGIN_MAX_ATTEMPTS | 5 | 登录失败锁定阈值 |
| NETCHECK_LOGIN_LOCK_MINUTES | 15.0 | 锁定时长（分钟） |
| NETCHECK_PASSWORD_MIN_LENGTH | 8 | 密码最短长度 |

### 通知

| 变量 | 默认 | 说明 |
|---|---|---|
| NETCHECK_NOTIFICATION_ENABLED | false | 总开关 |
| NETCHECK_NOTIFICATION_MIN_LEVEL | warning | 最低告警等级（minor/warning/major/critical） |
| NETCHECK_SMTP_HOST/PORT/USER/... | — | SMTP 配置 |
| NETCHECK_WEBHOOK_URL | "" | Webhook 地址 |
| NETCHECK_WEBHOOK_SCHEME | generic | 平台适配：generic/dingtalk/wecom/feishu |
| NETCHECK_WEBHOOK_HEADERS | "" | 额外请求头（JSON 或 `k:v` 多行） |

### AI 诊断（可选）

| 变量 | 默认 | 说明 |
|---|---|---|
| NETCHECK_AI_DIAGNOSIS_ENABLED | false | 开关 |
| NETCHECK_AI_BASE_URL | "" | OpenAI 兼容 base URL（本地 Ollama 也可） |
| NETCHECK_AI_API_KEY | "" | API Key |
| NETCHECK_AI_MODEL | "" | 模型名 |
| NETCHECK_AI_TIMEOUT | 30.0 | 请求超时 |

### 设备采集（N1：SNMPv3 / SSH 只读）

| 变量 | 默认 | 说明 |
|---|---|---|
| NETCHECK_SECRET_KEY | "" | 凭据加密密钥（AES-256-GCM），生产用随机 32+ 字符 |
| NETCHECK_SNMP_TIMEOUT | 5.0 | SNMP 请求超时（秒） |
| NETCHECK_SNMP_RETRIES | 1 | SNMP 重试次数 |
| NETCHECK_SNMP_MAX_INTERFACES | 64 | 单设备最大采集接口数 |
| NETCHECK_SNMP_MAX_REQUESTS | 30 | 单设备最大 SNMP 请求次数 |
| NETCHECK_SSH_TIMEOUT | 10.0 | SSH 连接超时（秒） |
| NETCHECK_SSH_MAX_OUTPUT_BYTES | 524288 | SSH 命令输出最大字节数（512KB） |
| NETCHECK_DEVICE_COLLECT_MAX_BATCH | 8 | 单次批量采集最多设备数 |

> 依赖新增：`pysnmp==7.1.28`、`paramiko==5.0.0`、`cryptography==50.0.0`。

## 7. 备份与恢复

```bash
# Linux/macOS
./scripts/backup.sh          # 按时间戳备份 DB + reports + 配置，自动清理过期
# Windows PowerShell
./scripts/backup.ps1
```

## 8. 容器网络注意

- backend 容器需 `cap_add: NET_RAW` 才能在容器内发起 ICMP（ping）。
- 若容器内 ping 失败，请运行 `./scripts/verify-container-network.sh` 五步自检。
- 详细说明见 `docs/phase-c/container-network.md`。