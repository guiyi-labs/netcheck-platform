# 数据库表结构说明

> 数据库：SQLite
> 位置：Docker volume `db_data` 中的 `/app/data/netcheck.db`

## users

用户表。

关键字段：

- `id`：主键。
- `username`：用户名。
- `password_hash`：密码哈希。
- `display_name`：显示名称。
- `role`：角色。
- `enabled`：是否启用。
- `created_at`、`updated_at`：时间戳。

## assets

资产台账表。

关键字段：

- `id`：主键。
- `name`：资产名称。
- `asset_type`：资产类型。
- `ip`：IP 或主机标识。
- `hostname`：主机名。
- `port`：默认服务端口。
- `protocol`：协议。
- `status`：资产状态，`online/offline/warning/unknown`。
- `description`：描述。
- `created_at`、`updated_at`：时间戳。

## inspection_tasks

巡检任务表。

关键字段：

- `id`：主键。
- `name`：任务名称。
- `description`：任务描述。
- `check_types`：检测类型，逗号分隔。
- `enabled`：是否启用。
- `schedule_enabled`：是否启用定时巡检。
- `schedule_interval_minutes`：定时间隔分钟。
- `next_run_at`：下次执行时间。
- `last_scheduled_run_at`：最近一次定时执行时间。
- `created_at`、`updated_at`：时间戳。

## inspection_task_assets

巡检任务与资产多对多关系表。

关键字段：

- `task_id`：巡检任务 ID。
- `asset_id`：资产 ID。

## inspection_runs

巡检运行记录表。

关键字段：

- `id`：主键。
- `task_id`：所属任务。
- `status`：运行状态。
- `trigger_type`：触发方式，`manual/scheduled`。
- `started_at`：开始时间。
- `finished_at`：结束时间。
- `error_message`：运行错误信息。

## inspection_results

巡检结果表。

关键字段：

- `id`：主键。
- `run_id`：运行 ID。
- `asset_id`：资产 ID。
- `check_type`：检测类型，`ping/port/http/dns`。
- `target`：检测目标。
- `status`：结果状态，`success/warning/failed`。
- `response_time`：响应时间。
- `message`：成功或提示信息。
- `error_message`：错误信息。
- `checked_at`：检测时间。

## diagnosis_records

故障诊断记录表。

关键字段：

- `id`：主键。
- `run_id`：运行 ID。
- `result_id`：关联巡检结果。
- `asset_id`：资产 ID。
- `check_type`：检测类型。
- `fault_type`：故障类型。
- `severity`：故障等级。
- `suggestion`：处理建议。
- `evidence`：诊断依据。
- `created_at`：创建时间。

## reports

报告记录表。

关键字段：

- `id`：主键。
- `report_name`：报告名称。
- `report_type`：报告类型。
- `report_date`：报告日期。
- `run_id`：关联运行。
- `task_id`：关联任务。
- `file_name`：文件名。
- `file_path`：文件路径。
- `file_size`：文件大小。
- `created_at`：创建时间。

## alerts

告警表。

关键字段：

- `id`：主键。
- `asset_id`：资产 ID。
- `run_id`：触发运行 ID。
- `result_id`：触发结果 ID。
- `diagnosis_id`：关联诊断 ID。
- `alert_title`：告警标题。
- `alert_level`：告警等级。
- `alert_status`：告警状态，`active/confirmed/recovered`。
- `alert_key`：去重键。
- `check_type`：检测类型。
- `fault_type`：故障类型。
- `evidence`：告警依据。
- `suggestion`：处理建议。
- `first_triggered_at`：首次触发时间。
- `last_triggered_at`：最近触发时间。
- `trigger_count`：触发次数。
- `consecutive_failures`：连续失败次数。
- `consecutive_successes`：连续成功次数。
- `confirmed_by`：确认人。
- `confirmed_at`：确认时间。
- `recovered_at`：恢复时间。
- `recovery_reason`：恢复原因。
- `created_at`、`updated_at`：时间戳。

## alert_policies

告警策略表。

关键字段：

- `id`：主键。
- `name`：策略名称。
- `enabled`：是否启用。
- `slow_response_threshold`：慢响应阈值。
- `failure_threshold`：连续失败触发阈值。
- `recovery_threshold`：连续正常恢复阈值。
- `deduplicate_enabled`：是否启用同类告警去重。
- `created_at`、`updated_at`：时间戳。

## discovery_scans

资产发现扫描任务表。

关键字段：

- `id`：主键。
- `target_range`：扫描范围。
- `scan_mode`：扫描模式。
- `ports`：端口列表。
- `status`：扫描状态。
- `total_targets`：目标数量。
- `discovered_count`：发现数量。
- `error_message`：错误信息。
- `started_at`：开始时间。
- `finished_at`：结束时间。

## discovery_results

资产发现结果表。

关键字段：

- `id`：主键。
- `scan_id`：扫描任务 ID。
- `ip`：发现 IP。
- `hostname`：主机名。
- `open_ports`：开放端口。
- `status`：发现状态。
- `already_exists`：资产是否已存在。
- `matched_asset_id`：匹配到的资产 ID。
- `imported_asset_id`：导入后的资产 ID。
- `created_at`：发现时间。
