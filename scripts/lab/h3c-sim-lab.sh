#!/usr/bin/env bash
#
# P1 H3C 适配器真实验证（仿真服务载体）编排：build → up → verify → down
#
# 载体：高保真 Comware V7 仿真容器（OpenSSH 真实传输 + 忠实 CLI 文本 +
#        net-snmp H3C 风格 sysDescr）。边界如实标注：仿真服务 ≠ 真实 H3C 设备。
#
# verify 步骤：
#   1) SSH 真实采集（vendor=h3c_comware）：display version / interface brief /
#      ip routing-table / clock → 解析字段断言（先捕获 host key，再以指纹连接）
#   2) SNMPv3 authPriv 采集 sys facts（sysDescr 含 Comware、sysName）
#
# 用法：
#   scripts/lab/h3c-sim-lab.sh            # build + up + verify + down
#   scripts/lab/h3c-sim-lab.sh up         # 仅 up（调试）
#   scripts/lab/h3c-sim-lab.sh verify     # 仅 verify
#   scripts/lab/h3c-sim-lab.sh down       # 仅 down
#
# 环境变量（可覆盖）: H3C_NET / H3C_IP / H3C_PORT / SSH_USER / SSH_PASSWORD / SNMP_*
set -euo pipefail

H3C_IMAGE="${H3C_IMAGE:-netcheck-h3c-sim:lab}"
H3C_NET="${H3C_NET:-netcheck-h3c}"
H3C_SUBNET="${H3C_SUBNET:-172.29.0.0/16}"
H3C_IP="${H3C_IP:-127.0.0.1}"
H3C_PORT="${H3C_PORT:-2222}"
SSH_USER="${SSH_USER:-monitor}"
SSH_PASSWORD="${SSH_PASSWORD:-simpass}"
SNMP_USER="${SNMP_USER:-monitor}"
SNMP_AUTH_KEY="${SNMP_AUTH_KEY:-netcheckauth}"
SNMP_PRIV_KEY="${SNMP_PRIV_KEY:-netcheckpriv}"
# 宿主访问端口（Docker Desktop for Mac 无法直连容器 bridge IP，需 -p 发布）
PUBLISH_SSH_PORT="${PUBLISH_SSH_PORT:-3022}"
PUBLISH_SNMP_PORT="${PUBLISH_SNMP_PORT:-3161}"

_action="${1:-all}"

log() { printf '[h3c-sim] %s\n' "$*"; }

cmd_up() {
  if ! docker image inspect "$H3C_IMAGE" >/dev/null 2>&1; then
    log "构建镜像 $H3C_IMAGE ..."
    docker build -q -f scripts/lab/h3c-sim/Dockerfile -t "$H3C_IMAGE" scripts/lab/h3c-sim/
  else
    log "镜像 $H3C_IMAGE 已存在，跳过构建"
  fi
  if ! docker network inspect "$H3C_NET" >/dev/null 2>&1; then
    log "创建 bridge $H3C_NET ($H3C_SUBNET)"
    docker network create --subnet "$H3C_SUBNET" "$H3C_NET"
  fi
  log "start h3c-sim (ssh:$PUBLISH_SSH_PORT snmp:$PUBLISH_SNMP_PORT)"
  docker rm -f h3c-sim >/dev/null 2>&1 || true
  docker run -d --name h3c-sim --network "$H3C_NET" --ip 172.29.0.10 \
    -p "$PUBLISH_SSH_PORT:2222" -p "$PUBLISH_SNMP_PORT:161/udp" \
    "$H3C_IMAGE" >/dev/null
  log "等待 sshd/snmpd 就绪（~5s）..."
  sleep 5
}

