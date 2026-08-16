#!/usr/bin/env python3
"""P1 SNMP 真实验证：平台采集器代码路径（collect_snmpv3）在采集器容器内，
以真实 UDP SNMPv3 authPriv 访问仿真载体（172.29.0.10:161），断言
H3C 风格 sysDescr / sysName 解析成功。

边界：采集进程运行在【采集器容器】内（Docker Desktop for Mac 的 UDP
发布对宿主不可达），载体为仿真服务（见 docs/final-delivery/
h3c-real-verification.md 边界声明）。
"""
import asyncio
import os

IP = os.environ.get("H3C_SIM_IP", "172.29.0.10")
USER = os.environ.get("SNMP_USER", "monitor")
AUTH = os.environ.get("SNMP_AUTH_KEY", "netcheckauth")
PRIV = os.environ.get("SNMP_PRIV_KEY", "netcheckpriv")


async def main() -> int:
    from app.services.snmpv3_collector import collect_snmpv3

    result = await collect_snmpv3(IP, USER, AUTH, PRIV,
                                  auth_algo="SHA-256", priv_algo="AES-128",
                                  port=161)
    print("status:", result.status)
    print("facts:", result.facts)
    if result.status != "ok":
        print(f"SNMP 采集失败: {result.status} {result.error}")
        return 1
    sys_descr = result.facts.get("sys_descr", "") or ""
    if "Comware" not in sys_descr:
        print(f"sysDescr 应含 Comware: {sys_descr!r}")
        return 1
    if not result.facts.get("sys_name"):
        print("sysName 应非空")
        return 1
    print("SNMP H3C sysDescr/sysName 断言通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))