#!/usr/bin/env bash
# ============================================================
# 容器网络适配自检：验证 backend 容器内巡检所需的网络能力。
#
# 覆盖：
#   1. ping 命令与 setuid/raw socket 能力（NET_RAW cap）
#   2. DNS 解析（demo-web-ok 等容器名）
#   3. TCP 连通性（到 demo 服务容器）
#   4. HTTP 请求（到 demo-web-ok:80）
#
# 用法：
#   docker compose up -d --build && ./scripts/verify-container-network.sh
# ============================================================
set -u

BACKEND="netcheck-backend"
FAILURES=0

check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "[PASS] $name"
  else
    echo "[FAIL] $name"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "== 1. ping 工具与 raw socket 能力 =="
check "ping 命令存在" docker exec "$BACKEND" sh -c "command -v ping >/dev/null"
check "Ping 自身网关（需要 NET_RAW）" docker exec "$BACKEND" ping -c 1 -W 2 127.0.0.1

echo "== 2. DNS 解析（容器名） =="
check "解析 demo-web-ok" docker exec "$BACKEND" sh -c "getent hosts demo-web-ok >/dev/null 2>&1 || nslookup demo-web-ok >/dev/null 2>&1"

echo "== 3. TCP 连通性 =="
check "TCP 到 demo-web-ok:80" docker exec "$BACKEND" sh -c "cat < /dev/null > /dev/tcp/demo-web-ok/80" 2>/dev/null || check "TCP 到 demo-web-ok:80 (python)" docker exec "$BACKEND" python -c "import socket; socket.create_connection(('demo-web-ok', 80), timeout=3)"

echo "== 4. HTTP 请求 =="
check "HTTP GET demo-web-ok" docker exec "$BACKEND" python -c "
import httpx
r = httpx.get('http://demo-web-ok:80', timeout=5)
assert r.status_code == 200, r.status_code
"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "✅ 全部通过：容器内巡检所需的网络能力正常。"
  exit 0
else
  echo "❌ $FAILURES 项失败。排查建议见 docs/phase-c/container-network.md。"
  exit 1
fi