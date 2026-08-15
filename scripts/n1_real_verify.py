#!/usr/bin/env python3
"""N1/N2 真实环境验证：对 scripts/lab/Dockerfile.lab 构建的容器执行真实 SNMPv3 + SSH 采集。

可复现启动（推荐：bridge 网络 + Docker DNS，兼容 colima UDP 发布不可用的情况）：

  # 1. 构建镜像（凭据默认 = 文档测试值，可 --build-arg 覆盖）
  docker build -f scripts/lab/Dockerfile.lab -t netcheck-n1-lab:latest scripts/lab/

  # 2. 创建隔离网络并启动实验路由器（同网络内可用服务名 DNS）
  docker network create netcheck-n1
  docker run -d --name netcheck-n1-lab-router --network netcheck-n1 \
      --cap-add NET_RAW --cap-add NET_ADMIN \
      netcheck-n1-lab:latest

  # 3. 任选其一运行本脚本：
  #    宿主机（若无 UDP 端口发布限制，也可 -p 映射后指向 127.0.0.1）：
  #      PYTHONPATH=backend .venv/bin/python scripts/n1_real_verify.py \
  #        N1_ROUTER_HOST=netcheck-n1-lab-router N1_SNMP_PORT=161 N1_SSH_PORT=2222
  #    或进入同网络容器（推荐）：
  #      docker run --rm --network netcheck-n1 -v $PWD/backend:/app/backend \
  #        -v $PWD/scripts:/app/scripts -w /app \
  #        -e N1_ROUTER_HOST=netcheck-n1-lab-router -e N1_SNMP_PORT=161 -e N1_SSH_PORT=2222 \
  #        python:3.12-alpine sh -c "pip install pysnmp paramiko cryptography -q \
  #          && PYTHONPATH=/app/backend python3 /app/scripts/n1_real_verify.py"

  # 4. 清理
  docker rm -f netcheck-n1-lab-router; docker network rm netcheck-n1

验证内容：
  1) SNMPv3 authPriv（createUser 认证算法，默认 SHA-256 + AES-128）真实采集
     sysName/sysDescr/sysUpTime + ifTable
  2) SSH 只读采集（hostname/uname/ip link）真实执行
  3) N2 配置备份（CONFIG_READ_COMMANDS 内 linux 命令）真实读取 + 脱敏
  4) host key 首次未知/匹配/不匹配真实行为

全部凭据为文档测试值（Obsidian 16 N2.1 归档声明），可用环境变量覆盖：
  N1_SNMP_USER / N1_SNMP_AUTH / N1_SNMP_PRIV / N1_SSH_USER / N1_SSH_PASS
"""
import asyncio
import os
import sys

from app.services.snmpv3_collector import collect_snmpv3, run_snmpv3_sync
from app.services.ssh_collector import collect_ssh
from app.services.config_backup import _collect_config_ssh, ConfigCollectResult

# 支持容器内验证：N1_ROUTER_HOST 指向同网络容器名
HOST = os.environ.get("N1_ROUTER_HOST", "127.0.0.1")
SNMP_PORT = int(os.environ.get("N1_SNMP_PORT", "16111"))
SSH_PORT = int(os.environ.get("N1_SSH_PORT", "2222"))
# 凭据默认 = 文档测试值（与 Dockerfile.lab ARG 默认一致，可环境变量覆盖）
USERNAME = os.environ.get("N1_SNMP_USER", "monitor")
AUTH_KEY = os.environ.get("N1_SNMP_AUTH", "netcheckauth")
PRIV_KEY = os.environ.get("N1_SNMP_PRIV", "netcheckpriv")
SSH_USER = os.environ.get("N1_SSH_USER", "root")
SSH_PASS = os.environ.get("N1_SSH_PASS", "netcheck123")
# 认证算法：必须与镜像 createUser 一致（默认 SHA-256 / AES-128，可用环境变量覆盖）
AUTH_ALGO = os.environ.get("N1_SNMP_AUTH_ALGO", "SHA-256")
PRIV_ALGO = os.environ.get("N1_SNMP_PRIV_ALGO", "AES-128")

FAILED = []


