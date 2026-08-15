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
---

## 增补：N3 前置门禁（实验 Secret 与可复现环境检查，2026-08-14）

### 提交内容（本批）

| 文件 | 变更 |
|---|---|
| `docs/operations/n1-lab.md`（新） | 消除 `scripts/n1-lab.sh` 断链：Docker bridge 网络 + Docker DNS 可复现启动方式（构建/网络/冒烟/完整验证/清理/归档要求），标注凭据为文档测试值 |

### 工作树修复（未提交，另属 Agent 归属待确认）

| 文件 | 修复 |
|---|---|
| `scripts/lab/Dockerfile.lab` | `createUser SHA`（SHA-1）→ `SHA-256` 与采集端对齐（真实验证必要）；凭据改 `--build-arg` 覆盖，默认仍为文档测试值 |
| `scripts/n1_real_verify.py` | 凭据改环境变量读取（N1_SNMP_AUTH 等）；docstring 更新为 bridge 网络复现步骤；接口字段 `status`→`admin_status`/`oper_status` |

### 实测证据（2026-08-14，alpine 3.22 + net-snmp 5.9.4 + openssh，netcheck-n1-lab:latest）

- SNMPv3 authPriv（SHA-256 + AES-128）：采集 sysName/sysDescr/sysUpTime + ifTable ✅
- SSH：root 密码认证、host key 未知/匹配/不匹配、错误密码 auth_failed ✅
- N2 配置备份：`cat /etc/ssh/sshd_config` 真实读取 124 行 + 脱敏预览 ✅
- 未阻塞：SNMP 错误凭据分类返回 `error` 而非 `auth_failed`（pysnmp 异常路径差异，已记录待复核）

### Secret 结论

`Dockerfile.lab` 与 `n1_real_verify.py` 全部凭据为文档测试值（`netcheckauth`/`netcheckpriv`/`netcheck123`/`public`），
无真实 Secret 泄漏；`n1_mock_demo.py` 仅脱敏演示字符串。

---

## 增补：N3 真实网络实验与证据（2026-08-15）

### 提交内容

| 文件 | 变更 |
|---|---|
| `scripts/lab/Dockerfile.lab` | 纳入版本控制：alpine 3.22 + net-snmp 5.9.4 + openssh，createUser SHA-256，凭据 `--build-arg` 覆盖（文档测试值） |
| `scripts/n1_real_verify.py` | 纳入版本控制：完整真实验收脚本（SNMPv3/SSH/host key/配置备份/**配置变化 diff**/命令不支持），凭据 env 覆盖，N3 diff 场景扩展 |
| `backend/app/services/snmpv3_collector.py` | `classify_error` 识别真实 USM 异常（WrongDigest/UnknownUserName/NotInTimeWindow/UnknownEngineID）→ auth_failed（N3 实测发现） |
| `backend/tests/test_snmpv3.py` | +4 个 USM 异常分类测试 |
| `docs/final-delivery/n3-real-verification.md` | N3 验收记录（环境/版本/证据/边界/风险） |

### 真实验收结果（2026-08-15，全部通过）

SNMPv3 authPriv(SHA-256+AES-128) 采集、错误凭据→auth_failed、SSH 密码/host key 未知-匹配-不匹配、
错误密码→auth_failed、配置备份读取 126 行+脱敏、配置变化 diff（HostKey 追加→`+HostKey ********`）、
cisco_ios 命令不支持→cmd_not_supported。

### 测试

- 后端全量 `235 passed`（新增 4 个 classify_error 单测）
- 真实容器链路全部通过（非 mock）

### 未推送

- 本记录对应提交未推送；本地 main 领先 origin/main 14 个提交。
