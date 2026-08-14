#!/usr/bin/env bash
# ============================================================
# N1 实验入口：确定性 Mock 演示 + containerlab/FRRouting Linux SNMP agent 实验。
#
# 用法：
#   ./scripts/n1-lab.sh mock     # 本地 mock 演示（无需真实设备）
#   ./scripts/n1-lab.sh lab-up   # 启动 containerlab FRRouting 实验（需 Docker + containerlab）
#   ./scripts/n1-lab.sh lab-down # 停止实验
#   ./scripts/n1-lab.sh status   # 查看实验状态
#
# 实验环境说明：
#   mock 模式：直接调用确定性采集逻辑，验证 SNMPv3 + SSH 全链路（不连真实设备）。
#   lab 模式：启动 FRRouting 容器，运行 Linux SNMP agent (snmpd)，
#            通过 SSH + SNMPv3 采集接口/路由信息，结果写入 NetCheck 设备表。
#
# 真实设备路径：
#   若已有运行的路由器/交换机支持 SNMPv3 authPriv + SSH 只读，
#   可直接在前端"设备管理"中录入管理 IP 和凭据，触发采集即可验证。
# ============================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0"])" && pwd)/.." 2>/dev/null || cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

ACTION="${1:-mock}"

case "$ACTION" in
  mock)
    echo "===== N1 确定性 Mock 演示 ====="
    echo ""
    echo "运行 Python mock 演示脚本（无真实网络访问）："
    echo ""
    PYTHONPATH=backend .venv/bin/python scripts/n1_mock_demo.py
    echo ""
    echo "===== Mock 演示完成 ====="
    ;;

  lab-up)
    echo "===== 启动 N1 FRRouting 实验环境 ====="
    if ! command -v docker &>/dev/null; then
      echo "错误：Docker 未安装，请先安装 Docker Desktop 或 Docker Engine。"
      exit 1
    fi
    if command -v containerlab &>/dev/null; then
      echo "使用 containerlab 拓扑：scripts/n1-lab.yml"
      if [ ! -f scripts/n1-lab.yml ]; then
        echo "正在生成 containerlab 拓扑..."
        cat > scripts/n1-lab.yml <<'TOPOLOGY'
name: netcheck-n1-lab
topology:
  nodes:
    router1:
      kind: frrouting
      image: frrouting/frr:v8.4.0
    router2:
      kind: frrouting
      image: frrouting/frr:v8.4.0
  links:
    - endpoints: ["router1:eth0", "router2:eth0"]
TOPOLOGY
      fi
      containerlab deploy -t scripts/n1-lab.yml
      echo ""
      echo "实验环境已启动："
      echo "  router1: 172.20.20.11 (SNMPv3 + SSH via FRR)"
      echo "  router2: 172.20.20.12 (SNMPv3 + SSH via FRR)"
      echo ""
      echo "在 NetCheck 前端 http://localhost:8080/devices.html 中："
      echo "  1. 创建凭据（SNMPv3 authPriv + SSH）"
      echo "  2. 添加设备（management_ip = 172.20.20.11 或 .12）"
      echo "  3. 绑定凭据并触发采集"
    else
      echo "containerlab 未安装，使用 Docker 网络替代..."
      docker network create netcheck-n1 2>/dev/null || true
      docker run -d --name n1-router1 --network netcheck-n1 \
        --cap-add NET_RAW --cap-add NET_ADMIN \
        -e SNMP_AUTH_KEY=netcheck-test \
        -e SNMP_PRIV_KEY=netcheck-test \
        -e SNMP_USER=netcheck \
        -p 16111:16111/udp \
        -p 2211:22 \
        -p 8081:80 \
        frrouting/frr:v8.4.0 2>/dev/null || echo "(n1-router1 已存在或拉取中)"
      echo ""
      echo "实验路由器 n1-router1 启动中，需手动配置 SNMPv3（见 docs/operations/n1-lab.md）。"
    fi
    echo ""
    echo "查看状态：./scripts/n1-lab.sh status"
    ;;

  lab-down)
    echo "===== 停止 N1 实验环境 ====="
    if command -v containerlab &>/dev/null && [ -f scripts/n1-lab.yml ]; then
      containerlab destroy -t scripts/n1-lab.yml
    fi
    docker rm -f n1-router1 n1-router2 2>/dev/null || true
    docker network rm netcheck-n1 2>/dev/null || true
    echo "实验环境已清理。"
    ;;

  status)
    echo "===== N1 实验状态 ====="
    echo ""
    echo "容器："
    docker ps -a --filter name=n1- --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "(无 Docker 容器)"
    echo ""
    if command -v containerlab &>/dev/null; then
      echo "containerlab 实验："
      containerlab inspect -t scripts/n1-lab.yml 2>/dev/null || echo "(无运行中的实验拓扑)"
    fi
    ;;

  *)
    echo "用法：$0 mock | lab-up | lab-down | status"
    exit 1
    ;;
esac