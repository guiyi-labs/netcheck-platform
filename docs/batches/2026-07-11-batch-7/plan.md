# 第 7 批实施计划：测试、部署、文档材料与演示交付闭环

> 日期：2026-07-11
> 前置：第 1-6 批功能已完成。
> 目标：冻结功能范围，完成最终测试、部署说明、文档材料、演示脚本和交付清单。

## 范围

- 全链路回归测试。
- Docker 部署说明。
- 测试报告。
- API 清单。
- 数据库表结构说明。
- 演示脚本。
- 功能截图清单。
- 最终交付清单。
- README 最终补充。
- 第 7 批完成归档。

## 不再新增的内容

- 新业务功能。
- 新检测器。
- 新告警通知渠道。
- 新拓扑发现算法。
- 新报表模板。
- 大范围扫描或复杂调度。

## 交付文档

- `docs/final-delivery/deployment-guide.md`
- `docs/final-delivery/test-report.md`
- 演示脚本（本地归档）
- `docs/final-delivery/api-list.md`
- `docs/final-delivery/database-schema.md`
- 功能截图清单（本地归档）
- `docs/final-delivery/delivery-checklist.md`
- `docs/batches/2026-07-11-batch-7/plan.md`
- `docs/batches/2026-07-11-batch-7/archive.md`

## 验证命令

### 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### Docker 构建启动

```powershell
docker compose up -d --build
```

### 服务状态

```powershell
docker compose ps
```

### 健康检查

```powershell
curl http://localhost:8000/health
curl http://localhost:8080/api/health
```

### 页面检查

- `login.html`
- `index.html`
- `assets.html`
- `tasks.html`
- `results.html`
- `diagnosis.html`
- `alerts.html`
- `reports.html`
- `discovery.html`
- `topology.html`

## 完成标准

- 自动化测试全部通过。
- Docker 环境构建成功。
- 5 个容器服务均为 `Up`。
- 后端和前端代理健康检查通过。
- 前端核心页面均返回 200。
- 能完成登录、巡检、结果、诊断、告警、报告、资产发现、拓扑的端到端演示。
- 最终交付文档齐全。
- README 补充最终交付说明。
