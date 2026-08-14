# 阶段 B 完成归档：业务补强（通知 / CSV / 任务控制 / 角色 / TLS / 变更日志）

> 完成日期：2026-08-14
> 目标：补全实用业务能力，为真实网络检测打底。
> 测试：`71 passed`（全量回归通过）。

## 1. B1 告警通知

- 新增 `app/services/notifications.py`：`dispatch_alert_notifications(run_id, db)` 在 `process_run` 末尾调用。
- 支持两种渠道：
  - **邮件通知**（SMTP）：SSL / STARTTLS 双模式；邮件内容列出本次告警条数、各告警等级/资产/故障/依据/建议；支持 `smtp_user/smtp_password` 认证。
  - **Webhook**：POST JSON `{"source":"netcheck-platform","alerts":[...]}`；支持 `webhook_headers`（JSON 或 `Key:Value` 格式）自定义请求头（常用于企业微信/钉钉/Slack）。
- 配置项：`notification_enabled`（总开关，默认 false）、`notification_min_level`（最低通知等级，默认 warning：只通知 warning 及以上）。
- 未配置对应渠道或无告警时跳过；任何投递异常仅日志记录，不阻断巡检主流程。
- 测试：`test_notifications.py` 4 个用例（Webhook / 邮件 / 等级过滤 / 未启用跳过）。

## 2. B2 资产批量导入/导出 CSV

- `POST /api/assets/import`：接收 CSV 文件（UTF-8，必填字段 name/ip）；跳过空 name/ip 与重复 IP；返回 `{imported, skipped, errors:[{row,error}]}`。
- `GET /api/assets/export`：导出全部资产为 CSV（UTF-8 with BOM，Excel 可直接打开）。
- 前端 `assets.html` 新增「导出 CSV」下载按钮与「导入 CSV」文件选择器（含结果弹窗提示）。
- 测试：`test_asset_import_export.py` 3 个用例；`requirements.txt` 增加 `python-multipart`。

## 3. B3 任务取消/重试/Cron 调度

### 取消

- `InspectionRun` 新增 `cancel_requested: bool`；`POST /api/tasks/runs/{run_id}/cancel` 置位。
- 执行器（`_execute_checks`）每收集一个资产结果后查询 DB `cancel_requested`，已取消则丢弃结果并返回 `"cancelled"` 状态，`process_run` 标记运行为 cancelled。

### 失败重试

- 执行器新增「全失败判定」：所有检测结果均为 `failed` 时运行状态标记为 `failed`（便于重试），否则正常 `completed`。
- `POST /api/tasks/runs/{run_id}/retry`：仅失败/已取消运行可重试；创建新 pending 运行并入队；若任务已停用则 409 拒绝。

### Cron 调度

- `InspectionTask` 新增 `schedule_cron: str`；新增 `app/services/schedule.py` 统一计算下次执行时间（Cron / 分钟间隔）。
- 调度器（APScheduler `CronTrigger`）与执行器均从 `schedule.py` 读取，避免循环导入。
- 前端任务弹窗新增 Cron 表达式字段（间隔分钟与 Cron 二选一，优先 Cron）。

- 测试：`test_task_control.py` 3 个用例（取消、重试、Cron 表达式合法性/调度注册）。

## 4. B4 多用户与角色权限

- `User` 新增 `is_active: bool`；登录时 `is_active=False` 的账号返回 401。
- 角色体系：
  - `admin`：全部权限，包含用户管理；
  - `operator`：可读写资产/任务/报告/告警；
  - `viewer`：只读（所有写操作返回 403）。
- 新增 `app/api/users.py`：`GET /api/users`（分页列表）、`POST /api/users`（创建，强制密码策略）、`PUT /api/users/{id}`（改角色/改密/启用停用）、`DELETE /api/users/{id}`（自保：不能删自己）。
- `app/core/deps.py` 新增 `require_write`（写操作拦截 viewer）与 `require_admin`（用户管理拦截非 admin）；所有 mutation 端点已升级为 `require_write`。
- 前端新增 `users.html` + `js/users.js`（admin-only）；导航栏仅 admin 可见「用户管理」入口。
- 测试：`test_users_roles.py` 5 个用例（创建/改密/停用/角色限制/自保/登录拦截）。

## 5. B5 TLS 证书检测器

- `app/services/checkers.py` 新增 `TlsChecker`：连接端口（优先 443/8443/9443，未配置 TLS 端口时默认 443）获取证书，解析 `notAfter`；剩余天数 < `tls_expiry_warning_days`（默认 30）判为 warning，已过期判为 failed。
- `CHECK_TYPES` 增加 `tls`；任务弹窗新增「TLS 证书」检测类型复选框；结果页/巡检结果页 `typeLabel` 同步更新。
- 测试：`test_tls_checker.py` 5 个用例（有效 / 即将过期 / 已过期 / 连接失败 / 默认端口 443）。

## 6. B6 资产变更日志

- 新增 `AssetChangeLog` 表：`asset_id/action(CREATE|UPDATE|DELETE)/field/old_value/new_value/username/detail/changed_at`。
- `app/services/asset_change.py`：`record_asset_create`（变更字段汇总）、`record_asset_update`（逐字段 diff，只写变化字段）、`record_asset_delete`（保留完整快照）。
- `GET /api/assets/{asset_id}/changes`：分页查询资产变更历史（按 ID 倒序）。
- 前端资产变更历史查询按钮与页面（`asset-changes.html` / `js/asset-changes.js`，展示操作/字段/新旧值/操作人/时间）。
- 测试：`test_asset_changes.py` 2 个用例（创建+更新+删除可追溯、无 token 拒绝）。

## 7. 验证结果

```text
71 passed in 7.86s
```

## 8. 已知边界与后续

- 通知渠道目前仅 SMTP/Webhook，缺少即时消息（飞书/企微机器人）与短信。
- TLS 检测器默认 443 端口，不支持自签证书跳过验证（需新增 `tls_verify_cert=False` 配置）。
- 角色体系为固定三角色；若需自定义角色权限矩阵，可迁移到 RBAC 权限表。
- 批量导入不支持 Excel 格式；若需 Excel 可引入 openpyxl。
- Cron 时区固定为 `Asia/Shanghai`；多地区部署需配置化。