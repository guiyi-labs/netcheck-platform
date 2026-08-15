#!/bin/sh
# LLDP 实验节点启动脚本（容器内 PID1 执行）。
# 启动 snmpd (AgentX master) + lldpd (AgentX subagent) 并创建 SNMPv3
# authPriv 用户（SHA-256/AES-128，与平台采集器完全一致）。
#
# 用法: sh /lldp-entry.sh   （镜像 entry 或 docker run CMD）
#
# 关键约束（真实 lldpd 1.0.19 / net-snmp 5.9.4 实测）：
#   - lldpd 的 -d 选项【无参数】；写成 `-d 6` 会令 getopt 把 6 当作首个
#     位置参数、停止解析后续选项，导致 -x/-X 被吞掉、AgentX 永远不启用。
#   - AgentX socket 必须放在 lldpd 主进程（非 priv/chroot）可见的全路径，
#     例如 /run/lldpd/agentx.sock；-X unix:... 前缀不会被接受（应直接给
#     路径，且不落在 priv 子进程 chroot 根 /run/lldpd 之外不可见的位置）。
set -e

mkdir -p /run/lldpd /run/snmpd

# snmpd：AgentX master + SNMPv3 用户（SHA-256/AES-128，与平台采集器一致）
cat > /etc/snmp/snmpd.conf <<'SNMP'
master agentx
agentXSocket /run/lldpd/agentx.sock
rocommunity public 127.0.0.1
createUser monitor SHA-256 netcheckauth AES netcheckpriv
rouser monitor priv
sysLocation lab
sysContact test
SNMP

# lldpd：监听 eth*/veth*，PortID 用 ifname，快速 tx 便于老化验证
cat > /etc/lldpd.conf <<'LLDP'
configure system interface pattern eth*,veth*
configure lldp portidsubtype ifname
configure lldp tx-interval 5
configure lldp tx-hold 2
LLDP

# 启动（前台保持，避免 zombie 问题）
snmpd -f -u root &
lldpd -d -x -X /run/lldpd/agentx.sock &

# 等待 AgentX 注册完成（日志出现 "AgentX subagent connected"）
sleep 5

echo "lldp-node ready (snmpd+lldpd agentx @ /run/lldpd/agentx.sock)"

# PID1 行为：保持前台，方便 docker run -d 直接作为 entry
trap 'kill 0 2>/dev/null' EXIT INT TERM
wait