# NetCheck Platform

[![CI](https://github.com/guiyi-labs/netcheck-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/guiyi-labs/netcheck-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![Vue.js](https://img.shields.io/badge/Vue.js-3-4FC08D?logo=vuedotjs&logoColor=white)

> 面向中小型网络的资产巡检、故障诊断、报告与告警平台。

## 项目定位

NetCheck 将网络运维中的“资产在哪里、哪里异常、异常依据是什么、是否需要通知”组织成一条
可复现的工作链路。当前版本以 Docker 演示网络为主要验证环境，重点覆盖 HTTP、端口、Ping
和 DNS 检测，并保留真实网络接入所需的边界说明。

```text
资产台账 / 资产发现
          ↓
巡检任务 → 结果与趋势 → 故障诊断 → 告警确认 / 恢复
          └──────────────→ 报告导出 / 逻辑拓扑
```

## 已实现能力

| 方向 | 能力 |
|---|---|
| 资产管理 | 资产台账增删改查、类型元数据、授权范围内的主机与端口发现、发现结果导入 |
| 网络巡检 | Ping、端口、HTTP、DNS 检测；手动执行、定时任务、运行记录与结果查询 |
| 故障诊断 | 按巡检结果生成故障类型、等级、诊断依据和处理建议，并回写资产状态 |
| 告警闭环 | 告警策略、告警生成、确认、恢复、汇总和调度器状态 |
| 运维视图 | 仪表盘趋势、全局结果检索、Excel 报告、资产状态与逻辑拓扑 |
| 可复现演示 | Compose 内置正常、HTTP 500、慢响应和 DNS 可解析的演示目标服务 |

当前能力来自第 1–6 批迭代。完整实现范围、测试报告和答辩材料见
[最终交付文档](docs/final-delivery/delivery-checklist.md)。

## 网络运维扩展路线

下列能力是后续网络运维方向的扩展项，当前 README 不将其写成已完成能力：

- SNMPv3 / SSH 设备采集与凭据隔离；
- 设备配置备份、版本差异和受控回滚；
- LLDP 邻居发现与物理 / 逻辑拓扑关联；
- 接口流量、丢包、错误包和链路可用性指标；
- 基于 containerlab / FRRouting 的可复现网络实验场景。

## 快速启动

准备 Docker Desktop 或 Docker Engine，然后在项目根目录执行：

```bash
docker compose up -d --build
docker compose ps
```

访问地址：

| 服务 | 地址 | 用途 |
|---|---|---|
| Web 控制台 | `http://localhost:8080/login.html` | 登录并进入运维控制台 |
| Backend API | `http://localhost:8000` | FastAPI 服务 |
| API 健康检查 | `http://localhost:8000/health` | 后端存活检查 |
| Demo 正常服务 | `http://localhost:18080` | HTTP 200 场景 |
| Demo 异常服务 | `http://localhost:18081` | HTTP 500 场景 |
| Demo 慢服务 | `http://localhost:18082` | 慢响应场景 |

首次启动会创建本地演示管理员：`admin` / `admin123`。该账号只用于本地演示，部署到真实环境前
必须修改密码并替换默认配置。

停止环境：

```bash
docker compose down
```

## 推荐演示流程

1. 登录控制台，确认仪表盘显示资产状态和巡检趋势。
2. 使用 `demo-web-ok`、`demo-web-error`、`demo-web-slow` 创建 Ping、端口或 HTTP 巡检任务。
3. 执行任务后查看结果，进入故障诊断页核对故障等级、依据和建议。
4. 在告警中心确认或恢复告警，再从报告管理导出 Excel 报告。
5. 在资产发现和逻辑拓扑页查看授权范围内的资产与关系。

这条流程可以稳定复现正常响应、HTTP 500、慢响应、Docker 服务名 DNS 解析、诊断、告警和
资产状态回写结果，适合作为系统演示和论文答辩的基础场景。

## 技术栈

- Backend：Python 3.11、FastAPI、SQLAlchemy、SQLite、APScheduler
- Frontend：Vue 3、Vite、Element Plus、Axios
- 运维集成：Paramiko、Docker SDK、Kubernetes Python Client
- Runtime：Docker Compose、Nginx、内置演示网络

## 本地验证

没有 Docker 时，可以先运行后端测试：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pytest -q
```

完整接口清单见 [API 清单](docs/final-delivery/api-list.md)，部署、初始化、备份恢复和故障排查见
[部署与运维说明](docs/final-delivery/deployment-guide.md)。

## 运维边界

- 资产发现和扫描只能在获得授权的地址范围内执行，默认限制最多 256 个目标。
- 当前主要通过 Compose 演示网络验证，真实局域网扫描应在 Linux 或宿主机网络环境中单独复验。
- 真实网络环境中的凭据、设备地址和日志不得提交到仓库。

## 交付材料

- [部署说明](docs/final-delivery/deployment-guide.md)
- [测试报告](docs/final-delivery/test-report.md)
- [答辩演示脚本](docs/final-delivery/demo-script.md)
- [论文截图清单](docs/final-delivery/screenshot-checklist.md)
- [最终交付清单](docs/final-delivery/delivery-checklist.md)
