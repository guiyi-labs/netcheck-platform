# Changelog

## [Unreleased]

### Added
- **P1 H3C 适配器真实验证（仿真服务载体）**：`scripts/lab/h3c-sim/`
  载体（OpenSSH 真实传输 + 忠实 Comware V7 CLI 文本 + net-snmp H3C 风格
  sysDescr）+ `h3c-sim-lab.sh` 一键编排（build/up/verify/down）；
  端到端验证 `display version/interface brief/ip routing-table/clock`
  解析（os_version/uptime/接口统计/路由数/system_time）与 SNMPv3 authPriv
  sys facts（sysDescr 含 Comware、sysName）；如实标注仿真服务 ≠ 真实 H3C
  设备（验收记录 `docs/final-delivery/h3c-real-verification.md`；+1 测试
  未识别命令 → cmd_not_supported）。
- **网络自动化增强（厂商适配 + 合规基线）**：
  - **H3C Comware SSH 适配器**（C1）：`display version` / `display interface
    brief` / `display ip routing-table` / `display clock` 解析与命令 allowlist，
    配置备份命令 `display current-configuration`；mock 输出验证、如实标注无
    真实 H3C 设备（+5 测试）。P1 已升级为仿真服务载体端到端验证。
  - **配置合规基线**（C2）：`DeviceConfigSnapshot.is_baseline`（同设备唯一）、
    `POST /api/devices/{id}/configs/{snapshot_id}/baseline`（标记/取消）、
    `GET /api/devices/{id}/configs/compliance`（最新快照 vs 基线行级合规报告，
    pass/warn/fail，粒度如实标注为行级 diff 非语义级；+12 测试）。
  - **协议覆盖文档**（C3）：`docs/protocol-coverage.md` 梳理 SNMPv3/SSH/HTTP/
    LLDP/ICMP/DNS 协议栈、厂商矩阵（linux/cisco_ios/h3c_comware/generic）、
    合规基线说明与扩展点代码索引；README 能力表与交付材料同步。
- **开源门面文件**：新增 `SECURITY.md`（Supported Versions / 漏洞上报与披露时间线
  / threat model 边界 / CI 与供应链控制 / 凭据处理 / 安全贡献清单）与
  `CONTRIBUTING.md`（预置条件 / 快速开始 / 代码规范 / PR 流程 / Issue 上报 /
  安全披露），针对 netcheck 的 SNMP/SSH host-key、AES-256-GCM 凭据加密、
  配置脱敏、告警上报等实际安全点改写；README 顶部已链接两文件。
- **N4.1 LLDP 真实 WALK 验收**：两节点 lldpd 1.0.19 / net-snmp 5.9.4
  Alpine 3.22 容器实验环境，SNMPv3 authPriv 真实 WALK 远端 LLDP-MIB
  证据（`1.0.8802.1.1.2.1.4.1.1` lldpd 布局列 4..12）。
- `scripts/lab/Dockerfile.lldp`：LLDP 实验节点镜像（lldpd AgentX subagent
  + snmpd AgentX master），凭据运行时注入（环境变量覆盖，不固化 Secret）。
- `scripts/lab/lldp-lab.sh`：**可复现 up → verify → down 一键编排**——构建
  镜像、创建 bridge、启动 ll-a/ll-b、veth 互联、等待 LLDP、双向 SNMPv3
  authPriv WALK 断言（sysname 非空 + chassis_subtype=4 + port_subtype=5，
  输出脱敏）、拆除清理（镜像保留）。
- `scripts/lab/lldp-node.sh`：LLDP 节点 entry 脚本（snmpd AgentX
  master + lldpd AgentX subagent），修正 `-d` 无参 getopt 问题、
  socket 路径为 chroot 内可见全路径、快速 tx interval 5s + tx-hold 2；
  凭据支持 `SNMP_USER`/`SNMP_AUTH_KEY`/`SNMP_PRIV_KEY` 环境变量注入。
- `docs/final-delivery/n4-lldp-real-verification.md`：N4.1 真实 WALK
  验收记录，含版本证据、WALK 摘要（脱敏）、一键复现输出、平台全路径
  验证矩阵、mock vs 真实边界复核。

### Changed
- `backend/app/services/snmpv3_collector.py`：
  - `LLDP_REM_COLUMNS` 拆分为 `LLDP_REM_STANDARD_COLUMNS`（标准
    `1.3.7` 列 3..10）和 `LLDP_REM_LLDPD_COLUMNS`（lldpd `1.4.1.1`
    列 4..12，含 port_desc）；`LLDP_REM_LAYOUTS` 列表按优先级探测。
  - `_collect_lldp_via_transport`：支持双布局探测；timeout/
    auth_failed/priv_failed 直接上抛（不再被当作空表）；返回
    `layout`/`unsupported` 诊断字段。
  - 新增 `_parse_lldp_index(full_oid, col_oid)` 共享索引解析函数。

### Fixed
- `-d 6` getopt 陷阱：lldpd 的 `-d` 无参数，写成 `-d 6` 时数字被
  getopt 当作首个位置参数，导致后续 `-x -X` 选项永不被解析；
  AgentX 从未启用。修正为 `lldpd -d -x -X <sock>`。
- 超时边界误分类：`collect_lldp` 对不可达主机现在正确返回
  `status=timeout`（不再返回 `status=ok + neighbors=0`）。
- `lldp-lab.sh` 增强（6 点交叉复核落实）：`lldpcli show neighbors`
  独立确认二层邻居；`_launch` 抽取；双向行走严格断言（任一方失败
  即整体失败）；新增 `recreate` 验证 USM 用户持久化（销毁容器→
  重建→veth 重接→再 WALK；容器进程被 kill 即容器退出，故不用
  docker restart——后者重置 netns 丢 veth）。

### Test
- `backend/tests/test_lldp_collector.py`（新增，9 个）：
  lldpd 布局解析、标准布局回退、索引解析、port_desc 保留、
  time_mark tick 语义、多邻居分组、空表返回、超时上抛、
  列映射字段校验。
- 全量 pytest：257 passed（原 248 + N4.1 新增 9）。

---

## [0.2.0] - 2026-08-15

### Added
- N1/N2/N2.1/N3：SNMPv3/SSH 设备采集、配置备份与版本差异、LLDP
  观测表骨架（mock 单测）——248 passed。