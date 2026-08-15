# N2.1 配置备份安全与一致性收口 — Change Record

- 日期：2026-08-14
- 分支：`main`（本地，未推送；超前 `origin/main` 12 个提交）
- 标题建议：`refactor: N2.1 config-backup security & consistency hardening — PEM/isakmp/WireGuard redaction state machine, bounded streamed reads + truncated semantics, operator/admin authz, DB unique dedup + retention + device-delete cascade, diff context/row limits (229 passed)`

## 变更文件

| 文件 | 变更 |
|---|---|
| `backend/app/services/config_backup.py` | P0 PEM 私钥块状态机 + isakmp/WireGuard 脱敏 + 缩进保留；`_read_limited` 流式有界读取（stdout/stderr）+ UTF-8 边界；`config_full_sha256` 哈希语义文档；`collect_config_snapshot` 传密码 + 唯一约束冲突回退 + `_enforce_retention`；`diff_configs(context_lines)` + `skip` 行 |
| `backend/app/models/device.py` | `DeviceConfigSnapshot` 增加 `truncated` 列 + `(device_id, config_full_hash)` 唯一约束 |
| `backend/app/api/devices.py` | latest/diff 改 `require_operator_admin`；diff 增加 `context_lines`/行数上限 `capped`/from-to 时间窗校验；collect 返回 `truncated`；delete 级联清理快照；audit 含 truncated 详情 |
| `backend/app/core/deps.py` | 新增 `require_operator_admin`（viewer → 403） |
| `backend/app/core/config.py` + `.env.example` | `config_snapshot_retention` / `config_diff_max_rows` / `config_diff_context_lines` |
| `backend/app/schemas/device.py` | snapshot/text/collect/diff 增加 `truncated`、`capped`、`skip` |
| `frontend/js/devices.js` | 快照表 truncated 徽标、skip 行弱样式、capped 提示 |
| `backend/tests/test_config_n2_1.py` | 新增 38 用例（脱敏/有界/哈希/权限/并发/保留/级联/diff） |
| `backend/tests/test_config_backup.py` | 有界测试改写为流式 fake + 新增哈希语义 |
| `README.md` / `docs/final-delivery/api-list.md` | N2/N2.1 文档与 API 清单更新 |
| Obsidian `16 N2.1 ... 实施归档` | 新归档 + 14/04 更新 |

## 行为变化（对用户可见）

1. 配置全文（`configs/latest`）与 diff 现在要求 operator/admin；viewer 返回 403。
2. 配置快照删除设备时随之清理；每台设备最多保留 20 份快照（`NETCHECK_CONFIG_SNAPSHOT_RETENTION`）。
3. diff 返回增加 `capped` 字段与 `context_lines` 参数；超大 diff 截断并标记。
4. 采集输出超限时快照标记 `truncated`，哈希为该内容子集的哈希。
5. PEM 私钥块（含 RSA/EC/OPENSSH）、`crypto isakmp key`、WireGuard 密钥行开启脱敏。

## 测试

- 本地全量：`229 passed`（`backend/tests`）
- 新增：`backend/tests/test_config_n2_1.py` 38 用例

## 未推送

- 本记录对应提交未推送（`origin/main` 仍为旧基线）。推送前需权限确认。