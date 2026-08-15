# N1/N2 实验环境（containerlab / Docker lab 路由器）

本页说明如何可复现地搭建 N1（SNMPv3 + SSH 只读采集）与 N2（配置备份/diff）的
真实环境实验，并把证据归档到 Obsidian（16 N2.1 归档 → N3 准入）。

> 安全说明：`scripts/lab/Dockerfile.lab` 内所有凭据均为**文档测试值**
> （`netcheckauth` / `netcheckpriv` / `netcheck123` / `public`），只用于本地实验，
> 无生产价值。可用 `--build-arg` 覆盖，避免在镜像中固化自定义口令。
> 真实设备请勿使用本测试凭据。

## 1. 方式 A：self-contained Docker lab 路由器（推荐，兼容 colima/无 UDP 发布）

macOS colima 的 UDP 端口发布不可用（`-p 16111:161/udp` 会超时），因此统一使用
**Docker bridge 网络 + 服务名 DNS**，采集端与被测容器同网络通信。

```bash
# ① 构建镜像（凭据默认 = 文档测试值；可 --build-arg 覆盖）
docker build -f scripts/lab/Dockerfile.lab -t netcheck-n1-lab:latest scripts/lab/

# ② 隔离网络 + 启动实验路由器
docker network create netcheck-n1 2>/dev/null || true
docker run -d --name netcheck-n1-lab-router --network netcheck-n1 \
  --cap-add NET_RAW --cap-add NET_ADMIN \
  netcheck-n1-lab:latest

# ③ 容器内冒烟验证（证明镜像本身可用）
docker exec netcheck-n1-lab-router snmpget -v3 -l authPriv \
  -u monitor -a SHA-256 -A netcheckauth -x AES -X netcheckpriv \
  127.0.0.1 1.3.6.1.2.1.1.1.0
docker exec netcheck-n1-lab-router ssh -p 2222 root@127.0.0.1 hostname
# 又或宿主机验证（TCP 2222 可发布，UDP 不行）
docker run --rm --network netcheck-n1 alpine sh -c \
  "apk add --no-cache net-snmp-tools openssh-client -q \
   && snmpget -v3 -l authPriv -u monitor -a SHA-256 -A netcheckauth \
      -x AES -X netcheckpriv netcheck-n1-lab-router 1.3.6.1.2.1.1.1.0"

# ④ 运行完整验证（采集端容器需要 pysnmp/paramiko/cryptography）
docker run --rm --network netcheck-n1 \
  -v "$PWD/backend:/app/backend" -v "$PWD/scripts:/app/scripts" -w /app \
  -e N1_ROUTER_HOST=netcheck-n1-lab-router \
  -e N1_SNMP_PORT=161 -e N1_SSH_PORT=2222 \
  python:3.12-alpine sh -c "apk add --no-cache py3-pip -q \
    && pip install --break-system-packages -q pysnmp==7.1.28 paramiko==5.0.0 cryptography==50.0.0 \
    && PYTHONPATH=/app/backend python3 /app/scripts/n1_real_verify.py"

# ⑤ 清理
docker rm -f netcheck-n1-lab-router 2>/dev/null || true
docker network rm netcheck-n1 2>/dev/null || true
```

对应验证脚本：`scripts/n1_real_verify.py`（SNMPv3 采集 + 错误凭据、SSH host key
未知/匹配/不匹配、错误密码、N2 配置备份脱敏）。

## 2. 方式 B：containerlab（如已安装）

`./scripts/n1-lab.sh lab-up` 会检测 containerlab；若存在则生成 `scripts/n1-lab.yml`
（FRRouting v8.4.0 双节点），并部署。采集端仍建议与实验网络同网通信。

## 3. 方式 C：真实设备

若已有支持 SNMPv3 authPriv + SSH 只读的路由器/交换机：

1. 在前端 `http://localhost:8080/devices.html` 创建凭据（SNMPv3 authPriv + SSH）；
2. 添加设备，绑定凭据，触发采集；
3. 配置备份：打开设备行「配置快照」→ 采集配置快照 → 查看脱敏全文与 diff。

## 4. 归档要求（N3 准入）

- 记录：容器镜像 tag、net-snmp/openssh 版本、采集输出（脱敏）、截图、日期；
- 全部实验凭据为文档测试值且已在 README/本页标注；
- 真实链路验证通过后更新 Obsidian 16 N2.1 归档的 N3 准入勾选；
- 实验产生的可提交文件不得含默认 root 口令、SNMP community、认证/加密密钥之外的
  任何真实凭据（`--build-arg` 注入的凭据不得提交）。