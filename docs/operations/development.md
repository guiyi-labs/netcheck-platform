# 开发指南

> 面向后续维护者/协作者：代码结构、新增检测器/端点/页面的标准流程、测试与提交约定。

## 1. 代码结构

```text
backend/app/
├── api/           # FastAPI 路由，每个领域一个文件（assets/tasks/alerts/diagnosis/stats/realtime...）
├── core/          # config（pydantic-settings）、database（engine/session/迁移）、security、deps、ratelimit
├── models/        # SQLAlchemy ORM（SQLite/MySQL 兼容）
├── schemas/       # Pydantic 输入输出模型
└── services/      # 核心业务（executor/checkers/scheduler/notifications/diagnosis/alerts/...）

frontend/
├── *.html         # 每页一个文件，底部引入 js/api.js、js/auth.js、js/<page>.js
└── js/            # api.js(请求封装)、auth.js(登录态+导航)、ws.js(实时推送)、<page>.js

observability/     # Prometheus 抓取配置 + Grafana 供给（datasource/dashboard）
scripts/           # 备份/验证/演示脚本
tests/（backend/tests） # pytest 测试
```

## 2. 常用命令

```bash
# 运行全部测试（必须从项目根目录）
.venv/bin/python -m pytest -q

# 只跑某个文件
.venv/bin/python -m pytest backend/tests/test_stats.py -q

# 后端热加载启动
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 前端静态服务
cd frontend && python3 -m http.server 8080
```

## 3. 新增检测器（CheckType）

1. 在 `backend/app/services/checkers.py` 新建 `XXChecker` 类：
   ```python
   class MyChecker(BaseChecker):
       check_type = "mycheck"          # 唯一标识
       async def check(self, asset):    # 或同步版本
           return [CheckResult("success", asset.ip, 1, "ok")]  # 或 failed/warning
   ```
2. 把实例加入 `CHECKERS` 字典：
   ```python
   CHECKERS = {c.check_type: c for c in (PingChecker(), PortChecker(), HttpChecker(), DnsChecker(), TlsChecker(), MyChecker())}
   ```
3. `backend/app/schemas/inspection.py` 的 `CHECK_TYPES` 增加 `"mycheck"`。
4. 前端 `task-run.js` / `results.js` / `tasks.js` 的 `typeLabel` 增加标签。
5. 写测试：mock checker 输出，调用执行链路断言。

## 4. 新增 REST 端点

1. `backend/app/api/` 新建或扩展 router，声明 `prefix` 与 `tags`。
2. 写 `schemas/` 输入输出（统一 `Response[xxx]` 包络、`PageData` 分页）。
3. 在 `backend/app/main.py` import 并 `app.include_router(...)`。
4. 写测试：`client` fixture 登录 + 调用 + 断言包络。

## 5. 测试约定

- `backend/tests/conftest.py` 固定数据库为临时 SQLite，`client` fixture 已含演示数据（admin/admin123、12 条资产）。
- 检测器打桩：`monkeypatch.setitem(CHECKERS, "ping", FakeChecker())`。
- 运行等待：`helpers.wait_run(client, headers, run_id)` 轮询到终态。
- **禁止并发跑 pytest**（共享临时 SQLite 会互踩）。
- 测试文件按主题命名：`test_<topic>.py`。

## 6. 提交约定

- 里程碑提交信息：`feat: phase X ...`（维持可读历史）。
- 参考提交序列：
  - A 阶段 `915cd79` / B `1884c50` / C `d3f0a24` / D `1a2a7fd`
  - 演示增强 `7d3c7c7` / 指标格式修复 `8a86979`
- 不提交 IDE 配置（`.idea/` 已在 .gitignore）。

## 7. 关键设计约束（改动前必读）

1. **巡检异步**：运行先落库 pending 再入队；`process_run` 消费；终态提交前先做诊断/告警/资产回写（顺序不可反，避免竞态）。
2. **线程安全**：检测线程不要共享 ORM Session；资产信息以 plain dict 传入，ORM 行在主线程构建。
3. **分布式锁**：`process_run` 开始 `acquire_lock`、结束 `release_lock`（finally）；锁 TTL 10 分钟。
4. **通知不阻塞巡检**：`dispatch_alert_notifications` 任何异常只记日志。
5. **指标格式**：Prometheus `# TYPE/# HELP` 必须用裸指标名；标签只出现在样例行。
6. **配置外置**：新增可配置项务必走 `config.py` + `.env.example`。

## 8. N1 设备采集约束（改动前必读）

1. **凭据绝不回显**：`DeviceCredential` 密钥字段必须在写库前 `encrypt_secret`；API/日志/前端只允许 `has_secret`/算法/摘要。
2. **OID 白名单**：只允许 `sys*` 与 `ifTable` 子树（`DEVICE_OID_ALLOWLIST`），禁止任意 OID 浏览器。
3. **SSH 只读**：命令必须来自 `SSH_READONLY_COMMANDS` 厂商 allowlist；host key 校验走 `HostKeyPolicy`，禁止 `AutoAddPolicy`。
4. **速率真实语义**：首样本/缺样本速率必须 `None`（页面显示 unknown），禁止 0 或绿色冒充健康；64 位计数器回绕按 2^64 修正。
5. **有界采集**：接口数、请求数、命令数、输出字节数、批量设备数都有上限（config 可调）。
6. **失败分类清晰**：`auth_failed/priv_failed/timeout/host_key_unknown/host_key_mismatch/conn_refused` 必须映射到设备 `collect_status`。

## 8.1 N2 配置备份约束（改动前必读）

1. **配置读取命令 allowlist**：只允许 `CONFIG_READ_COMMANDS` 厂商映射内的命令；禁止任意命令拼接、禁止写配置。
2. **脱敏必达**：配置入库前必须 `redact_config`（password/secret/community/key 值替换为 `********`），明文密钥绝不落库；全文仅存 SHA-256 哈希。
3. **去重**：`config_full_hash` 相同不产生新快照；`changed=True` 仅当相邻快照 hash 不同。
4. **有界**：配置快照字节上限 `MAX_CONFIG_SNAPSHOT_BYTES`（512KB），超长截断。
5. **审计**：任何配置采集/变更必须写 `OperationLog`（action=`device_config_backup`）。
6. **不做配置下发**：N2 只读备份，diff 只读展示，无下发/回滚/覆盖能力。