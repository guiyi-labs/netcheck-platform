# 部署说明

> 项目：面向中小型网络的自动化巡检与故障诊断平台
> 适用：最终答辩、验收与本地复现

## 1. 环境要求

- Docker Desktop 或 Docker Engine
- Windows 10/11、Linux 或 macOS
- 可用端口：
  - `8000`：后端 API
  - `8080`：前端页面
  - `18080`：正常 Web 演示服务
  - `18081`：HTTP 500 演示服务
  - `18082`：慢响应演示服务

## 2. 启动系统

在项目根目录执行：

```powershell
docker compose up -d --build
```

访问地址：

- 前端登录页：`http://localhost:8080/login.html`
- 后端健康检查：`http://localhost:8000/health`
- 前端代理健康检查：`http://localhost:8080/api/health`

默认账号：

```text
用户名：admin
密码：admin123
```

## 3. 查看服务状态

```powershell
docker compose ps
```

正常情况下应看到以下服务均为 `Up`：

- `netcheck-backend`
- `netcheck-frontend`
- `demo-web-ok`
- `demo-web-error`
- `demo-web-slow`

## 4. 演示服务说明

| 服务 | 地址 | 预期表现 |
|---|---|---|
| demo-web-ok | http://localhost:18080 | HTTP 200 正常 |
| demo-web-error | http://localhost:18081 | HTTP 500 异常 |
| demo-web-slow | http://localhost:18082 | 慢响应，约 3 秒 |

这些服务同时可在 Docker 内部通过服务名访问：

- `demo-web-ok`
- `demo-web-error`
- `demo-web-slow`

用于巡检和 DNS 检测演示。

## 5. 数据持久化

Docker volume：

- `db_data`：SQLite 数据库
- `report_data`：Excel 报告文件
- `backend_logs`：后端日志目录

停止系统但保留数据：

```powershell
docker compose down
```

停止系统并清空数据：

```powershell
docker compose down -v
```

注意：`down -v` 会删除数据库和历史报告。

## 6. 本地自动化测试

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

如果虚拟环境已存在：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 7. 常见问题

### 端口被占用

检查 `8000`、`8080`、`18080`、`18081`、`18082` 是否被其他程序占用。

### Docker Desktop 未启动

先启动 Docker Desktop，再执行 `docker compose up -d --build`。

### 前端图表样式异常

前端使用 Bootstrap / ECharts CDN。若答辩现场无网络，核心页面仍可访问；部分样式或图表可能受 CDN 影响。拓扑页已提供 ECharts 不可用时的文本降级展示。

### 资产发现安全边界

资产发现仅用于授权范围内的小规模扫描，系统限制最多 256 个目标。演示建议使用 `127.0.0.1` 或 Docker 内部可控目标，避免扫描未知网络。

### 定时巡检边界

定时巡检使用单进程 APScheduler，适合本地和单实例部署演示；分布式调度锁、Cron 表达式和复杂任务队列作为后续扩展。
