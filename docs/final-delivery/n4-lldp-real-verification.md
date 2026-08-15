# N4.1 LLDP 真实 SNMPv3 WALK 验证记录（2026-08-15）

> 本页记录 **lldpd AgentX 真实 LLDP-MIB 的 SNMPv3 authPriv WALK 验收证据**，
> 以及平台采集器对真实布局的适配与全链路验证结论。
> 环境为两节点 lldpd 容器（Alpine 3.22），**不是任何厂商实机**。

## 1. 实验环境与版本（可复现）

| 组件 | 值 |
|---|---|
| 容器镜像 | `netcheck-ll-node:final`（Alpine 3.22.5, aarch64） |
| lldpd | lldpd-1.0.19-r0（Alpine 官方包，编译含 net-snmp AgentX 支持） |
| net-snmp | 5.9.4-r1（snmpd 作 AgentX master，lldpd 作 AgentX subagent） |
| 网络 | docker bridge `netcheck-ll` 172.19.0.0/16；ll-a=172.19.0.2、ll-b=172.19.0.3；veth 对 `vethB2`(ll-a) ↔ `vethA2`(ll-b) |
| 平台后端 | `ll-api`(172.19.0.4)，FastAPI + SQLite `/tmp/n4_1.db`，backend bind-mount 最新代码 |
| SNMPv3 凭据 | `monitor` / SHA-256 `netcheckauth` / AES-128 `netcheckpriv`（文档测试值） |
| 数据采集 | `snmpwalk -v3 -l authPriv` 于容器内（net-snmp 5.9.4 支持 SHA-256） |

复现脚本：`scripts/lab/lldp-node.sh`（容器 entry）；veth 接线用 privileged helper
`docker run --rm --privileged --pid=host --net=host alpine:3.22` + `nsenter`。

### 关键启动约束（真实 lldpd 实测，源码 + 运行确认）

1. **`lldpd -d` 无参数**。写成 `-d 6`（或任何数字）时，getopt 把 `6` 当首个
   位置参数、停止解析后续选项 → `-x -X` 被吞 → AgentX 永不启用（日志无
   "enable SNMP subagent"，WALK 无数据）。正确写法：`lldpd -d -x -X <sock>`。
2. AgentX socket 用 **lldpd 主进程可见的全路径**（`/run/lldpd/agentx.sock`），
   不要加 `unix:` 前缀；也不要把 socket 放在 priv 子进程 chroot（`/run/lldpd`）
   之外不可见的位置（否则日志报 `cannot connect to /agentx.sock: No such file
   or directory`）。

## 2. 真实 WALK 证据

下面两个方向的远端邻居表（LLDP-MIB 真实布局）是 **lldpd 1.0.19 通过
AgentX 注册在 `1.0.8802.1.1.2.1.4.1.1` 的 lldpRem 变体**（非标准 `1.3.7`）。
索引 = `time_mark.local_port.lldp_index`。MAC 值与容器 ID 用占位符脱敏。

### ll-a 视角（看到 ll-b，vethB2 ifindex=1173）

```
iso.0.8802.1.1.2.1.4.1.1.4.150100.1173.1 = INTEGER: 4        # chassis_subtype=macAddress
iso.0.8802.1.1.2.1.4.1.1.5.150100.1173.1 = Hex-STRING: 11 22 33 44 55 66   # chassis_id
iso.0.8802.1.1.2.1.4.1.1.6.150100.1173.1 = INTEGER: 5        # port_subtype=ifName
iso.0.8802.1.1.2.1.4.1.1.7.150100.1173.1 = STRING: "vethA2"  # port_id
iso.0.8802.1.1.2.1.4.1.1.8.150100.1173.1 = STRING: "vethA2"  # port_desc
iso.0.8802.1.1.2.1.4.1.1.9.150100.1173.1 = STRING: "<ll-b-hostname>"  # sysname
iso.0.8802.1.1.2.1.4.1.1.10.150100.1173.1 = STRING: "Alpine Linux v3.22 ..."  # sysdesc
iso.0.8802.1.1.2.1.4.1.1.11.150100.1173.1 = STRING: "9"     # sys_cap_supported
iso.0.8802.1.1.2.1.4.1.1.12.150100.1173.1 = Hex-STRING: 08   # sys_cap_enabled
```

### ll-b 视角（对称，vethA2 ifindex=1172）

```
iso.0.8802.1.1.2.1.4.1.1.4.150100.1172.1 = INTEGER: 4
iso.0.8802.1.1.2.1.4.1.1.5.150100.1172.1 = Hex-STRING: AA BB CC DD EE FF
iso.0.8802.1.1.2.1.4.1.1.6.150100.1172.1 = INTEGER: 5
iso.0.8802.1.1.2.1.4.1.1.7.150100.1172.1 = STRING: "vethB2"
iso.0.8802.1.1.2.1.4.1.1.9.150100.1172.1 = STRING: "<ll-a-hostname>"
```

### 索引语义（验收关键点）

- 索引三段 = `time_mark.local_port.lldp_index`；`time_mark` 是 **lldpd 的
  TimeFilter tick**（记录本次邻居信息刷新的 sysUpTime 时刻），**不是**
  墙钟/Unix 时间戳。
