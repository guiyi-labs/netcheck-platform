# P1 H3C Comware 适配器真实验证 — 验收记录（仿真服务载体）

> **载体边界（如实标注，不模糊）**：本验收为【仿真服务载体】——容器内
> OpenSSH 提供真实 SSH 传输（真实 host key、真实认证/通道），CLI 交互由
> 自定义仿真脚本按 H3C Comware V7 官方输出样张忠实还原；net-snmp 提供
> H3C 风格 `sysDescr`/`sysName`。验证对象是「采集器 H3C 适配器在真实
> SSH/SNMP 传输链路上的端到端解析」，**不是**「H3C Comware 操作系统兼容性」。
> 有无真实 H3C 设备的差别均如上如实声明，不冒充真机。

## 环境

- 载体镜像：`netcheck-h3c-sim:lab`（`scripts/lab/h3c-sim/Dockerfile`，
  Alpine 3.22 + OpenSSH + net-snmp 5.9.4 + python3 + pysnmp 7.1.28/
  pydantic-settings/sqlalchemy，版本与宿主 venv 对齐）。
- 编排：`scripts/lab/h3c-sim-lab.sh`（build → up → verify → down，一键复现）。
- 拓扑：宿主 SSH 采集经 `-p 3022` 发布端口（TCP 发布正常）；SNMP 采集因
  Docker Desktop for Mac 的 UDP 发布对宿主不可达（实证：容器内 tcpdump
  收不到宿主 UDP 包），在载体容器内以真实 UDP socket 往返容器内 snmpd
  （172.29.0.10:161，veth 层真实报文 + 真实 SNMPv3 authPriv 认证）。
- 凭据全部为文档测试值：`monitor`/`simpass`（SSH）、`monitor`/
  `netcheckauth`/`netcheckpriv`（SNMP）。

## 验收结果（全部通过 ✅）

| 项 | 结果 | 证据 |
|---|---|---|
| 1. SSH 真实采集（vendor=h3c_comware） | ✅ | status=ok，facts 全部解析 |
| 1a. host key 识别 | ✅ | 首次连接 `host_key_unknown` → 采集指纹 → 二次连接 `ok` |
| 1b. `display version` 解析 | ✅ | `os_version=Comware 7.1.070`、`uptime=2 weeks, 1 day, 3 hours, 4 minutes` |
| 1c. `display interface brief` 解析 | ✅ | `interfaces_count=5`、`up_count=4`、`down_count=1` |
| 1d. `display ip routing-table` 解析 | ✅ | `routes_count=3` |
| 1e. `display clock` 解析 | ✅ | `system_time=2026-08-16 09:30:00` |
| 2. SNMPv3 authPriv sys facts | ✅ | `sys_descr=H3C Comware Software, Version 7.1.070...`（含 Comware）、`sys_name=h3c-core-sim`、`sys_uptime`/`sys_contact`/`sys_location` |
| 3. 未识别命令（Comware 风格拒绝） | ✅ | 单测：`% Unrecognized command found...` → `cmd_not_supported`（非 ok） |

## 关键输出摘录（脚本实测）

```
【1】SSH 真实采集（vendor=h3c_comware）
  host key fingerprint: 78ddfd9d4cc4fb9fba5f5f1c5e58c58b
  status: ok
  facts: {'os_version': 'Comware 7.1.070',
          'uptime': '2 weeks, 1 day, 3 hours, 4 minutes',
          'interfaces_count': '5', 'up_count': '4', 'down_count': '1',
          'routes_count': '3', 'system_time': '2026-08-16 09:30:00'}
  --- display version ---
  H3C Comware Software, Version 7.1.070, Release 1118P02
  Copyright (c) 2004-2021 New H3C Technologies Co., Ltd. All rights reserved.
  H3C H3C S5560X-30C-EI uptime is 2 weeks, 1 day, 3 hours, 4 minutes
  --- display interface brief ---
  Interface            Link         Speed   Duplex Type PVID Description
  GE1/0/1              UP           1G      F(a)   A    1    to-core
  GE1/0/2              DOWN         1G      F(a)   A    1    --
  GE1/0/3              UP           10G     F(a)   A    1    to-server
  Vlan-interface1      UP           1G      F(a)   R    --   --
  LoopBack0            UP           1G      F(a)   L    --   --
  --- display ip routing-table ---
  Destination/Mask   Proto   Pre  Cost        NextHop         Interface
  0.0.0.0/0          Static  60   0           10.0.0.254       Vlan-interface1
  10.0.0.0/24        Direct  0    0           10.0.0.1         Vlan-interface1
  192.168.1.0/24     Direct  0    0           192.168.1.1      Vlan-interface1
  --- display clock ---
  2026-08-16 09:30:00
  Friday
  Time Zone : China Standard Time
  ✅ SSH H3C 解析断言全部通过

【2】SNMPv3 authPriv sys facts（平台采集器 collect_snmpv3）
  status: ok
  facts: {'sys_descr': 'H3C Comware Software, Version 7.1.070, Release 1118P02',
          'sys_uptime': '652', 'sys_name': 'h3c-core-sim',
          'sys_contact': 'p1-verification', 'sys_location': 'sim-lab'}
  ✅ SNMP H3C sysDescr/sysName 断言通过
```

## 结论

H3C Comware 适配器（ssh 采集 `display` 系列 + SNMP sys facts）在真实
SSH/SNMPv3 传输链路上端到端解析全部通过（仿真服务载体）。测试基线
274 → 275 passed（+1：未识别命令 → cmd_not_supported）。

## 边界与剩余风险

- **仿真载体**：CLI 文本为按 H3C 官方文档样张忠实还原的仿真输出，非真实
  Comware OS；真实 H3C 设备上的输出格式细节（版本号、界面名、路由统计行）
  可能与此有差异，若接入真实设备需按实机输出复核适配器解析。
- **SNMP 采集进程位置**：Docker Desktop for Mac UDP 发布对宿主不可达，采集
  器在载体容器内执行（真实 UDP 往返容器内 snmpd）；联网环境可使用宿主侧
  UDP 发布（已保留 `PUBLISH_SNMP_PORT` 端口发布配置）。
- 复现：`scripts/lab/h3c-sim-lab.sh`（需 Docker；镜像构建需拉取 alpine 与
  pysnmp 依赖，网络不稳定时重试）。
