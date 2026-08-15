# 快速开始

> 目标：3 分钟内把平台跑起来，体验完整巡检链路。

## 方式一：Docker 一键启动（推荐）

前置：已安装 Docker Desktop。

```bash
# （可选）把用户目录写入 .env，见部署手册
cp .env.example .env

# 一键构建并启动全部服务（含 Prometheus + Grafana 大屏）
./scripts/demo-stack.sh up
```

启动完成后访问：

| 服务 | 地址 | 账号 |
|---|---|---|
| 前端界面 | http://localhost:8080 | admin / admin123 |
| 后端 API 文档 | http://localhost:8000/docs | — |
| Grafana 大屏 | http://localhost:3000 | admin / admin123 |
| Prometheus | http://localhost:9090 | — |

## 方式二：本地开发运行

前置：Python 3.11+，Node 可选。

```bash
# 1. 后端：虚拟环境 + 依赖 + 启动
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
cd .. && PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 2. 前端：静态文件服务器（或任意静态托管）
cd frontend
python3 -m http.server 8080  # 或 npx serve -l 8080
```

访问 http://localhost:8080/login.html，admin / admin123 登录。

## 三分钟体验动线

1. 登录后进入**仪表盘**（index.html）：查看资产/任务/告警概览。
2. 进入**巡检任务**（tasks.html）→ 新建任务（勾选检测类型：Ping/端口/HTTP/TLS，选择资产）→ 点「运行」。
3. 打开**任务运行详情**（task-run.html）：状态变化通过 WebSocket 实时刷新，无需手动刷新。
4. 完成后在**巡检结果**（results.html）看每项检测输出，在**故障诊断**（diagnosis.html）看平台给出的诊断与建议。
5. 打开**趋势分析**（trends.html）：查看 RTT 曲线、可用率 SLA、运行耗时。

> 演示资产（seed 数据）：demo-web-ok / demo-web-error / demo-web-slow 等 12 条。
> 默认后端数据库为 `data/netcheck.db`（SQLite）。

## 下一步

- 想了解完整部署与配置：[[deployment|部署手册]]
- 想准备演示：[[demo-guide|演示指南]]
- 遇到问题：[[troubleshooting|排障 FAQ]]