#!/usr/bin/env bash
# ============================================================
# 一键演示：拉起全栈并验证 Prometheus 抓取 / Grafana 仪表盘。
#   ./scripts/demo-stack.sh up     # 构建并启动全部服务
#   ./scripts/demo-stack.sh status # 查看各服务健康状态
#   ./scripts/demo-stack.sh verify # 验证抓取与仪表盘可用
#   ./scripts/demo-stack.sh down   # 停止全部服务
#
# 演示地址：
#   前端界面   http://localhost:8080    （admin / admin123）
#   Prometheus http://localhost:9090/targets
#   Grafana    http://localhost:3000    （admin / admin123，仪表盘已自动导入）
# ============================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

case "${1:-up}" in
  up)
    docker compose up -d --build
    echo "提示: 等待 10 秒让后端完成建表与调度启动"
    sleep 10
    ./scripts/demo-stack.sh status
    ;;
  status)
    echo "--- 容器状态 ---"
    docker compose ps
    echo "--- 后端健康 ---"
    curl -s -m 5 http://localhost:8000/health || echo "(后端未就绪)"
    echo
    echo "--- 前端首页 ---"
    curl -s -o /dev/null -w "HTTP %{http_code}\n" -m 5 http://localhost:8080/login.html || echo "(前端未就绪)"
    ;;
  verify)
    echo "--- Prometheus 目标 ---"
    curl -s -m 5 http://localhost:9090/api/v1/targets | head -c 400 || echo "(Prometheus 未就绪)"
    echo
    echo "--- Prometheus 抓取指标 ---"
    curl -s -m 5 "http://localhost:9090/api/v1/query?query=netcheck_assets_total" | head -c 300 || echo "(抓取失败)"
    echo
    echo "--- Grafana 可访问 ---"
    curl -s -o /dev/null -w "HTTP %{http_code}\n" -m 5 http://localhost:3000/login || echo "(Grafana 未就绪)"
    echo "--- 动态存储容量 ---"
    docker compose ps --format 'table {{.Name}}\t{{.Status}}'
    ;;
  down)
    docker compose down
    ;;
  *)
    echo "用法: $0 {up|status|verify|down}"
    exit 2
    ;;
esac