- 验证：邻居不变时 time_mark 随 LLDP tx 周期变化（2500 → 5500 → …）；它
  不随当前 sysUpTime 单调递增（stable 时保持在最后一次变更时刻附近）。
- 采集器因此**原样保留 tick**，不做时间换算，DB 记录 `lldp_time_mark`。

## 3. 采集器布局适配（本次变更）

`backend/app/services/snmpv3_collector.py`：

- **新增 lldpd 真实布局** `LLDP_REM_LLDPD_COLUMNS`：
  列 4..12 映射到 chassis_subtype/chassis_id/port_subtype/port_id/port_desc/
  sysname/sysdesc/sys_cap_supported/sys_cap_enabled，前缀 `1.0.8802.1.1.2.1.4.1.1`。
- **保留标准布局** `LLDP_REM_STANDARD_COLUMNS`（`1.0.8802.1.1.2.1.3.7` 列 3..10），
  作为 lldpRemTable 回退探测。
- `_collect_lldp_via_transport` 按 `LLDP_REM_LAYOUTS` 探测：先 lldpd、后标准；
  取有数据的布局聚合。索引统一 `_parse_lldp_index` 解析三段。
- `port_desc`（lldpd 特有列 8）被保留进邻居 dict。
- 失败分类：WALK timeout/auth_failed/priv_failed **直接上抛**（不当作空表）；
  两种布局都无数据 → `ok + 空邻居`（unsupported=no_llpd_data）。
- 新增单测 `backend/tests/test_lldp_collector.py`（9 个）。

## 4. 平台全路径验证（ll-api 实测）

设备与凭据通过 API 创建：ll-a(172.19.0.2)、ll-b(172.19.0.3)，凭据
`monitor`/SHA-256/AES-128 与实验一致。

| 验收项 | 结果 | 证据 |
|---|---|---|
| POST /lldp/collect | ✅ | ll-a: `{"status":"ok","neighbors":1,"stored":1}`；ll-b 对称 |
| GET /api/devices/{id}/lldp | ✅ | ll-a 行：`remote_sysname=<ll-b>`, `remote_chassis_id=0x…`, `remote_port_subtype=5`, `remote_port_id=vethA2`, `chassis_subtype=4` |
| DB 持久化（upsert） | ✅ | `lldp_observations` 表，`first_seen`/`last_seen` 写入 |
| 同邻居重采幂等 | ✅ | 连续 3 次 collect → 仍 1 条活动行，`last_seen` 刷新、无重复行 |
| 邻居变化（新写旧停） | ✅ | ll-b 重启后 port-id 由 ifname 变 MAC(0x…ee3f8e23b006)：新行 id=3 写入；恢复 ifname 后旧 MAC 行 id=3 停止刷新、id=1 持续更新；**无虚构删除** |
| 失败边界 · 坏凭据 | ✅ | `status=error`（SNMPv3 认证失败，非成功/非健康） |
| 失败边界 · 超时 | ✅ | 不可达主机(192.0.2.250)：`status=timeout`, error=`LLDP WALK timeout`（本次修复后正确分类） |
| 失败边界 · 无 LLDP MIB | ✅ | 空表 → `status=ok, neighbors=0`（unsupported） |
| devices.html LLDP 视图 | ✅ | devices.js `showLldpNeighbors` 消费字段与 GET 返回值完全匹配（端口号/sysname/port_id/chassis_id/timestamp），无需改前端 |

## 5. mock vs 真实边界复核

| 场景 | mock/单测 | 真实 lldpd 容器 |
|---|---|---|
| lldpd 布局（1.4.1.1 列 4..12）解析 | ✅ 8 个单测 | ✅ 双方向 WALK |
| 标准布局（1.3.7 列 3..10）回退 | ✅ | ⏳ 未布标准 MIB（单测覆盖） |
| 索引 time_mark.local_port.lldp_index | ✅ | ✅ |
| time_mark 为 tick 非时间戳 | ✅ | ✅（2500→5500 变化） |
| 邻居变化/老化 | ✅（无虚构删除单测） | ✅（veth down → 0 邻居；恢复 → 更新） |
| 超时分类 | ✅ | ✅（192.0.2.250） |
| 坏凭据 | ✅ | ✅ |
| LLDP-MIB 不存在 | ✅（空表 ok） | ✅（空表 ok） |

## 6. 剩余风险 / 未验证（明确边界）

- **非 lldpd 平台的 LLDP-MIB 布局**：本实验只验证了 lldpd 1.0.19 与标准
  lldpRemTable 两个布局；Cisco/Juniper/FRR 等厂商实现的 OID/索引/类型差异
  **未做任何实机或仿真验证**（N4.1 范围外，不做多厂商归一化）。
- 大量邻居（>64）与表行数上限的实测（单测覆盖 max_rows 截断）。
- `addr`/`addr_type`（管理地址列）未在 lldpd 布局中被采集（列 13+ 不在
  1.4.1.1 骨干列内），当前仅 sysname/sysdesc/port/chassis 等核心字段入库。
- 前端为静态页面，未做浏览器自动化截图（API 契约已逐字段比对）。

## 7. 测试统计

- 全量 pytest：**257 passed**（本次新增 9 个 LLDP 采集单测；
  此前基线 248 → 251 → 257）。