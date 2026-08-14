# 排障 FAQ

> 按「现象 → 原因 → 解决」组织。检查顺序从上到下。

## 1. 部署与启动

### 1.1 容器启动后马上退出（Exited 137）

- **原因**：通常是被 OOM 杀掉（Docker 内存不足），尤其是镜像 build 阶段 + 其他项目容器共存时。
- **解决**：
  ```bash
  docker stats                    # 确认内存
  docker compose up -d netcheck-backend netcheck-grafana   # 不带 --build，避免构建峰值
  ```
  若仍不稳定：先 `docker compose down` 停止 Grafana/Prometheus，跑核心链路（后端+前端）演示。

### 1.2 前端访问 404 / 页面缺失

- **原因**：镜像构建早于新增页面（audit/users/asset-changes/trends/diag）。
- **解决**：重新构建 `docker compose build netcheck-frontend && docker compose up -d netcheck-frontend`。
  （当前 Dockerfile 已改为 `COPY *.html`，后续新增页面无需改 Dockerfile。）

### 1.3 前端登录后接口 401 / 一直跳登录

- **原因**：token 过期（默认 24h）或后端时间异常。
- **解决**：重新登录；检查 `NETCHECK_TOKEN_TTL_HOURS`。
- 前端 `api.js` 在 401 时会自动清理本地 token 跳转登录页。

### 1.4 端口占用

- **原因**：8000/8080 与其他服务冲突。
- **解决**：
  ```bash
  lsof -i :8000
  docker compose stop netcheck-backend
  ```
  或改 compose 的 `ports` 映射。

## 2. 巡检执行

### 2.1 任务运行一直 pending，不变成 running/completed

排查顺序：
1. 执行队列是否满？`NETCHECK_RUN_QUEUE_MAXSIZE`（默认 1000），满则运行直接 failed。
2. 运行被标记 failed 且错误消息含「分布式锁」：说明另一实例持有该任务锁。
   - 锁 TTL 10 分钟，或手动清表：`DELETE FROM task_locks WHERE task_id = <id>;`
3. 守护线程是否活着？后端日志里应有巡检运行记录。

### 2.2 容器内 ping 全部失败（timeout）

- **原因**：容器缺少 `NET_RAW` 权限，或未安装 `iputils-ping`。
- **解决**：确认 compose 中 backend `cap_add: [NET_RAW]`；运行五步自检：
  ```bash
  ./scripts/verify-container-network.sh
  ```

### 2.3 容器内能 ping 通 IP 但 DNS 解析不了 demo-web-ok

- **原因**：未挂到 `netcheck-lab` 网络，或 demo 服务没起来。
- **解决**：
  ```bash
  docker compose up -d demo-web-ok
  docker exec netcheck-backend getent hosts demo-web-ok   # 应解析出容器 IP
  ```

### 2.4 结果全部 failed（所有检查失败）

- **原因**：目标不可达、误配 IP、或检测端口不对（如 TLS 检测默认只扫 443/8443/9443）。
- **解决**：趋势页 RTT 曲线先确认资产可达；用「网络诊断」跑 traceroute 定位中断点；
  资产编辑页核对检测类型与端口。

## 3. 指标与 Grafana

### 3.1 Prometheus target 显示 down

- **原因**：最常见是 `/metrics` 输出格式非法——`# TYPE`/`# HELP` 行必须用**裸指标名**（不能带 `{label=...}`）。
- **解决**：
  ```bash
  curl -s http://localhost:8000/metrics | head -30   # 检查语法
  ./scripts/demo-stack.sh verify
  ```
  当前 `metrics.py` 已用 `_family()` 保证格式正确。

### 3.2 Grafana 面板导入失败或无数据

- **原因**：数据源供给未生效或面板路径不对。
- **解决**：
  - 确认 `observability/grafana/provisioning/datasources/prometheus.yml` 中 `uid: prometheus` 与面板引用一致。
  - `docker compose restart grafana`（供给每 30s 自动刷新，重启兜底）。
  - Grafana → Connections → Data sources → 点 Prometheus → Save & test，应连上 `http://prometheus:9090`。

## 4. 告警与通知

