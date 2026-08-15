# 演示指南

> 一份「讲得出彩、不会翻车」的演示动线 + 话术提示 + 故障制造脚本。

## 0. 演示前检查清单

- [ ] `./scripts/demo-stack.sh up` 全栈拉起，`status` 输出健康
- [ ] 浏览器打开前端可登录（admin/admin123）
- [ ] Grafana http://localhost:3000 可访问（admin/admin123）
- [ ] 演示设备网络可连 demo 服务端口（18080/18081/18082）
- [ ] 预设 1-2 条巡检任务已创建，避免现场临时配置
- [ ] （可选）AI 已配置或准备「本地 Ollama」方案

## 1. 演示动线（约 8-12 分钟）

### 第一幕：平台与架构（约 2 分钟）

开场话术：
> 「这是一个面向中小型网络的自动化巡检与故障诊断平台，核心解决『人工巡检靠脚本、故障靠人猜』的问题。整体分为四层：资产层、巡检调度层、诊断告警层、可观测展示层。」

演示动作：
- 打开仪表盘，点几个统计卡片过渡。
- （可选）打开 `docs/operations/README.md` 或仓库架构图展示技术栈。

### 第二幕：实时巡检（约 3 分钟）★ 核心亮点

演示动作：
1. 进入「巡检任务」→ 新建任务→勾选 Ping+HTTP+TLS、选择 demo 资产 → 保存。
2. 点「运行」→ 立即切到「任务运行详情」。
3. 台词：**「注意看状态，不用 F5——这是 WebSocket 实时推送，运行进度、结果逐项刷新。」**
4. 运行完成，点开几条结果（正常/警告/失败形成对比）。

要点：demo-web-ok / demo-web-error / demo-web-slow 三条资产会产生 success / failed / warning 三种结果，天然适合对比讲解。

### 第三幕：诊断与 AI 建议（约 2 分钟）

演示动作：
1. 打开「故障诊断」，筛出 demo-web-error 的诊断记录。
2. 台词：**「平台根据检测证据自动生成故障类型与处置建议。」**
3. （若 AI 已配置）点「AI 增强建议」，展示大模型给出的进一步排查方向。

### 第四幕：趋势与可观测大屏（约 2 分钟）★ 视觉冲击

演示动作：
1. 打开「趋势分析」页 → 选资产 → RTT 曲线 / 可用率 SLA 图表。
2. 切到 Grafana（新标签页）：**「这里是 Prometheus 抓取 /metrics 后自动供给的运维大屏，资产状态、运行、告警、耗时都在一个大屏上。」**
3. （可选）演示页开 Grafana 全屏模式。

### 第五幕：告警触达（约 1-2 分钟，可选）

- 若已配置钉钉/企微机器人：把任务指向故障资产再跑一次，**「告警会直接推送到钉钉群」**。

## 2. 现场造故障（Plan B）

若想现场演示「发现故障」的过程，在演示前或中场操作：

```bash
# 停掉 demo-web-error 站点
docker stop demo-web-error 2>/dev/null || docker compose stop demo-web-error

# 或改造成更慢的响应（若已配 web-slow）
```

再触发一次巡检，运行中即可看到 failed 结果与告警。演示结束后记得恢复：

```bash
docker compose start demo-web-error
```

## 3. 话术要点

| 关注点 | 一句话回答 |
|---|---|
| 为什么自研指标？ | 零依赖、演示环境离线可跑；正式环境可平滑换 prometheus_client |
| 并发怎么控制？ | 每运行内资产级并行（check_concurrency=8），全局有界队列防堆积 |
| 多实例会重复执行吗？ | 分布式锁（task_locks 表 + TTL），同一任务同时只有一个实例执行 |
| 安全上做了哪些？ | 登录限流/锁定、token 过期、RBAC 三角色、审计日志全留痕 |
| AI 需要联网吗？ | 可选；Ollama 本地模型即可，接口 OpenAI 兼容，改 base_url 即用 |

## 4. 翻车预案

| 风险 | 预案 |
|---|---|
| WebSocket 断连 | 前端自动回退 2s 轮询，必要时手动刷新 |
| demo 站点容器意外挂了 | `docker compose up -d demo-web-*` 秒级恢复 |
| Grafana 没数据 | `/metrics` 是否 200，Prometheus targets 是否 up（`./scripts/demo-stack.sh verify`） |
| 端口被占用 | `lsof -i :8000` 排查后换端口或释放 |
| Docker 内存被杀（Exit 137） | `docker stats` 看内存，必要时 `docker compose down` 关掉 Grafana/Prometheus 再演示核心链路 |

## 5. 演示后收尾

```bash
./scripts/demo-stack.sh down   # 释放资源（数据卷保留）
```

归档材料：演示 PPT 参照 [[user-guide|用户操作手册]] 与 [[api-reference|API 参考]]。