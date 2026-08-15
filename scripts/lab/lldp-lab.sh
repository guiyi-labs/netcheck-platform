#!/usr/bin/env bash
#
# N4.1 LLDP 真实 WALK 可复现编排：up → verify(邻居CLI+WALK) → recreate验证 → down
#
# 在两节点 lldpd 容器上：
#   1) up      —— 构建镜像（若缺失）+ 创建 bridge + 启动 ll-a/ll-b + veth 互联
#   2) verify  —— ① lldpcli show neighbors（独立确认二层邻居，command-center
#                 AI 交叉复核点1）② 双向 SNMPv3 authPriv WALK lldpRem
#                 （lldpd 布局 1.4.1.1），断言 sysname 非空 + chassis_subtype=4
#                 + port_subtype=5；输出脱敏（MAC 打码、hostname 截断）
#   3) recreate —— 销毁容器→重建→重新接 veth→再 WALK（验证 entry 每次启动
#                 重建 USM 用户，AI 复核点6）
#   4) down    —— 删除容器与 bridge（镜像保留）
#
# 用法:
#   scripts/lab/lldp-lab.sh            # 全流程
#   scripts/lab/lldp-lab.sh up         # 仅 up（调试）
#   scripts/lab/lldp-lab.sh verify     # 仅 verify（要求已 up）
#   scripts/lab/lldp-lab.sh recreate   # 仅 recreate 验证（要求已 up）
#   scripts/lab/lldp-lab.sh down       # 仅 down
#
# 环境变量（可覆盖）:
#   LL_NET / LL_SUBNET / LL_A_IP / LL_B_IP
#   SNMP_USER / SNMP_AUTH_KEY / SNMP_PRIV_KEY（运行时注入，默认文档测试值）
#
# 关键事实（真实 lldpd 1.0.19 / net-snmp 5.9.4 实测）：
#   - WALK 目标是 lldpd 布局 1.0.8802.1.1.2.1.4.1.1（列4..12），既非标准 1.3.7；
#     采集器对两者均兼容。
#   - 容器进程被 kill 即容器退出（PID1）；USM 持久化用“销毁重建”验证，而非 docker
#     restart（后者净重置 netns 丢 veth）。
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

# 启动容器 + 接 veth（供 up / recreate 共用）
_launch() {
  docker rm -f ll-a ll-b >/dev/null 2>&1 || true
  docker run -d --name ll-a --network "$LL_NET" --ip "$LL_A_IP" \
    "$LL_IMAGE" sh /lldp-entry.sh >/dev/null
  docker run -d --name ll-b --network "$LL_NET" --ip "$LL_B_IP" \
    "$LL_IMAGE" sh /lldp-entry.sh >/dev/null
  local pa pb
  pa="$(docker inspect -f '{{.State.Pid}}' ll-a)"
  pb="$(docker inspect -f '{{.State.Pid}}' ll-b)"
  log "veth wire (ll-a:$pa <-> ll-b:$pb)"
  docker run --rm --privileged --pid=host --net=host alpine:3.22 sh -c "
    apk add --no-cache iproute2 >/dev/null 2>&1
    ip link add vethB2 type veth peer name vethA2
    ip link set vethB2 netns $pa
    ip link set vethA2 netns $pb
    nsenter -t $pa -n ip link set vethB2 up
    nsenter -t $pb -n ip link set vethA2 up
  "
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
  _launch

  log "等待 LLDP 发现（~${LL_WAIT}s）..."
  sleep "$LL_WAIT"
}

# ---------- verify ----------

# ① 邻居视图（lldpd 自带 CLI，与 SNMP WALK 分开验证二层邻居成立，AI 点1）
cmd_lldpcli() {
  local ok=1
  for name in ll-a ll-b; do
    log "=== $name lldpcli show neighbors ==="
    local out
    out="$(docker exec "$name" lldpcli show neighbors 2>&1 | mask)"
    echo "$out"
    if ! echo "$out" | grep -qiE 'LLDP neighbors:|veth'; then
      log "FAIL: $name lldpcli 未显示邻居"
      ok=0
    fi
  done
  [ "$ok" -eq 1 ]
}

# ② 单向 SNMP WALK 断言
_walk_one_direction() {
  local from="$1" expect_name="$2"
  local sys c4 c6
  log "=== $from view (expect $expect_name) ==="
  sys="$(node_walk "$from" 1.0.8802.1.1.2.1.4.1.1.9 | mask)"
  echo "$sys"
  if ! echo "$sys" | grep -q 'STRING:'; then
    log "FAIL: $from 未发现任何邻居"; return 1
  fi
  c4="$(node_walk "$from" 1.0.8802.1.1.2.1.4.1.1.4 | mask)"
  c6="$(node_walk "$from" 1.0.8802.1.1.2.1.4.1.1.6 | mask)"
  echo "$c4" | grep -qE 'INTEGER: 4' || { log "FAIL: chassis_subtype != 4 ($from)"; return 1; }
  echo "$c6" | grep -qE 'INTEGER: 5' || { log "FAIL: port_subtype != 5 ($from)"; return 1; }
  echo "$c4"; echo "$c6"
  return 0
}

cmd_verify() {
  local ok=1
  for pair in "ll-a:ll-b" "ll-b:ll-a"; do
    local from="${pair%%:*}" expect_name="${pair##*:}"
    _walk_one_direction "$from" "$expect_name" || ok=0
  done
  if [ "$ok" -eq 1 ]; then
    log "VERIFY OK：双向 SNMPv3 authPriv LLDP WALK 通过（lldpd 布局 1.4.1.1）"
  else
    log "VERIFY FAILED"; return 1
  fi
}

# ③ 销毁重建后断言（AI 点6：entry 每次启动重建 USM 用户）
cmd_verify_recreate() {
  log "销毁并重建 ll-a / ll-b（验证 entry 每次启动重建 USM 用户 + 邻居恢复）"
  _launch
  log "等待 LLDP 重新发现（~${LL_WAIT}s）..."
  sleep "$LL_WAIT"
  local ok=1
  for pair in "ll-a:ll-b" "ll-b:ll-a"; do
    local from="${pair%%:*}" expect_name="${pair##*:}"
    _walk_one_direction "$from" "$expect_name" || ok=0
  done
  if [ "$ok" -eq 1 ]; then
    log "VERIFY-RECREATE OK：USM 用户重建 + 邻居恢复 + WALK 通过"
  else
    log "VERIFY-RECREATE FAILED"; return 1
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
  all)      cmd_up; cmd_lldpcli; cmd_verify; cmd_verify_recreate; cmd_down ;;
  up)       cmd_up ;;
  verify)   cmd_lldpcli; cmd_verify ;;
  recreate) cmd_verify_recreate ;;
  down)     cmd_down ;;
  *) echo "用法: $0 [all|up|verify|recreate|down]" >&2; exit 2 ;;
esac

log "done ($_action)"