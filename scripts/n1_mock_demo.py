#!/usr/bin/env python3
"""N1 确定性 Mock 演示：展示 SNMPv3 + SSH 只读采集全链路，无需真实设备。

运行方式：
    PYTHONPATH=backend .venv/bin/python scripts/n1_mock_demo.py

输出：
    采集结果（设备事实、接口速率、失败分类、凭据脱敏状态）。
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import datetime, timedelta
from app.services.interface_rate import compute_rate, classify_interface
from app.services.snmpv3_collector import classify_error, _oid_in_allowlist
from app.models.device import SSH_VENDOR_ADAPTERS, SSH_READONLY_COMMANDS, OID_ALLOWLIST


def main():
    print("=" * 60)
    print("  N1 SNMPv3 与 SSH 只读采集 — 确定性 Mock 演示")
    print("=" * 60)
    print()

    # 1. OID Allowlist 验证
    print("【1】OID Allowlist 验证")
    test_oids = [
        ("1.3.6.1.2.1.1.5.0", "sysName", True),
        ("1.3.6.1.2.1.2.2.1.10", "ifInOctets", True),
        ("1.3.6.1.2.1.69.1.1", "LLDP（未开放）", False),
    ]
    for oid, label, expected in test_oids:
        result = _oid_in_allowlist(oid)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {oid} ({label}) → {'允许' if result else '拒绝'}")
    print()

    # 2. SNMPv3 authPriv 算法映射
    print("【2】SNMPv3 authPriv 算法 Allowlist")
    from app.services.snmpv3_collector import AUTH_MAP, PRIV_MAP
    print(f"  认证算法：{list(AUTH_MAP.keys())}")
    print(f"  加密算法：{list(PRIV_MAP.keys())}")
    print()

    # 3. 错误分类
    print("【3】SNMPv3 错误分类")
    try:
        from pysnmp.proto.errind import RequestTimedOut, AuthenticationError
        cases = [
            (RequestTimedOut(), "超时"),
            (AuthenticationError(), "认证失败"),
            (None, "成功"),
            ("OtherError", "未知错误"),
        ]
        for err, desc in cases:
            print(f"  {desc} → classify_error → {classify_error(err, 0)}")
    except ImportError:
        print("  ⚠️ pysnmp 未安装，跳过错误分类演示")
    print()

    # 4. 接口速率计算
    print("【4】接口速率计算（回绕 / 重启 / 缺样本）")
    base = datetime(2025, 8, 1, 12, 0, 0)
    curr = base + timedelta(seconds=10)
    rate1 = compute_rate(0, 1000, base, curr)
    print(f"  正常样本：0→1000B / 10s = {rate1} bps（预期 800.0）")
    C64 = 2**64
    rate2 = compute_rate(C64 - 1000, 500, base, curr)
    print(f"  回绕样本：{C64-1000}→500B / 10s = {rate2} bps（预期 1200.0）")
    rate3 = compute_rate(10**12, 200, base, curr)
    print(f"  重启样本：{10**12}→200B / 10s = {rate3} bps（预期 None，速率异常高→丢弃）")
    print()

    # 5. 接口状态分类
    print("【5】接口状态分类（RFC 2863）")
    print(f"  (1,1) → {classify_interface(1,1)}（Up/Up → ok）")
    print(f"  (1,2) → {classify_interface(1,2)}（Up/Down → down）")
    print(f"  (2,1) → {classify_interface(2,1)}（Down/Up → down）")
    print(f"  (None,None) → {classify_interface(None,None)}（未知 → unknown）")
    print()

    # 6. SSH 厂商适配器与命令 Allowlist
    print("【6】SSH 厂商适配器 Allowlist")
    for vendor in SSH_VENDOR_ADAPTERS:
        cmds = SSH_READONLY_COMMANDS.get(vendor, [])
        print(f"  {vendor}: {len(cmds)} 条只读命令（示例：{cmds[0] if cmds else '无'}）")
    print()

    # 7. 凭据脱敏（不显示真实密钥）
    print("【7】凭据脱敏状态")
    from app.services.credential_manager import redact, secret_digest
    print(f"  redact('AuthKeySecret123') → {redact('AuthKeySecret123')}")
    print(f"  secret_digest('SSHPasswordRich1') → {secret_digest('SSHPasswordRich1')[:12]}...")
    print()

    # 8. 设备事实采集 mock 模拟
    print("【8】设备采集结果模拟（SNMPv3 + SSH）")
    print("""
  设备: core-router-01 (10.0.0.1)
  协议: SNMPv3 authPriv + SSH (linux)
  ───────────────────────────────────
  SNMPv3 Facts:
    sys_name    = core-router-01
    sys_descr   = Linux core-router 5.15.0-91-generic #102-Ubuntu SMP
    sys_uptime  = 15 days, 3:22:45
  ───────────────────────────────────
  接口状态（2 条）:
    eth0  (Admin Up, Oper Up)   → ok
      in:  1,234,567 B  out: 2,345,678 B
      in_rate:  800.0 bps   out_rate: 1,200.0 bps
    eth1  (Admin Up, Oper Down) → down
      in:  0 B  out: 0 B
      in_rate:  unknown       out_rate:  unknown
  ───────────────────────────────────
  SSH Facts:
    hostname  = core-router-01.lab.local
    os_version = Linux core-router 5.15.0-91-generic
  ───────────────────────────────────
  采集状态: success
  凭据状态: configured, has_secret=True, algo_digest=SHA-256/AES-128
""")

    # 9. 三种失败场景演示
    print("【9】失败场景模拟")
    scenarios = [
        ("SNMPv3 认证失败", "auth_failed", "auth_key 或 username 错误"),
        ("SSH host key 未知（首次连接）", "host_key_unknown", "需人工确认 fingerprint 后登记"),
        ("SNMPv3 超时", "timeout", "设备不可达或 161 端口未开放"),
    ]
    for name, status, desc in scenarios:
        print(f"  {name}:")
        print(f"    collect_status = {status}")
        print(f"    说明：{desc}")
        print(f"    页面显示：{desc}（红色状态，非绿色/0 流量）")
        print()
    print("=" * 60)
    print("  演示完成。")
    print("=" * 60)


if __name__ == "__main__":
    main()