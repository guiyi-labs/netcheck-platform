"""演示数据：1 个管理员 + 12 条资产。

演示资产覆盖正常/异常/慢响应 Web 服务及离线主机，供第 1 批台账展示与第 2 批巡检复用。
"""
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.asset import Asset
from app.models.user import User

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

DEMO_ASSETS: list[dict] = [
    {
        "name": "正常Web服务",
        "ip": "demo-web-ok",
        "hostname": "demo-web-ok",
        "asset_type": "web_service",
        "location": "核心机房",
        "business_name": "演示业务",
        "ports": "80",
        "owner": "运维组",
        "status": "online",
        "remark": "Docker 演示服务，HTTP 200",
    },
    {
        "name": "异常Web服务",
        "ip": "demo-web-error",
        "hostname": "demo-web-error",
        "asset_type": "web_service",
        "location": "核心机房",
        "business_name": "演示业务",
        "ports": "80",
        "owner": "运维组",
        "status": "offline",
        "remark": "Docker 演示服务，HTTP 500",
    },
    {
        "name": "慢响应Web服务",
        "ip": "demo-web-slow",
        "hostname": "demo-web-slow",
        "asset_type": "web_service",
        "location": "核心机房",
        "business_name": "演示业务",
        "ports": "80",
        "owner": "运维组",
        "status": "warning",
        "remark": "Docker 演示服务，延迟 3 秒",
    },
    {
        "name": "核心交换机",
        "ip": "10.0.0.1",
        "hostname": "core-sw-01",
        "asset_type": "network_device",
        "location": "核心机房",
        "os_type": "VRP",
        "ports": "22,80",
        "owner": "网络组",
        "status": "online",
        "remark": "核心层交换机",
    },
    {
        "name": "业务服务器01",
        "ip": "10.0.0.11",
        "hostname": "app-server-01",
        "asset_type": "server",
        "location": "业务机房",
        "os_type": "Linux",
        "business_name": "订单系统",
        "ports": "22,80,443",
        "owner": "运维组",
        "status": "online",
        "remark": "订单服务主节点",
    },
    {
        "name": "业务服务器02",
        "ip": "10.0.0.12",
        "hostname": "app-server-02",
        "asset_type": "server",
        "location": "业务机房",
        "os_type": "Linux",
        "business_name": "订单系统",
        "ports": "22,80,443",
        "owner": "运维组",
        "status": "offline",
        "remark": "订单服务备节点，当前停机",
    },
    {
        "name": "数据库服务",
        "ip": "10.0.0.21",
        "hostname": "db-master",
        "asset_type": "database_service",
        "location": "数据机房",
        "os_type": "MySQL 8",
        "business_name": "订单系统",
        "ports": "3306",
        "owner": "DBA",
        "status": "online",
        "remark": "主数据库",
    },
    {
        "name": "Redis缓存服务",
        "ip": "10.0.0.22",
        "hostname": "redis-01",
        "asset_type": "middleware",
        "location": "数据机房",
        "business_name": "订单系统",
        "ports": "6379",
        "owner": "DBA",
        "status": "online",
        "remark": "缓存节点",
    },
    {
        "name": "堡垒机",
        "ip": "10.0.0.254",
        "hostname": "bastion",
        "asset_type": "server",
        "location": "核心机房",
        "os_type": "Linux",
        "ports": "443",
        "owner": "安全组",
        "status": "online",
        "remark": "运维入口",
    },
    {
        "name": "办公终端01",
        "ip": "10.0.0.101",
        "hostname": "pc-101",
        "asset_type": "terminal",
        "location": "办公区",
        "os_type": "Windows 11",
        "owner": "张三",
        "status": "online",
        "remark": "研发工位",
    },
    {
        "name": "办公终端02",
        "ip": "10.0.0.102",
        "hostname": "pc-102",
        "asset_type": "terminal",
        "location": "办公区",
        "os_type": "Windows 11",
        "owner": "李四",
        "status": "offline",
        "remark": "已下班关机",
    },
    {
        "name": "测试容器服务",
        "ip": "10.0.0.201",
        "hostname": "test-container",
        "asset_type": "container",
        "location": "测试环境",
        "business_name": "测试平台",
        "ports": "8080",
        "owner": "测试组",
        "status": "unknown",
        "remark": "临时容器，状态待确认",
    },
]


def seed_demo_data(SessionLocal: sessionmaker) -> None:
    db: Session = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    username=ADMIN_USERNAME,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role="admin",
                )
            )
        if db.query(Asset).count() == 0:
            db.add_all([Asset(**item) for item in DEMO_ASSETS])
        db.commit()
    finally:
        db.close()
