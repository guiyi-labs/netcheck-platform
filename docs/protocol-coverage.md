# NetCheck 协议覆盖与厂商适配说明

> 本文梳理 NetCheck 当前支持的采集/探测协议栈、厂商适配器矩阵与可扩展点，
> 突出「平台化」能力：新增协议或厂商不需要改动平台骨架，只需登记适配器。

## 1. 协议栈总览

| 协议 | 用途 | 传输/安全 | 状态 |
|---|---|---|---|
| **SNMPv3** | 资产事实、接口指标趋势、LLDP 邻接发现 | UDP，authPriv（SHA-256 认证 + AES-128 加密），USM 用户，OID allowlist | ✅ 真实验证（N1/N4/LLDP 容器 WALK） |
| **SSH** | 只读采集（厂商命令 + 解析）、配置备份 | TCP，host-key 指纹校验（unknown/mismatch 分类），命令 allowlist | ✅ 真实验证（N3 容器） |
| **HTTP(S)** | 服务存活/状态码/慢响应探测 | TCP 443/80 | ✅ 平台巡检链路 |
| **LLDP (SNMP sub-agent)** | 邻居发现：远端邻居表真实布局 | SNMPv3 authPriv over AgentX（lldpd sub-agent / snmpd master） | ✅ 真实验证（N4.1 双节点 lldpd 双向 WALK） |
| **ICMP (Ping)** | 网络可达性 | 单包探测（命令拼接受控） | ✅ 平台巡检链路 |
| **DNS** | 域名解析成功/延迟 | UDP/TCP 53 | ✅ 平台巡检链路 |

边界说明：

- **SNMP 仅 GET/BULK WALK，不写**；OID 白名单
  （`backend/app/models/device.py` 的 `OID_ALLOWLIST`）。
- **SSH 只读**：不申请 PTY、不执行 allowlist 之外命令、不做配置下发/回滚。
- **LLDP 采集采用双布局探测**：lldpd 真实布局
  `1.0.8802.1.1.2.1.4.1.1`（列 4..12）优先，标准布局
  `1.0.8802.1.1.2.1.3.7`（列 3..10）兜底，兼容不同 SNMP agent 实现。

## 2. 厂商适配器矩阵

SSH 只读采集通过「命令 allowlist + 输出解析器」适配不同厂商 CLI：

| 厂商适配器 | 平台 | 采集命令示例 | 配置备份命令 | 解析字段 | 验证状态 |
|---|---|---|---|---|---|
| `linux` | Linux 主机 | `hostname -f` / `uname -a` / `ip -o link show` / `uptime` / `free -h` / `df -h` | `cat /etc/network/interfaces` 等 | hostname, os_version, uptime, mem_total/free | ✅ 容器验证（N3） |
| `cisco_ios` | Cisco IOS | `show version` / `show ip interface brief` / `show ip route` / `show clock` | `show running-config` | os_version, uptime, interfaces_count | ✅ 容器验证（N3） |
| `h3c_comware` | H3C Comware | `display version` / `display interface brief` / `display ip routing-table` / `display clock` | `display current-configuration` | os_version, uptime, interfaces_count, up/down_count, routes_count, system_time | ✅ 仿真服务载体端到端验证（真实 SSH/SNMP 传输；无真实 H3C 设备） |
| `generic` | 兜底 | `hostname` / `uname -a` | `hostname` | —（无结构化解析） | — |

> **如实标注**：`h3c_comware` 适配器按真实 Comware CLI 输出格式编写；P1 已通过
> **仿真服务载体**完成端到端真实验证（真实 SSH/SNMP 传输链路，见
> `docs/final-delivery/h3c-real-verification.md`）。载体为 OpenSSH + 忠实
> Comware V7 文本 + net-snmp H3C 风格 sysDescr，**非真实 H3C 设备**；真实
> 设备上的输出格式细节需按实机复核。

## 3. 配置合规基线（N2.2，行级 diff 粒度）

轻量合规闭环（复用既有配置快照 + 行级 diff，不重复造轮子）：

1. `POST /api/devices/{id}/configs/{snapshot_id}/baseline` — 标记某快照为基线
   （同设备唯一，后标覆盖先标；`enabled=false` 取消）。
2. `GET /api/devices/{id}/configs/compliance` — 最新快照 vs 基线，返回结构化报告：
   `baseline_id/collected_at`、`current_id/collected_at`、`total_rules`、
   `passed`、`failed`、`changed_lines`（行级变更）、`status`（pass/warn/fail）。

**粒度如实标注**：合规判定基于配置**行级 diff**（内容变化即不合规项），
非语义级规则（如「某命令必须存在」「密码策略」等语义检查需设备知识，
不在当前范围）。阈值：`changed_lines=0 → pass`；`≤10 → warn`；`>10 → fail`。

## 4. 可扩展点（新增厂商/协议）

新增一个 SSH 厂商适配器只需 4 处登记（全部集中，不改平台骨架）：

| 位置 | 登记内容 |
|---|---|
| `backend/app/models/device.py` | `SSH_VENDOR_ADAPTERS` 加厂商名；`SSH_READONLY_COMMANDS[厂商]` 加只读命令；`CONFIG_READ_COMMANDS[厂商]` 加配置备份命令 |
| `backend/app/services/ssh_collector.py` | 新增 `_parse_<厂商>_output(cmd, output) -> dict`，注册进 `PARSERS` |
| `backend/tests/test_ssh_collector.py` | 追加解析单测 + 端到端 mock 采集测试 |

新增 SNMP 采集 OID：追加到 `OID_ALLOWLIST`（sys / if / lldp 分组），
采集器按白名单 WALK。新增 LLDP 布局：在 `LLDP_REM_LAYOUTS` 追加列映射。

协议/数据出口（告警通知、报告导出）均为可选关闭配置（默认关闭），
见 `backend/app/core/config.py` 的 `notification_*` / `webhook_*` / `ai_*`。

## 5. 验证边界汇总

| 能力 | 验证方式 | 证据位置 |
|---|---|---|
| SNMPv3 采集/LLDP WALK | 双节点 lldpd 容器真实验证 | `docs/final-delivery/n4-lldp-real-verification.md`，`scripts/lab/lldp-lab.sh` |
| SSH 采集（linux/cisco_ios） | N3 容器真实验证 | `docs/final-delivery/n3-real-verification.md` |
| SSH 采集（h3c_comware） | 仿真服务载体端到端（真实 SSH 传输 + 忠实 Comware 文本） | `docs/final-delivery/h3c-real-verification.md`，`scripts/lab/h3c-sim-lab.sh` |
| 配置备份/脱敏/diff/合规基线 | 单元测试（mock DB） | `backend/tests/test_config_backup.py`、`test_compliance.py` |
| 平台巡检（HTTP/Ping/DNS） | 内置演示网络（Compose） | `docs/final-delivery/` 测试报告 |