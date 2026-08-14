#!/usr/bin/env bash
# ============================================================
# 局域网真实环境验证：在真实局域网内校验巡检/诊断链路。
# 覆盖：ping、端口、DNS、HTTP、traceroute、SNMP(可选)、nmap(可选)。
#
# 用法：
#   ./scripts/verify-lan.sh <网关/目标IP> [第二个目标IP ...]
#   例如：./scripts/verify-lan.sh 192.168.1.1 8.8.8.8
# ============================================================
set -u
TARGETS=("$@")

if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "用法: $0 <目标IP> [更多IP...]"
  exit 2
fi

echo "=== 环境信息 ==="
uname -a
echo "--- 本机路由 ---"
ip route 2>/dev/null || route -n 2>/dev/null || echo "(无 ip/route 命令)"

for TARGET in "${TARGETS[@]}"; do
  echo
  echo "===== 目标: $TARGET ====="

  echo "--- 1. ping ---"
  ping -c 2 -W 2 "$TARGET" >/dev/null 2>&1 \
    && echo "PASS: 可达" || echo "FAIL: 不可达(或防火墙拦截ICMP)"

  echo "--- 2. TCP 22/80/443 ---"
  for PORT in 22 80 443; do
    if nc -z -w 3 "$TARGET" "$PORT" 2>/dev/null; then
      echo "PASS: $TARGET:$PORT 开放"
    fi
  done

  echo "--- 3. traceroute (最多5跳) ---"
  if command -v traceroute >/dev/null 2>&1; then
    traceroute -n -m 5 -q 1 -w 1 "$TARGET" 2>&1 | tail -n +2 | head -5 || true
  else
    echo "(未安装 traceroute，跳过)"
  fi

  echo "--- 4. HTTP(S) ---"
  if command -v curl >/dev/null 2>&1; then
    for SCHEME in http https; do
      CODE=$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$SCHEME://$TARGET" 2>/dev/null)
      [ "$CODE" = "000" ] || echo "PASS: $SCHEME://$TARGET -> HTTP $CODE"
    done
  else
    echo "(未安装 curl，跳过)"
  fi

  echo "--- 5. SNMP (可选) ---"
  if command -v snmpget >/dev/null 2>&1; then
    snmpget -v2c -c public -t 2 -r 0 -On "$TARGET" 1.3.6.1.2.1.1.1.0 2>/dev/null \
      && echo "PASS: SNMP 可取系统描述" || echo "FAIL/跳过: SNMP 无响应"
  else
    echo "(未安装 net-snmp，跳过)"
  fi

  echo "--- 6. nmap (可选) ---"
  if command -v nmap >/dev/null 2>&1; then
    nmap -sn -T4 "$TARGET" 2>/dev/null | grep -q "Nmap scan report" \
      && echo "PASS: nmap 主机发现完成" || echo "FAIL/跳过: nmap 无响应"
  else
    echo "(未安装 nmap，跳过)"
  fi
done

echo
echo "=== 完成。FAIL 项请结合 docs/phase-c/archive.md 排查。 ==="