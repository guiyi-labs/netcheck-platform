# 阶段 D 完成归档：进阶扩展（AI 诊断 / Prometheus / K8s / 分布式锁 / 有界队列）

> 完成日期：2026-08-14
> 目标：生产就绪特性与运维可观测性。
> 测试：`96 passed`（全量回归通过）。

## 1. D1 AI 辅助诊断（可选增强）

- 新增 `app/services/ai_diagnosis.py`：调用 OpenAI 兼容 chat/completions 接口，基于诊断记录的
  资产/故障类型/证据/平台建议 生成 ≤150 字进一步排查建议；支持 `temperature=0.3` 低随机性输出。
- 新增 `POST /api/diagnosis/{id}/ai-suggestion`（需登录）：
  - AI 未启用时返回 409 提示配置；
  - 服务调用失败返回 `{"status":"error","message":"..."}`（不抛异常）；
  - 正常返回 `{"status":"ok","model":"...","content":"..."}`。
- 配置项：`ai_diagnosis_enabled`、`ai_base_url`、`ai_api_key`、`ai_model`、`ai_timeout`（
  均可通过 `.env` 设置）。
- 测试：`test_ai_diagnosis.py` 3 例（未启用回落、网络异常、正常增强）。

## 2. D2 Prometheus 指标导出

- 新增 `app/services/metrics.py`（零依赖）：实时聚合 DB 统计生成 Prometheus text format 指标：
  - `netcheck_assets_total / assets_by_status{status=...}`
  - `netcheck_tasks_total / tasks_enabled`
  - `netcheck_runs_total / runs_by_status{status=...}`
  - `netcheck_results_total / results_by_status{status=...} / results_avg_response_ms`
  - `netcheck_alerts_total / alerts_by_status{status=...} / alerts_by_level{level=...}`
  - `netcheck_diagnoses_total`
- 新增 `GET /metrics`（无鉴权，与 `/health` 同级，便于 Prometheus/K8s Liveness 抓取）。
- 测试：`test_metrics.py` 2 例（无鉴权返回、text/plain 格式含基础指标）。

## 3. D3 Kubernetes 容器巡检扩展

- 新增 `scripts/k8s-inspect.sh`：调用 `kubectl` 采集节点/工作负载/Pod 状态快照，输出 JSON，
  供 netcheck 外部数据导入或 K8s Dashboard 补充。
- 覆盖：节点 Ready 状态、控制面角色标记、全命名空间 Pod 统计、非 Running Pod 列表。
- 文档：`docs/phase-c/container-network.md` 中补充容器/主机网络调试表（C1 延续），以及
  本脚本用法说明。

## 4. D4 分布式执行锁

- 新增 `TaskLock` 表（`task_locks`）：`task_id`（PK）、`worker_id`、`acquired_at`、`expires_at`（
  默认 +10 分钟 TTL）。
- 新增 `app/services/execute_lock.py`：`acquire_lock`（抢占/续约）/ `release_lock`（释放
  仅限本人持有或已过期）；`worker_id` 由 `hostname:pid` 组成，多实例天然区分。
- 执行器 `process_run`：运行开始前先 `acquire_lock`，拿不到锁（另一实例持有）直接标记
  `failed`（消息：`分布式锁`），在 `finally` 中释放锁；避免多实例并发执行同任务。
- 多实例部署时配合 MySQL 共享库使用；SQLite 单文件下仍生效（同一主机多进程）。
- 测试：`test_lock_queue.py` 3 例（锁抢占、队列满回落、加锁-释放周期）。

## 5. D5 有界执行队列

- `run_queue_maxsize`（默认 1000）：当待执行运行队列已满时，`enqueue_task_run` 不入队，
  直接将运行标记 `failed`（错误消息：`巡检执行队列已满，请稍后重试`），防止无限堆积。
- 实现：`_run_queue.put_nowait` + `queue.Full` 捕获 → `_mark_queued_run_failed`。
- 测试：`test_lock_queue.py`（`test_queue_full_marks_run_failed`）。

## 6. 验证结果

```text
96 passed in 8.34s
```

## 7. 已知边界与后续

- AI 诊断增强仅在用户触发时调用（避免无谓 token 消耗），目前为同步阻塞；如需异步可
  迁移到 Celery/RQ 后台任务。
- Prometheus 指标每次 `/metrics` 抓取都查库聚合，高 QPS 下可引入内存计数 + 按时间窗口
  刷新。
- 分布式锁 TTL 为 10 分钟；极端长时间运行（>10 分钟）可能导致锁过期，后续可加续租
  心跳。
- K8s 脚本仅做只读采集；若需纳入 netcheck 统一调度，可实现为「外部检测器」
  （ExternalChecker）模式。