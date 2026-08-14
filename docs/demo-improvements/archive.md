# 演示出彩增强（WebSocket 实时 / 趋势可视 / Grafana 大屏 / 告警渠道）

> 完成日期：2026-08-14
> 目标：让一次演示具备「实时感 + 图表冲击力 + 可观测性大屏 + 真实渠道触达」。
> 测试：`110 passed`（全量回归通过，新增 5 个测试文件）。

## 1. 实时推送（WebSocket）

- **后端**：`app/services/realtime.py` 线程安全中枢（每连接一个 asyncio.Queue，
  executor 后台线程 `hub.publish` 只是 put_nowait，非阻塞）；`/ws/runs?token=` 端点
  （路由 `app/api/realtime.py`），token 复用登录令牌（校验 api_token + 有效期 + is_active），
  30s 空闲发送 ping 心跳检测断线。
- **事件**：`{"type":"run.updated","run_id":..., "task_id":..., "status":...}`，
  executor 在 running / completed / failed / cancelled 各状态转换点广播。
- **前端**：`js/ws.js`（指数退避自动重连）；`task-run.js` 订阅当前任务事件实时刷新列表与
  结果，WS 掉线时自动回退 2s 轮询兜底。
- 测试：`test_realtime.py` 4 例（鉴权拒绝、广播可达、生命周期事件流）。

## 2. 趋势分析（ECharts）

- **后端**：`app/api/stats.py` 三个聚合端点：
  - `GET /api/stats/rtt-trend?asset_id&days` — 每日平均/最大 RTT（ms）
  - `GET /api/stats/availability?asset_id&days` — 每日可用率（success 占比 %）
  - `GET /api/stats/run-durations?days&limit` — 最近运行耗时（秒）
  - `GET /api/stats/assets` — 资产下拉候选
- **前端**：`trends.html` + `js/trends.js`（ECharts 5 CDN）：RTT 曲线（平均主 + 最大虚线）、
  可用率柱状（分级着色 ≥99 绿 / ≥95 黄 / <95 红）、运行耗时柱状；支持资产切换与天数选择，
  窗口缩放自适应。
- 测试：`test_stats.py` 5 例（鉴权、资产列表、RTT/可用率/耗时数据正确性）。

## 3. Prometheus + Grafana 一键演示

- `docker-compose.yml` 新增 `prometheus`（v2.53，抓取 `netcheck-backend:8000/metrics`，15s
  间隔）与 `grafana`（v11.1，admin/admin123，禁止注册）。
- **自动供给**：`observability/prometheus/prometheus.yml` 抓取配置；
  `observability/grafana/provisioning/`（datasource uid=prometheus + dashboard file provider）；
  `observability/grafana/dashboards/netcheck-overview.json` 中文总览面板：
  资产总数 / 启用任务 / 告警总数（stat）、资产状态与运行状态饼图、告警等级分布、
  运行状态时序、检测结果状态时序、平均响应耗时时序。
- 演示脚本 `scripts/demo-stack.sh`：`up`（构建+启动+自检）`status` `verify`（抓取目标、
  指标查询、Grafana 可访问）`down`。

## 4. 告警渠道适配器

- `notifications.py` 新增平台化 adapter 模式：`webhook_scheme`（`generic` / `dingtalk` /
  `wecom` / `feishu`），`_build_platform_payload` 按平台构造消息：
  - 钉钉：`msgtype=markdown`（title + text）
  - 企微：`msgtype=markdown`（content）
  - 飞书：`msg_type=text`
- 新增配置 `NETCHECK_WEBHOOK_SCHEME`；其余配置（webhook_url / 等级阈值 / 邮件）不变。
- 测试：`test_notification_adapters.py` 5 例（各平台 payload 与端到端投递 body）。

## 5. 演示动线建议

```text
1. 终端: ./scripts/demo-stack.sh up            # 全栈拉起
2. 浏览器: http://localhost:8080 → 登录 admin/admin123
3. 巡检任务页 → 创建/运行任务 → 打开任务运行详情：
   运行状态在 2 秒内实时变化（WebSocket）
4. 趋势分析页：RTT 曲线 / 可用率 SLA / 运行耗时
5. 新标签页: http://localhost:3000（admin/admin123）→ NetCheck 巡检平台总览大屏
6. 可选: 配置钉钉机器人 webhook + NETCHECK_WEBHOOK_SCHEME=dingtalk 再跑一次故障任务，
   观察告警推送
```

## 6. 验证结果

```text
110 passed in 10.64s
```

新增测试：`test_realtime.py`(4) `test_stats.py`(5) `test_notification_adapters.py`(5)。

### 6.1 实机验证（本机 Docker，已跑通）

```text
targets:  [('netcheck-backend', 'up', '')]
assets_total: 12
netcheck_assets_by_status{label="online"} 7 / offline 3 / warning 1 / unknown 1
Grafana datasources:  [('Prometheus', 'prometheus', 'prometheus')]
Grafana dashboards:   [('NetCheck 巡检平台总览', 'netcheck-overview')]
```

期间修复一个问题：Prometheus text format 要求 `# TYPE/# HELP` 行使用裸指标名（不能带
`{label=...}`），原实现把标签写进 TYPE 行导致抓取报
`invalid metric type ... gauge` 目标变 down。已改为 `_family()` 只在样例行带标签
（`backend/app/services/metrics.py`）。

## 7. 后续可选

- WebSocket 鉴权升级为独立短时效 ticket（当前复用登录 token，30 分钟 TTL 内有效）。
- 趋势页可加资产对比叠加、报警阈值线、导出 PNG。
- Grafana 面板可增加 SLA 目标线、告警列表表格、探针拓扑图。