def ok(name: str, detail: str = ""):
    print(f"  ✅ {name}" + (f"  {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    print(f"  ❌ {name}  {detail}")
    FAILED.append(name)


def main() -> int:
    print("=" * 60)
    print("N1/N2 真实环境验证（Docker 容器 netcheck-n1-lab-router）")
    print("=" * 60)

    # ---------- 1. SNMPv3 authPriv ----------
    print("\n【1】SNMPv3 authPriv 真实采集 " + f"({AUTH_ALGO} + {PRIV_ALGO})")
    result = run_snmpv3_sync(
        host=HOST, username=USERNAME,
        auth_key=AUTH_KEY, priv_key=PRIV_KEY,
        auth_algo=AUTH_ALGO, priv_algo=PRIV_ALGO,
        port=SNMP_PORT,
    )
    if result.status != "ok":
        fail("SNMPv3 采集", f"status={result.status} error={result.error}")
    else:
        ok("SNMPv3 采集成功", f"facts={result.facts}")
        sys_name = result.facts.get("sys_name")
        if sys_name:
            ok(f"sysName = {sys_name}")
        else:
            fail("sysName 缺失")
        ok(f"接口数 = {len(result.interfaces)}")
        for i in result.interfaces[:3]:
            # 真实采集字段：admin_status/oper_status（0=down,1=up），非 mock 的 status
            a = i.get('admin_status')
            o = i.get('oper_status')
            st = 'up' if (o == 1) else 'down'
            ok(f"  接口 {i.get('name')}: oper={st}"
               f" in={i.get('in_octets')} out={i.get('out_octets')}")

    # 错误凭据 → auth_failed
    bad = run_snmpv3_sync(
        host=HOST, username="wrong", auth_key="wrongkey", priv_key="wrongkey",
        auth_algo=AUTH_ALGO, priv_algo=PRIV_ALGO, port=SNMP_PORT,
    )
    if bad.status == "auth_failed":
        ok("错误凭据 → auth_failed")
    else:
        fail("错误凭据分类", f"status={bad.status}")

    # ---------- 2. SSH 只读采集 ----------
    print("\n【2】SSH 只读采集真实执行")
    ssh = asyncio.run(collect_ssh(
        host=HOST, port=SSH_PORT, username=SSH_USER,
        password=SSH_PASS, key_pem=None,
        vendor="linux", host_key_fingerprint=None,
    ))
    if ssh.status == "host_key_unknown":
        ok("首次连接 host key 未知（正确阻断，未 AutoAdd）")
        first_fp = ssh.host_key_fingerprint
        # 匹配后重试
        ssh2 = asyncio.run(collect_ssh(
            host=HOST, port=SSH_PORT, username=SSH_USER,
            password=SSH_PASS, key_pem=None,
            vendor="linux", host_key_fingerprint=first_fp,
        ))
        if ssh2.status == "ok":
            ok("host key 匹配 → 采集成功", f"facts={ssh2.facts}")
        else:
            fail("host key 匹配后采集", ssh2.status)
    elif ssh.status == "ok":
        ok("SSH 采集成功（host key 已匹配）", f"facts={ssh.facts}")
        first_fp = ssh.host_key_fingerprint
    else:
        fail("SSH 采集", f"status={ssh.status} error={ssh.error}")
        first_fp = None

    if first_fp:
        # 错误 host key → mismatch
        bad_fp = "ff" * 16
        ssh3 = asyncio.run(collect_ssh(
            host=HOST, port=SSH_PORT, username=SSH_USER,
            password=SSH_PASS, key_pem=None,
            vendor="linux", host_key_fingerprint=bad_fp,
        ))
        if ssh3.status == "host_key_mismatch":
            ok("host key 不匹配 → host_key_mismatch")
        else:
            fail("host key 不匹配分类", ssh3.status)

    # 错误密码 → auth_failed
    ssh4 = asyncio.run(collect_ssh(
        host=HOST, port=SSH_PORT, username=SSH_USER,
        password="wrongpass", key_pem=None,
        vendor="linux", host_key_fingerprint=first_fp or None,
    ))
    if ssh4.status == "auth_failed":
        ok("SSH 错误密码 → auth_failed")
    else:
        fail("SSH 错误密码分类", ssh4.status)

    # ---------- 3. N2 配置备份（真实读取 + 脱敏） ----------
    print("\n【3】N2 配置备份真实读取（CONFIG_READ_COMMANDS + 脱敏）")
    cfg = asyncio.run(_collect_config_ssh(
        host=HOST, port=SSH_PORT, username=SSH_USER,
        password=SSH_PASS, key_pem=None,
        vendor="linux", host_key_fingerprint=first_fp or None,
        max_bytes=512 * 1024,
    ))
    if cfg.status == "ok":
        ok(f"配置读取成功 command={cfg.command} 行数={len(cfg.full_text.splitlines())}")
        redacted = cfg.redacted
        if len(redacted) < len(cfg.full_text) or redacted:
            ok("脱敏输出非空")
        print(f"  前 6 行脱敏预览:\n{chr(10).join('    ' + l for l in redacted.splitlines()[:6])}")
    else:
        fail("配置备份读取", cfg.status)

    # ---------- 4. N2 配置变化 diff（修改真实配置 → 重采 → diff） ----------
    print("\n【4】N2 配置变化 diff（修改真实配置 → 重采 → 差异行 + 脱敏）")
    diff_result = asyncio.run(_verify_config_change(
        host=HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS,
        vendor="linux", host_key_fingerprint=first_fp or None,
    ))
    if diff_result is True:
        ok("配置变化 → 重新采集 → diff 显示变化行（且含 password 值的行被脱敏）✅")
    else:
        fail("配置变化 diff", str(diff_result))

    # ---------- 5. 失败场景：命令不支持（cisco_ios 命令在 Alpine 上不存在） ----------
    print("\n【5】失败场景：配置命令不支持（cisco_ios show running-config 在 Alpine 不存在）")
    cns = asyncio.run(_collect_config_ssh(
        host=HOST, port=SSH_PORT, username=SSH_USER,
        password=SSH_PASS, key_pem=None,
        vendor="cisco_ios", host_key_fingerprint=first_fp or None,
        max_bytes=512 * 1024,
    ))
    if cns.status == "cmd_not_supported":
        ok("cisco_ios 命令在 Alpine 上不存在 → cmd_not_supported")
    else:
        fail("命令不支持分类", cns.status)

    print()
    if FAILED:
        print(f"结果：{len(FAILED)} 项失败 -> {FAILED}")
        return 1
    print("结果：全部真实环境验证通过 ✅")
    return 0


async def _verify_config_change(host: str, port: int, username: str,
                                password: str, vendor: str,
                                host_key_fingerprint: str | None) -> bool | str:
    """真实修改容器内配置（sshd_config 追加 HostKey 密钥行），重采后校验 diff。

    - 第一份快照来自 CONFIG_READ_COMMANDS['linux'][1] = cat /etc/ssh/sshd_config
    - 修改 sshd_config 追加 'HostKey /etc/ssh/ssh_host_ed25519_key' → 重采 → 应有 add 行
    - HostKey 行含 key 关键字，脱敏后应为 'HostKey ********'
    返回 True=通过；字符串=失败原因。
    """
    import app.services.config_backup as cb_mod
    from app.services.config_backup import _collect_config_ssh, diff_configs

    first = await _collect_config_ssh(
        host=host, port=port, username=username, password=password, key_pem=None,
        vendor=vendor, host_key_fingerprint=host_key_fingerprint, max_bytes=512 * 1024,
    )
    if first.status != "ok" or first.command != "cat /etc/ssh/sshd_config":
        return f"首次采集失败/命令不符: status={first.status} cmd={first.command}"

    # 通过 SSH 真实修改 /etc/ssh/sshd_config（追加一行含 key 关键字、应被脱敏的配置）
    mutate_cmds = [
        "echo '# N3 real change marker' >> /etc/ssh/sshd_config",
        "echo 'HostKey /etc/ssh/ssh_host_ed25519_key' >> /etc/ssh/sshd_config",
    ]
    policy = cb_mod.HostKeyPolicy(host_key_fingerprint)
    try:
        client = await cb_mod._transport_factory.connect(
            host, port, username, password, None, policy)
    except Exception as exc:  # noqa: BLE001
        return f"修改配置连接失败: {exc}"
    try:
        for cmd in mutate_cmds:
            _, stdout, stderr = client.exec_command(cmd, timeout=10)
            stdout.read()
            stderr.read()
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass

    second = await _collect_config_ssh(
        host=host, port=port, username=username, password=password, key_pem=None,
        vendor=vendor, host_key_fingerprint=host_key_fingerprint, max_bytes=512 * 1024,
    )
    if second.status != "ok":
        return f"二次采集失败: {second.status}"

    # diff 校验：应看到新增行，且 HostKey 密钥值已脱敏
    rows = diff_configs(first.redacted, second.redacted)
    add_rows = [r for r in rows if r["kind"] == "add"]
    has_marker = any("N3 real change marker" in r["text"] for r in add_rows)
    has_redacted_key = any("HostKey ********" in r["text"] for r in add_rows)
    leaked = any("/etc/ssh/ssh_host_ed25519_key" in r["text"] and
                 "********" not in r["text"] for r in add_rows)
    if not add_rows or not has_marker or not has_redacted_key or leaked:
        return (f"diff 未显示预期变化/脱敏（add_rows={len(add_rows)} "
                f"marker={has_marker} redacted={has_redacted_key} leaked={leaked}）")
    print(f"  diff 新增行数 = {len(add_rows)}，变化行示例：")
    for r in add_rows[:4]:
        print(f"      +{r['text']}")
    return True


if __name__ == "__main__":
    sys.exit(main())
