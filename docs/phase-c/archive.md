# 阶段 C 完成归档：真实网络能力（容器适配 / Traceroute / Nmap / SNMP）

> 完成日期：2026-08-14
> 目标：把平台从"模拟演示数据"推向"真实局域网可用"。
> 测试：`88 passed`（全量回归通过）。

## 1. C1 容器网络适配验证

- 验证并文档化 `docker-compose.yml` 的 `cap_add: NET_RAW`（容器内 ping 需要 raw socket）与
  `backend/Dockerfile` 的 `iputils-ping` 安装。
- **修复** `frontend/Dockerfile`：`COPY *.html` 补齐 audit/users/asset-changes 等新增页面，
  避免容器内 404。
- 新增 `scripts/verify-container-network.sh`：五步自检（ping 命令、raw socket、DNS、TCP、HTTP），
  定位容器内巡检链路问题。
- 文档 `docs/phase-c/container-network.md`：能力原理、自检方法、已知限制与排障表。

## 2. C2 Traceroute 诊断

- 新增 `app/services/traceroute.py`：调用系统 traceroute/tracert 并解析逐跳路径
  （兼容 BSD `host (ip)` 与 Linux `-n` 两种输出格式），区分 `completed / timeout / failed`；
  超时跳（`*`）保留为 `None` RTT。
- 新增 `POST /api/diagnostics/traceroute`（`target`、`max_hops`、`wait`），需登录。
- 前端新增「网络诊断」页（`diag.html` / `js/diag.js`，顶部导航入口）：输入目标/IP，
  展示逐跳表格（跳数、主机、IP、三条 RTT）。
- 测试 `test_traceroute.py` 7 例；本机实测 `traceroute 127.0.0.1` 返回 1 跳 completed。

## 3. C3 Nmap 增强发现（可选依赖）

- 新增 `app/services/nmap_discovery.py`：`nmap_ping_sweep`（`nmap -sn` 批量主机发现）与
  `nmap_port_scan`（`nmap -sT -Pn -p --open` 端口扫描）。返回 `None` 表示 nmap 缺失/失败，
  返回空集/空表表示正常但无结果。
- `run_discovery_scan` 优先尝试 nmap（批量更快），无 nmap 时回落原 socket 探测路径，
  保持既有行为完全向后兼容。
- 测试 `test_nmap_snmp.py`：扫描解析、缺失回落、异常回落、端口解析。

## 4. C4 SNMP 基础采集（可选依赖）

- 新增 `app/services/snmp_basic.py`：基于 net-snmp 命令行（snmpget/snmpwalk）只读采集；
  预置 SYSTEM/接口常用 OID；`snmp_get / snmp_walk / collect_device_basics`；工具缺失或
  目标无响应返回 `None`，调用方优雅降级。
- 测试 `test_nmap_snmp.py`：GET/WALK 解析、工具缺失回落、超时回落。

## 5. LAN 验证脚本

- 新增 `scripts/verify-lan.sh`：对真实局域网目标逐项跑 ping / TCP / traceroute / HTTP /
  SNMP(可选) / nmap(可选)，输出 PASS/FAIL，供演示现场演示与验收。

## 6. 验证结果

```text
88 passed in 6.65s
```

新增测试文件：`test_traceroute.py`（7）、`test_nmap_snmp.py`（10）。

## 7. 已知边界与后续

- SNMP 仅 v2c community 只读；如需 v3 认证可扩展 `snmpget -u/-A/-X` 参数。
- Nmap/SNMP 依赖目标机环境安装命令；容器镜像未内置，需运行于宿主机或以 sidecar 注入。
- Traceroute 目标是域名时依赖容器 DNS；跨网段路径探测受中间设备策略影响。
- C 阶段未做分布式探测节点（多 Agent 从不同位置发起），如需要可放入 D4 一起规划。