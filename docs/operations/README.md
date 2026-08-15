# NetCheck 平台文档中心

> 面向中小型网络的自动化巡检与故障诊断平台 —— 操作与说明文档总入口。

## 快速入口

| 文档 | 适用场景 |
|---|---|
| [[quickstart|快速开始]] | 3 分钟跑起来，先看效果 |
| [[deployment|部署手册]] | 本地开发 / Docker / MySQL / 配置项 |
| [[user-guide|用户操作手册]] | 各页面功能与完整巡检流程 |
| [[demo-guide|演示指南]] | 演示动线、话术、故障制造 |
| [[troubleshooting|排障 FAQ]] | 常见问题定位与修复 |
| [[api-reference|API 参考]] | 全部端点、鉴权、示例 |
| [[development|开发指南]] | 代码结构、测试、约定 |

## 项目状态

- 测试：`110 passed`（全绿）
- 技术栈：FastAPI + SQLAlchemy 2.0 + SQLite/MySQL + APScheduler + 原生 WebSocket
- 前端：原生 HTML/JS（Bootstrap 5 + ECharts 5），Nginx 托管
- 部署：Docker Compose（backend + frontend + MySQL + Prometheus + Grafana + demo 服务）

## 历史归档（仅供参考，可能早于最新功能）

- `docs/phase-a/archive.md` ~ `docs/phase-d/archive.md`：阶段开发归档
- `docs/final-delivery/`：早期交付文档（未覆盖 C/D 阶段与演示增强，仍保留备查）
- `docs/batches/`：批次计划与归档
- `docs/后续开发路线.md`：ABCD 全阶段路线图

## 版本

- 当前 `config.version = "0.2.0"`
- 中路提交：`915cd79`（A）→ `1884c50`（B）→ `d3f0a24`（C）→ `1a2a7fd`（D）→ `7d3c7c7`/`8a86979`（演示增强）