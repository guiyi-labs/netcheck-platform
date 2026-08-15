#!/usr/bin/env bash
#
# N4.1 LLDP 真实 WALK 可复现编排：up → verify → down
#
# 在两节点 lldpd 容器上：
#   1) up     —— 构建镜像（若缺失）+ 创建 bridge + 启动 ll-a/ll-b + veth 互联
#   2) verify —— 双向 SNMPv3 authPriv WALK lldpRem（lldpd 布局 1.4.1.1），
#                断言 chassis_subtype=4 / port_subtype=5 / sysname 非空；
#                输出脱敏（MAC 打码、sysname 截断）
#   3) down   —— 删除容器与 bridge（镜像保留）
#
# 用法:
#   scripts/lab/lldp-lab.sh            # 全流程
#   scripts/lab/lldp-lab.sh up         # 仅 up（调试）
#   scripts/lab/lldp-lab.sh verify     # 仅 verify（要求已 up）
#   scripts/lab/lldp-lab.sh down       # 仅 down
#
# 环境变量（可覆盖）:
#   LL_NET / LL_SUBNET / LL_A_IP / LL_B_IP
#   SNMP_USER / SNMP_AUTH_KEY / SNMP_PRIV_KEY（运行时注入，默认文档测试值）
set -euo pipefail

LL_NET="${LL_NET:-netcheck-ll}"
LL_SUBNET="${LL_SUBNET:-172.19.0.0/16}"
LL_A_IP="${LL_A_IP:-172.19.0.2}"
LL_B_IP="${LL_B_IP:-172.19.0.3}"
LL_IMAGE="${LL_IMAGE:-netcheck-ll-node:lab}"
LL_WAIT="${LL_WAIT:-25}"   # LLDP 发现等待秒数

SNMP_USER="${SNMP_USER:-monitor}"
SNMP_AUTH_KEY="${SNMP_AUTH_KEY:-netcheckauth}"
SNMP_PRIV_KEY="${SNMP_PRIV_KEY:-netcheckpriv}"

_action="${1:-all}"

# ---------- helpers ----------

log() { printf '[lldp-lab] %s\n' "$*"; }

# 脱敏工具：Hex-STRING 的 MAC 字节统一打码；容器 hostname（随机 ID）截断。
mask() {
  sed -E \
    -e 's/([0-9A-F]{2} ){5}[0-9A-F]{2}[[:space:]]*/XX:XX:XX:XX:XX:XX /' \
    -e 's/0x[0-9a-f]{12}/0x:MASKED:/g' \
    -e 's/"[0-9a-f]{12}"/"<hostname>"/g' \
    "$@"
}

# 容器内 SNMPv3 authPriv WALK（net-snmp 5.9.4 支持 SHA-256）
node_walk() {
  local name="$1" oid="$2"
  docker exec "$name" snmpwalk -v3 -l authPriv \
    -u "$SNMP_USER" -a SHA-256 -A "$SNMP_AUTH_KEY" \
    -x AES -X "$SNMP_PRIV_KEY" 127.0.0.1 "$oid" 2>&1
}

# ---------- up ----------

cmd_up() {
  if ! docker image inspect "$LL_IMAGE" >/dev/null 2>&1; then
    log "构建镜像 $LL_IMAGE ..."
    docker build -q -f scripts/lab/Dockerfile.lldp \
      -t "$LL_IMAGE" scripts/lab/
  else
    log "镜像 $LL_IMAGE 已存在，跳过构建"
  fi

  if ! docker network inspect "$LL_NET" >/dev/null 2>&1; then
    log "创建 bridge $LL_NET ($LL_SUBNET)"
    docker network create --subnet "$LL_SUBNET" "$LL_NET"
  fi

  log "启动 ll-a / ll-b"
  docker rm -f ll-a ll-b >/dev/null 2>&1 || true
  docker run -d --name ll-a --network "$LL_NET" --ip "$LL_A_IP" \
    "$LL_IMAGE" sh /lldp-entry.sh >/dev/null
  docker run -d --name ll-b --network "$LL_NET" --ip "$LL_B_IP" \
    "$LL_IMAGE" sh /lldp-entry.sh >/dev/null

  PA="$(docker inspect -f '{{.State.Pid}}' ll-a)"
  PB="$(docker inspect -f '{{.State.Pid}}' ll-b)"
  log "veth 互联 (ll-a:$PA ↔ ll-b:$PB)"
  docker run --rm --privileged --pid=host --net=host alpine:3.22 sh -c "
    apk add --no-cache iproute2 >/dev/null 2>&1
    ip link add vethB2 type veth peer name vethA2
    ip link set vethB2 netns $PA
    ip link set vethA2 netns $PB
    nsenter -t $PA -n ip link set vethB2 up
    nsenter -t $PB -n ip link set vethA2 up
  "

  log "等待 LLDP 发现（~${LL_WAIT}s）..."
  sleep "$LL_WAIT"
}

# ---------- verify ----------

cmd_verify() {
  local ok=1
  for pair in "ll-a:ll-b" "ll-b:ll-a"; do
    local from="${pair%%:*}" expect_name="${pair##*:}"
    log "=== $from view (expect $expect_name) ==="
    # sysname 列（9）
    local sys
    sys="$(node_walk "$from" 1.0.8802.1.1.2.1.4.1.1.9 | mask)"
    echo "$sys"
    if ! echo "$sys" | grep -q 'STRING:'; then
      log "FAIL: $from 未发现任何邻居"
      ok=0
    fi
    # chassis_subtype（列 4）与 port_subtype（列 6）：断言 =4 / =5
    local c4 c6
    c4="$(node_walk "$from" 1.0.8802.1.1.2.1.4.1.1.4 | mask)"
    c6="$(node_walk "$from" 1.0.8802.1.1.2.1.4.1.1.6 | mask)"
    echo "$c4" | grep -qE 'INTEGER: 4' || { log "FAIL: chassis_subtype != 4"; ok=0; }
    echo "$c6" | grep -qE 'INTEGER: 5' || { log "FAIL: port_subtype != 5"; ok=0; }
    echo "$c4"
    echo "$c6"
  done
  if [ "$ok" -eq 1 ]; then
    log "VERIFY OK：双向 SNMPv3 authPriv LLDP WALK 通过（lldpd 布局 1.4.1.1）"
  else
    log "VERIFY FAILED"
    return 1
  fi
}

# ---------- down ----------

cmd_down() {
  log "remove ll-a / ll-b and bridge $LL_NET (image kept)"
  docker rm -f ll-a ll-b >/dev/null 2>&1 || true
  docker network rm "$LL_NET" >/dev/null 2>&1 || true
}

# ---------- dispatch ----------

case "$_action" in
  all)   cmd_up; cmd_verify; cmd_down ;;
  up)    cmd_up ;;
  verify) cmd_verify ;;
  down)  cmd_down ;;
  *) echo "用法: $0 [all|up|verify|down]" >&2; exit 2 ;;
esac

log "done ($_action)"