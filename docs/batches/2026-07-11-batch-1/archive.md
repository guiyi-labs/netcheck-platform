# 第 1 批完成归档：资产台账闭环

> 完成日期：2026-07-11
> 状态：已闭环，端到端验证通过

## 1. 功能说明

本批交付了平台的登录鉴权与资产台账能力。管理员可通过登录页进入后台，对网络资产进行新增、编辑、删除、查询、筛选与分页，数据持久化于 SQLite。具体能力：

- 管理员登录（admin/admin123）与退出，固定 token 鉴权。
- 资产 CRUD：13 个字段（含类型、区域、端口、负责人、状态、备注）。
- 按名称/IP 模糊查询，按类型/区域/状态精确筛选，分页（默认 20/页）。
- 后台主框架含导航栏、当前用户、退出；资产概览统计卡片。
- 资产管理页含筛选表单、表格、状态颜色标签、新增/编辑模态框、删除确认、分页。

## 2. 接口清单

统一响应包络 `{code, message, data}`，`code=0` 成功。除 `/health`、`/api/health` 外均需 `Authorization: Bearer {token}`。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | /api/auth/login | 否 | 登录，返回 `{token, user:{id,username,role}}` |
| POST | /api/auth/logout | 是 | 退出，清空 token |
| GET | /api/auth/me | 是 | 当前用户信息 |
| GET | /api/assets | 是 | 列表，支持 name/ip/asset_type/location/status 筛选 + page/page_size |
| GET | /api/assets/meta/types | 是 | 下拉选项（资产类型、状态常量） |
| POST | /api/assets | 是 | 新增，201 |
| GET | /api/assets/{id} | 是 | 详情 |
| PUT | /api/assets/{id} | 是 | 更新 |
| DELETE | /api/assets/{id} | 是 | 删除 |

响应示例（列表）：
```json
{"code":0,"message":"ok","data":{"total":12,"page":1,"page_size":20,"items":[...]}}
```

## 3. 数据库表与字段变化

新增表：

**users**
- id, username(unique,index), password_hash, role, api_token(index,nullable), created_at, last_login_at

**assets**
- id, name, ip(index), hostname, asset_type(index), location(index), os_type, business_name, ports, owner, status(index,default 'unknown'), remark, created_at, updated_at

种子数据（`backend/app/seed.py`，幂等）：
- 1 个管理员：admin / admin123（pbkdf2_sha256 哈希）
- 12 条演示资产：3 个 Docker 演示服务（用 Compose 服务名作 ip，供第 2 批巡检复用）+ 交换机/服务器/数据库/Redis/堡垒机/终端/容器，覆盖 online/offline/warning/unknown 四种状态。

## 4. 页面与交互

- `login.html`：居中登录卡片，默认填 admin/admin123，成功存 token 跳 index。
- `index.html`：顶部导航 + 资产概览（总数/在线/警告/离线统计卡），无 token 跳登录。
- `assets.html`：筛选表单 + 表格（状态颜色标签）+ 新增/编辑模态框 + 删除确认 + 分页。
- `js/api.js`：fetch 封装，自动加 Bearer、解析包络、401 跳登录。
- `js/auth.js`：requireAuth/currentUser/logout/renderNav。

## 5. 测试结果

**单元测试**（`python -m pytest -q`）：

```
15 passed in 17.90s
```

覆盖：health(2) + auth(5：登录成功/失败、me 有无 token、登出失效) + assets(8：鉴权拦截、列表、类型筛选、状态筛选、元数据、CRUD 全流程、404、分页)。

**端到端验证**（重建容器后 curl）：

```
ASSETS_TOTAL=12
WEB_SERVICE_COUNT=3
PAGE_LOGIN=200
PAGE_ASSETS=200
PAGE_INDEX=200
NO_TOKEN_401=401
```

- 登录返回 token（64 字符）与用户信息
- 新增资产返回 id=13（验证后删除恢复 12 条）
- DELETE 后再 GET 返回 404
- 无 token 访问 /api/assets 返回 401

## 6. 已知问题与边界

- 单管理员单 token：同一用户同一时间只保留一个有效会话，后登录会使旧 token 失效。项目场景够用。
- 无角色权限：仅 admin 角色，不做多用户细粒度权限。
- 无 token 过期：固定 token 不带 TTL，登出才失效。后续如需可在第 5 批加过期策略。
- 演示资产 ip 字段对 Docker 演示服务使用 Compose 服务名（如 `demo-web-ok`），便于第 2 批巡检直接连接；其余资产用内网 IP，当前不可达（将作为离线场景演示）。
- 前端为原生 JS + Bootstrap CDN，无构建步骤；如后续需复杂交互可升级，但不影响本批闭环。

## 7. 下一批依赖

本批为第 2 批「巡检执行闭环」提供了：

- 资产台账数据与持久化，巡检任务可基于 `assets` 表选择巡检对象。
- 鉴权基础设施（token、get_current_user），第 2 批巡检接口可直接复用。
- 统一响应包络与前端 API 封装，新增巡检接口与页面只需扩展。
- 3 个 Docker 演示服务已登记为资产，第 2 批可直接对其执行 Ping/端口/HTTP 检测。

第 2 批应做：巡检任务管理、PingChecker/PortChecker/HttpChecker、手动执行、结果落库（inspection_result 表）、任务执行日志。
