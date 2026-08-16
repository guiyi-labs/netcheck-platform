#!/bin/sh
#
# H3C Comware V7 CLI 仿真交互服务（受限 shell）。
#
# 用途：为 netcheck 采集器提供「忠实于 Comware V7 输出格式」的命令文本，
#       通过真实 SSH（OpenSSH）传输层验证 h3c_comware 适配器解析。
#
# 边界如实声明（见 docs/final-delivery/h3c-real-verification.md）：
#   - 本服务为仿真载体：SSH 服务端是真实 OpenSSH，CLI 文本按 H3C
#     Comware V7 官方输出样张忠实还原；
#   - 验证对象是「采集器在真实 SSH/SNMP 传输链路上的端到端解析」，
#     不是「H3C Comware 操作系统兼容性」。
#
# 行为：
#   - 以本脚本作为 SSH 用户 shell（OpenSSH 以 `shell -c "cmd"` 调用）；
#     * -c 模式：单条命令，打印应答后退出（paramiko exec_command 路径）
#     * 交互模式：逐行读入，提示符 H3C>
#   - 仅允许 display 系列只读命令（与采集器 allowlist 一致）；
#   - 未知/可写命令返回 Comware 风格错误：
#     `% Unrecognized command found at '^' position.`
set -e

# 设备标识（可通过环境变量注入，便于复现脚本配置）
SYSNAME="${H3C_SYSNAME:-h3c-core-sim}"
SYS_VERSION="${H3C_VERSION:-H3C Comware Software, Version 7.1.070, Release 1118P02}"
SYS_DESCR="${H3C_DESCR:-H3C S5560X-30C-EI}"

# 单条命令应答（追加换行）
respond() {
    cmd="$1"
    case "$cmd" in
        "display version")
            printf 'H3C Comware Software, Version 7.1.070, Release 1118P02\n'
            printf 'Copyright (c) 2004-2021 New H3C Technologies Co., Ltd. All rights reserved.\n'
            printf 'H3C %s uptime is 2 weeks, 1 day, 3 hours, 4 minutes\n' "$SYS_DESCR"
            ;;
        "display interface brief")
            printf 'Brief information on interfaces in route mode:\n'
            printf 'Link: ADM - administratively down; Stby - standby\n'
            printf 'Interface            Link         Speed   Duplex Type PVID Description\n'
            printf 'GE1/0/1              UP           1G      F(a)   A    1    to-core\n'
            printf 'GE1/0/2              DOWN         1G      F(a)   A    1    --\n'
            printf 'GE1/0/3              UP           10G     F(a)   A    1    to-server\n'
            printf 'Vlan-interface1      UP           1G      F(a)   R    --   --\n'
            printf 'LoopBack0            UP           1G      F(a)   L    --   --\n'
            ;;
        "display ip routing-table")
            printf 'Destinations : 5        Routes : 5\n'
            printf 'Destination/Mask   Proto   Pre  Cost        NextHop         Interface\n'
            printf '0.0.0.0/0          Static  60   0           10.0.0.254       Vlan-interface1\n'
            printf '10.0.0.0/24        Direct  0    0           10.0.0.1         Vlan-interface1\n'
            printf '192.168.1.0/24     Direct  0    0           192.168.1.1      Vlan-interface1\n'
            ;;
        "display ip routing-table static")
            printf 'Summary count : 1\n'
            printf 'Destination/Mask   Proto   Pre  Cost        NextHop         Interface\n'
            printf '0.0.0.0/0          Static  60   0           10.0.0.254       Vlan-interface1\n'
            ;;
        "display clock")
            printf '2026-08-16 09:30:00\n'
            printf 'Friday\n'
            printf 'Time Zone : China Standard Time\n'
            ;;
        *)
            printf '%% Unrecognized command found at '\''^'\'' position.\n'
            ;;
    esac
}

# -c 模式：paramiko exec_command("display ...") -> shell -c "display ..."
if [ "$#" -ge 1 ] && [ "$1" = "-c" ]; then
    respond "${2:-}"
    exit 0
fi
# 单参数（无引号时可能把整串当单个参数）
if [ "$#" -eq 1 ] && [ "$1" != "-c" ]; then
    respond "$1"
    exit 0
fi

# 交互模式
prompt="H3C> "
printf "%s" "$prompt"
while IFS= read -r line; do
    line=$(printf '%s' "$line" | tr -d '\r')
    case "$line" in
        "quit" | "exit")
            printf 'logout\n'
            exit 0
            ;;
        "")
            ;;
        *)
            respond "$line"
            ;;
    esac
    printf "%s" "$prompt"
done

exit 0