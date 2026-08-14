# 阶段 A 完成归档：工程加固（登录安全 / 异步执行 / 数据层 / 审计 / 备份）

> 完成日期：2026-08-14
> 目标：把"可演示"升级为"可稳定运行"，为 B/C/D 阶段打底。
> 测试：`49 passed`（全量回归通过）。

## 1. A1 登录安全加固

### 变更内容

- **token 过期**：`users` 表新增 `api_token_expires_at`；登录时按 `NETCHECK_TOKEN_TTL_HOURS`（默认 24h）
  写入过期时间，`get_current_user` 校验过期即 401。旧数据（过期时间为空）兼容视为不过期。
- **登录失败限流**：新增 `app/core/ratelimit.py`，按「用户名 + 来源 IP」统计连续失败次数，
  达到 `NETCHECK_LOGIN_MAX_ATTEMPTS`（默认 5 次）后锁定 `NETCHECK_LOGIN_LOCK_MINUTES`（默认 15 分钟），
  锁定期间即使密码正确也返回 429。进程内实现（单实例足够，多实例可扩展 Redis）。
- **密码策略**：新增 `check_password_policy`（`NETCHECK_PASSWORD_MIN_LENGTH` 默认 8 位），
  在改密/建号接口执行。
- **修改密码接口**：`POST /api/auth/change-password`，改密后旧 token 立即失效，强制重新登录。

### 接口变化

- `POST /api/auth/change-password`：`{old_password, new_password}`，成功返回 200 并清空旧 token。
- 登录失败 5 次后返回 `429`，detail 提示剩余锁定秒数。

## 2. A2 巡检执行异步化

### 设计

`POST /api/tasks/{id}/run` 不再同步阻塞：只创建一条 `pending` 运行记录并入队后立即返回，
后台 worker 线程完成「检测 → 诊断 → 告警 → 资产状态回写」。

- 新增 `app/services/executor.py`：内存队列 + 守护线程；`enqueue_task_run()` 建 pending 记录并入队；
  `process_run()` 执行全流程；同一运行内不同资产并行检测（`NETCHECK_CHECK_CONCURRENCY` 默认 8）。
- 定时任务（调度器）同样改为入队执行，不再占用 APScheduler 线程。
- 新增 `GET /api/tasks/runs/{run_id}` 供前端/测试轮询运行状态。
- 关键点：检测线程只读「资产标量字段」（主线程构造纯数据再提交），避免跨线程共享 ORM 状态；
  诊断/告警/状态回写先于 `completed` 标记提交，杜绝轮询竞态。

### 接口变化

- `POST /api/tasks/{id}/run`：返回 `pending` 运行记录（`message: 巡检任务已提交执行`）。
- 新增 `GET /api/tasks/runs/{run_id}`：单条运行详情（轮询用）。
- 前端 `task-run.html` 自动轮询：存在 `pending/running` 运行记录时每 2s 刷新。

## 3. A3 数据层加固（索引 + 分页）

新增组合索引（新库由 ORM 自动建立，历史 SQLite 库由 `init_db` 里的幂等 SQL 补齐）：

- `inspection_results (run_id, status)`、`(asset_id, checked_at)`、`(checked_at)`
- `inspection_runs (task_id, status)`
- `alerts (alert_key, alert_status)`

列表接口此前已基本分页；本轮补充了单条运行详情接口与审计日志分页，并增加分页回归测试。

## 4. A4 MySQL 适配 + 配置外置化

- `requirements.txt` 增加 `pymysql`；`database.py` 非 SQLite 路径使用
  `pool_pre_ping=True, pool_recycle=3600` 连接池参数。
- `docker-compose.yml` 增加可选 `netcheck-mysql` 服务（默认注释）。
- 新增 `.env.example` 覆盖全部 `NETCHECK_*` 配置项（含 B 阶段通知、D 阶段 AI 预留项）；
  `settings.model_config` 增加 `env_file=".env"` 与 `extra="ignore"`。

## 5. A5 审计日志

- 新增 `operation_logs` 表与 `POST /api/audit-logs`（用户名/动作/对象类型/日期筛选 + 分页）。
- 已接入的关键写操作：登录/登出、资产增删改、任务增改/启停/执行、告警确认/恢复、策略更新、
  报告生成/删除、资产发现扫描/导入。
- 前端新增「审计日志」页面（`audit.html` / `js/audit.js`），顶部导航新增入口。

## 6. A6 备份脚本

- `scripts/backup.sh`（Linux/macOS）与 `scripts/backup.ps1`（Windows）：
  备份 SQLite（含 WAL/SHM 副文件）与报告目录到带时间戳归档，自动清理 N 天前旧备份。
- 恢复说明内置在脚本输出中；支持 `NETCHECK_DATA_DIR` 等环境变量覆盖路径。

## 7. 验证结果

```text
49 passed in 5.69s
```

新增测试：`test_auth.py`（token 过期/限流/改密）、`test_hardening.py`（索引/分页/MySQL/配置）、
`test_audit.py`（审计落库与查询）、async 轮询改造（`test_inspection.py` / `test_alerts.py` /
`test_dashboard_results_reports.py`）。

## 8. 已知边界与后续

- 登录限流为进程内实现，多实例部署需迁移到 Redis。
- 异步执行失败后无自动重试（B 阶段补「失败重试」）。
- 未做多用户/角色（B 阶段补）。
- SQLite 行级写竞争在并发巡检下可能出现短暂 `database is locked`，频率测试可接受；
  生产建议切 MySQL（B 阶段给出迁移指导）。