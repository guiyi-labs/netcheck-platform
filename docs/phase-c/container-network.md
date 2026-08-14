# 阶段 C1：容器网络适配验证

> 目标：验证「巡检后端跑在 Docker 容器内」时，各类检测能力是否可用，并给出适配方法与
> 排障指引。Docker 默认会给容器禁用 raw socket，而 `ping`/`traceroute` 依赖它，因此必须
> 为巡检容器显式授权 `NET_RAW` capability。

## 1. 为什么需要 NET_RAW

- `ping`（ICMP Echo）需要创建 raw socket；Docker 默认 seccomp 策略会拦截之。
- `traceroute` 使用 ICMP/UDP 探测报文，同样需要 raw socket。
- 结果：不加 `NET_RAW` 时，容器内 `ping` 报 `Operation not permitted`，端口/HTTP 检测不受影响。

## 2. 当前适配

`docker-compose.yml` 中 `netcheck-backend` 已配置：

```yaml
cap_add:
  - NET_RAW
```

`backend/Dockerfile` 已安装 `iputils-ping`（Debian 系包名，提供 ping）。

## 3. 自检

```bash
docker compose up -d --build
./scripts/verify-container-network.sh
```

脚本依次验证：ping 命令存在、raw socket 生效（ping 127.0.0.1）、容器名 DNS 解析、
TCP 连通、HTTP 请求。**全部 PASS** 即容器内巡检链路就绪。

## 4. 已知限制与对策

| 现象 | 原因 | 对策 |
| --- | --- | --- |
| `ping: Operation not permitted` | 缺 NET_RAW cap | compose 增加 `cap_add: [NET_RAW]` |
| ping 目标无法解析 | 容器网络 DNS 未覆盖 | 使用容器名（同一 compose 网络）或 `networks.netcheck-lab` 内的别名 |
| 巡检不到宿主机/外部网络 | compose 默认 bridge 隔离 | 前端/后端容器加 `extra_hosts` 或改为 `network_mode: host`（开发机） |
| traceroute 无输出 | 目标主机丢弃 ICMP/UDP | 使用 `-U`（UDP）或提升探测次数；结合 `-z` 间隔避免限速 |
| HTTP 检测到 demo 服务 404 | demo-nginx 未配置后端 | 检查 `demo-services/web-error` 的 conf，端口/首页映射正确即可 |

## 5. 验证记录

日期：2026-08-14。

- `frontend/Dockerfile` 由「逐个列 html」改为 `COPY *.html`，补齐 audit/users/asset-changes 等
  新增页面，避免容器内访问 404（阶段 C1 修复项）。
- `scripts/verify-container-network.sh` 新增，作为容器网络回归入口。
- 实测命令（本机构建验证）：

```text
docker compose up -d --build
./scripts/verify-container-network.sh
# 期望输出：
# [PASS] ping 命令存在
# [PASS] Ping 自身网关（需要 NET_RAW）
# [PASS] 解析 demo-web-ok
# [PASS] TCP 到 demo-web-ok:80
# [PASS] HTTP GET demo-web-ok
# ✅ 全部通过
```