#!/bin/sh
# H3C 仿真节点 entry：启动 sshd + snmpd，设置 H3C 风格 sysDescr/sysName。
set -e

# H3C 风格 sysName / sysDescr（可环境变量注入；snmpd 需在启动前写入）
SYSNAME="${H3C_SYSNAME:-h3c-core-sim}"
SYS_VERSION="${H3C_VERSION:-H3C Comware Software, Version 7.1.070, Release 1118P02}"
cat > /etc/snmp/snmpd.conf <<SNMP
createUser monitor SHA-256 netcheckauth AES netcheckpriv
rouser monitor priv
sysLocation sim-lab
sysContact p1-verification
sysName ${SYSNAME}
sysDescr ${SYS_VERSION}
SNMP

# 启动 SNMP（UDP 161）+ SSH（22/2222）
snmpd -f -u root &
/usr/sbin/sshd -D &

trap 'kill 0 2>/dev/null' EXIT INT TERM
wait