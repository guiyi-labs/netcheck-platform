# 第 0 批 Docker 闭环验证记录

验证时间：2026-07-11 11:32:04

## 宿主机访问验证
- 后端 /health：ok，服务：netcheck-backend，版本：0.1.0
- 前端代理 /api/health：ok，数据库：sqlite:////app/data/netcheck.db
- 前端首页 http://localhost:8080：HTTP 200，包含平台标题、Bootstrap 样式和 `css/app.css` 引用
- 正常演示服务 http://localhost:18080：HTTP 200
- 异常演示服务 http://localhost:18081：HTTP 500
- 慢响应演示服务 http://localhost:18082：3.01 秒，状态：slow

## 说明
- 当前 Codex 沙盒用户无法访问 Docker Desktop named pipe，因此 `docker compose ps` 需要在主用户或管理员 PowerShell 中查看。
- 以上 HTTP 验证均从宿主机访问容器映射端口，说明第 0 批 Compose 环境已对外提供服务。
