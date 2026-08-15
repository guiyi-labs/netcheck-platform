# N3 真实网络实验与证据 — 验收记录（2026-08-15）

> 环境：Docker bridge 网络 `netcheck-n1` + 服务名 DNS；镜像 `netcheck-n1-lab:latest`
> （`scripts/lab/Dockerfile.lab`，alpine 3.22 + net-snmp 5.9.4-r1 + OpenSSH 10.0_p1）。
> 凭据全部为文档测试值（`monitor`/`netcheckauth`/`netcheckpriv`/`root`/`netcheck123`/`public`）。

## 环境拓扑

```
宿主机 ── docker bridge (netcheck-n1) ── netcheck-n1-lab-router (172.19.0.2)
     │                                      │ snmpd :161/udp (SNMPv3 authPriv)
     │                                      │ sshd  :2222   (root 密码认证)
     └── 采集端（同网络容器 python:3.12-alpine，安装 pysnmp/paramiko，
         或宿主机 venv）执行 scripts/n1_real_verify.py
```

- 复现步骤见 `docs/operations/n1-lab.md`（构建 → 网络 → 冒烟 → 完整验证 → 清理）。
- 版本：alpine 3.22、net-snmp-5.9.4-r1（net-snmp-agent-libs/net-snmp-tools 同版本）、
  openssh-server-10.0_p1-r10、pysnmp 7.1.28、paramiko 5.0.0、cryptography 50.0.0、
  Docker bridge 网络。

## 验收结果（全部通过 ✅）

| 项 | 结果 | 证据 |
|---|---|---|
| 1. SNMPv3 authPriv 采集 | ✅ | sysDescr/sysName/sysUpTime/sysContact/sysLocation + ifTable（3 接口） |
| 1a. 错误凭据分类 | ✅ | `WrongDigest`/`UnknownUserName` → `auth_failed`（N3 修复 classify_error） |
| 2. SSH 采集 | ✅ | hostname/os_type/os_version 真实返回 |
| 2a. host key 未知/匹配/不匹配 | ✅ | 首次 `host_key_unknown` → 登记后 `ok` → 错 fp `host_key_mismatch` |
| 2b. 错误密码 | ✅ | `auth_failed` |
| 3. 配置备份读取 | ✅ | `cat /etc/ssh/sshd_config` 126 行，脱敏输出非空 |
| 4. 配置变化 diff | ✅ | 追加 `HostKey /etc/ssh/ssh_host_ed25519_key` → 重采 → diff `+HostKey ********`（密钥路径未泄漏） |
| 5. 命令不支持 | ✅ | cisco_ios `show running-config` 在 Alpine 不存在 → `cmd_not_supported` |

### 关键输出摘录

```
【1】SNMPv3 authPriv 真实采集 (SHA-256 + AES-128)
  ✅ SNMPv3 采集成功  facts={'sys_descr': 'Linux ad524c1f3bd6 6.8.0-117-generic ...',
                             'sys_uptime': '11958', 'sys_name': 'ad524c1f3bd6', ...}
  ✅ 错误凭据 → auth_failed
【4】N2 配置变化 diff
  diff 新增行数 = 2，变化行示例：
      +# N3 real change marker
      +HostKey ********
  ✅ 配置变化 → 重新采集 → diff 显示变化行（且密钥值被脱敏）
【5】失败场景：命令不支持
  ✅ cisco_ios 命令在 Alpine 上不存在 → cmd_not_supported
结果：全部真实环境验证通过 ✅
```

## N3 过程中修复的代码问题

1. `snmpv3_collector.classify_error`：真实 pysnmp 对认证失败返回 `WrongDigest`/
   `UnknownUserName`/`NotInTimeWindow`/`UnknownEngineID` 等异常对象，其类名不含
   "auth"，原有分类逻辑返回 `error`；新增 `_AUTH_FAILURE_TYPES`/`_PRIV_FAILURE_TYPES`
   识别（含 `AuthenticationError`、`WrongDigest`、`UnknownUserName`、
   `UnknownEngineID`、`NotInTimeWindow`、`PrivError`、`DecryptionError` 等）。
   新增 4 个单测 → 全量 235 passed。
2. `scripts/n1_real_verify.py`：接口字段 `status`→`admin_status`/`oper_status`；
   配置变化验证改为修改真实 sshd_config 并校验脱敏；命令不支持场景改用 cisco_ios。

## mock vs 真实边界（N1/N2 验收矩阵复核）

| 场景 | mock/单测 | 真实容器 |
|---|---|---|
| SNMPv3 authPriv 成功 | ✅ | ✅ |
| SNMPv3 认证失败分类 | ✅（AuthenticationError） | ✅（WrongDigest/UnknownUserName） |
| SSH 密码认证 | ✅ | ✅ |
| host key 未知/匹配/不匹配 | ✅ | ✅ |
| 配置备份读取+脱敏 | ✅ | ✅ |
| 配置变化 → diff 显示变化行 | ✅ | ✅ |
| diff 中密钥值脱敏 | ✅ | ✅ |
| 命令不支持 | ✅ | ✅ |
| SNMP 超时 | ✅（mock） | ✅（RequestTimedOut 场景与错误 priv key 相关） |

## 剩余风险 / 未验证

- 真实 Cisco/Juniper 设备的 `show running-config` 与厂商差异（本实验为 Linux 容器）；
- 海量接口（>64）与高速率计数器回绕的实测（单测覆盖）；
- `AnsweringDevice` 上 SNMP trap/通知、配置回滚（不在 N1/N2 范围）。