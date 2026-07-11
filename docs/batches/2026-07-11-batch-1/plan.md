# 第 1 批实施计划：资产台账闭环

> 日期：2026-07-11
> 前置：第 0 批 Docker 基础环境已闭环（5 容器运行、健康检查通过）。
> 目标：完成「登录 → 资产管理 → 资产状态维护」基础平台能力，形成可演示的前后端闭环。

## 范围

- 管理员登录/退出（固定 token + localStorage）
- 资产新增、编辑、删除、查询
- 按名称/IP 模糊、类型/区域/状态精确筛选 + 分页
- 资产字段：name、ip、hostname、asset_type、location、os_type、business_name、ports、owner、status、remark
- 前端登录页、后台主框架、资产管理页
- 1 个管理员 + 12 条演示资产种子数据

## 暂缓

- 复杂角色权限、多用户
- 资产批量导入导出（第 6 批）
- 巡检逻辑（第 2 批）

## 文件清单

后端：
- `backend/app/models/user.py`、`asset.py`
- `backend/app/schemas/{common,user,asset}.py`
- `backend/app/core/security.py`、`deps.py`
- `backend/app/api/auth.py`、`assets.py`
- `backend/app/seed.py`
- `backend/app/main.py`（接入路由 + lifespan init_db）
- `backend/tests/conftest.py`、`test_auth.py`、`test_assets.py`

前端：
- `frontend/login.html`、`index.html`、`assets.html`
- `frontend/js/api.js`、`auth.js`
- `frontend/css/app.css`
- `frontend/Dockerfile`（拷贝多页面与静态资源）

## 完成标准

- 登录后进入后台主框架，可看到资产概览
- 资产管理页可增删改查 + 筛选分页
- 数据持久化（容器重启不丢）
- pytest 全过
- 端到端 curl 验证通过