# 通过采集器代码路径做真实 SSH 采集 + 断言（host key 先捕获再二次连接）
cmd_verify() {
  local ok=1
  log "=== 1) SSH 真实采集（vendor=h3c_comware 适配器路径） ==="
  PYTHONPATH="backend" H3C_IP="$H3C_IP" H3C_PORT="$PUBLISH_SSH_PORT" SSH_USER="$SSH_USER" \
  SSH_PASSWORD="$SSH_PASSWORD" ./.venv/bin/python - <<'PY'
import asyncio
import os

IP = os.environ["H3C_IP"]
PORT = int(os.environ["H3C_PORT"])
USER = os.environ["SSH_USER"]
PASS = os.environ["SSH_PASSWORD"]


async def main():
    from app.services.ssh_collector import collect_ssh

    # 第一步：捕获 host key 指纹（首次连接返回 host_key_unknown）
    first = await collect_ssh(IP, PORT, USER, password=PASS,
                              vendor="h3c_comware", host_key_fingerprint=None)
    if first.status != "host_key_unknown":
        raise AssertionError(f"首次连接应为 host_key_unknown，实际 {first.status}")
    fp = first.host_key_fingerprint
    print("host key fingerprint:", fp)

    # 第二步：以指纹连接，走正常采集路径
    result = await collect_ssh(IP, PORT, USER, password=PASS,
                               vendor="h3c_comware", host_key_fingerprint=fp)
    print("status:", result.status)
    print("facts:", result.facts)
    for cmd, out in result.raw_outputs.items():
        print(f"--- {cmd} ---")
        print(out)
    assert result.status == "ok", f"采集失败: {result.status} {result.error}"
    facts = result.facts
    assert facts.get("os_version") == "Comware 7.1.070", facts
    assert facts.get("uptime") == "2 weeks, 1 day, 3 hours, 4 minutes", facts
    assert facts.get("interfaces_count") == "5", facts
    assert facts.get("up_count") == "4", facts
    assert facts.get("down_count") == "1", facts
    assert facts.get("routes_count") == "3", facts
    assert facts.get("system_time") == "2026-08-16 09:30:00", facts
    print("SSH H3C 解析断言全部通过")


asyncio.run(main())
PY
  [ $? -eq 0 ] || ok=0

  log "=== 2) SNMPv3 authPriv sys facts (platform collector, real UDP to sim snmpd) ==="
  # Docker Desktop for Mac 的容器 UDP 发布对宿主不可达（实证：tcpdump 无包）、
  # 且当前网络拉取 python 基础镜像不稳定，故 SNMP 验证在【载体容器内】执行：
  # 平台采集器代码路径（collect_snmpv3）以真实 UDP socket 往返容器内 snmpd
  # （172.29.0.10:161，veth 层真实报文 + 真实 SNMPv3 authPriv 认证）。
  # 边界：采集进程与 snmpd 同容器（进程隔离差异在验收文档如实标注）。
  docker exec h3c-sim sh -c 'mkdir -p /srv/netcheck && rm -rf /srv/netcheck/backend'
  docker cp backend h3c-sim:/srv/netcheck/backend >/dev/null
  docker cp scripts/lab/h3c-sim/snmp-verify.py h3c-sim:/tmp/snmp-verify.py
  docker exec h3c-sim sh -c 'cd /srv/netcheck && PYTHONPATH=/srv/netcheck/backend \
    H3C_SIM_IP=172.29.0.10 SNMP_USER='"$SNMP_USER"' \
    SNMP_AUTH_KEY='"$SNMP_AUTH_KEY"' SNMP_PRIV_KEY='"$SNMP_PRIV_KEY"' \
    python3 /tmp/snmp-verify.py' 2>&1 | grep -v CryptographyDeprecationWarning
  [ $? -eq 0 ] || ok=0

  if [ "$ok" -eq 1 ]; then
    log "VERIFY OK：H3C 适配器在真实 SSH/SNMP 传输链路上端到端解析通过（仿真服务载体）"
  else
    log "VERIFY FAILED"
    return 1
  fi
}

cmd_down() {
  log "remove h3c-sim and bridge $H3C_NET (image kept)"
  docker rm -f h3c-sim >/dev/null 2>&1 || true
  docker network rm "$H3C_NET" >/dev/null 2>&1 || true
}

case "$_action" in
  all)   cmd_up; cmd_verify; cmd_down ;;
  up)    cmd_up ;;
  verify) cmd_verify ;;
  down)  cmd_down ;;
  *) echo "用法: $0 [all|up|verify|down]" >&2; exit 2 ;;
esac

log "done ($_action)"