### 4.1 告警不推送

排查顺序：
1. `NETCHECK_NOTIFICATION_ENABLED=true`？
2. 告警等级是否达到 `NETCHECK_NOTIFICATION_MIN_LEVEL`（默认 warning，minor 不推）。
3. Webhook：`NETCHECK_WEBHOOK_URL` 是否可公网/内网访问？钉钉/企微/飞书机器人安全设置要允许。
4. 后端日志搜 `告警通知投递` 或 `Webhook 通知失败`。

### 4.2 SMTP 发不出邮件

- 确认 smtp_port 与 SSL 模式匹配：465 用 SSL；587 用 STARTTLS（`NETCHECK_SMTP_USE_SSL=false`）。
- 测试账号需开启「服务端授权码」。

## 5. 数据库

### 5.1 pytest 出现大量 error 而非断言失败

- **原因**：多个 pytest 进程同时跑，共用临时 SQLite 文件互踩。
- **解决**：同一时刻只允许一个 pytest 进程；误开后杀掉多余进程重跑。

### 5.2 SQLite 表缺列报错

- **原因**：旧库升级。
- **解决**：后端启动时 `_ensure_sqlite_columns/_ensure_sqlite_indexes` 会自动补列建索引；
  若仍异常，删除 `data/netcheck.db` 重建（演示数据会重新 seed，业务数据请先备份）。

## 6. AI 诊断

### 6.1 接口返回 409「AI 诊断增强未启用」

- **原因**：`NETCHECK_AI_DIAGNOSIS_ENABLED` 未开启或 key/base_url 未配。
- **解决**：`.env` 配置后重启后端：
  ```env
  NETCHECK_AI_DIAGNOSIS_ENABLED=true
  NETCHECK_AI_BASE_URL=https://api.openai.com/v1   # 或 http://localhost:11434/v1 (Ollama)
  NETCHECK_AI_API_KEY=...
  NETCHECK_AI_MODEL=gpt-4o-mini
  ```

### 6.2 返回 200 但 status=error

- **原因**：模型服务网络不通/超时/密钥无效。
- **解决**：看后端日志 `AI 诊断增强失败: ...`；本地可先 `curl` 测 `$BASE_URL/chat/completions`。

## 7. 设备采集（N1）

### 7.1 凭据解密失败 / 采集报错「缺少密钥」

- **原因**：`NETCHECK_SECRET_KEY` 未配置，或配置的值与加密时不一致。
- **解决**：`.env` 设置 `NETCHECK_SECRET_KEY=<随机 32+ 字符>`，重启后端。注意：**凭据加密时使用的 key 必须与解密时一致**，更换 key 需重新录入凭据。

### 7.2 SNMPv3 认证失败（collect_status = auth_failed）

- **原因**：auth_key / username / 认证算法不匹配设备配置。
- **排查**：确认设备 SNMPv3 用户名、authPriv 参数（authKey/authProtocol/privKey/privProtocol），对比 `GET /api/devices/{id}` 中 `last_collect_error`。
- **注意**：snmp3 的 authKey 和 privKey 是密钥（非密码），长度受算法限制（SHA-256 需 ≥ 12 字节）。

### 7.3 SSH host key 未知（collect_status = host_key_unknown）

- **原因**：首次连接，host key 未登记。
- **解决**：首次采集后设备会记录 `host_key_fingerprint`；再次触发采集时若 fingerprint 不变则自动通过。若指纹变了（设备重装），删除设备重新添加并更新 fingerprint。
- **安全**：host key 未知时采集立即中止，不降级为 AutoAdd。

### 7.4 SSH 超时（collect_status = timeout）

- **原因**：SSH 端口（22）未开放或不可达。
- **排查**：确认管理 IP 可 ping、22 端口已监听（`nc -zv <ip> 22`）、`NETCHECK_SSH_TIMEOUT` 设置足够（默认 10s）。

### 7.5 接口速率显示 unknown

- **原因**：首样本无相邻数据，或计数器重启（超过 2^32 下降），或速率超 100Gbps（sanity check）。
- **正常**：这是设计行为，不是 bug。采集 2 次以上后才会产生速率。