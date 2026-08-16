# H3C Comware V7 仿真服务节点镜像（P1 真实验证载体）
#
# 说明：本镜像用于验证 netcheck 的 h3c_comware 采集适配器在【真实 SSH/SNMP
# 传输链路】上的端到端解析。载体为仿真服务（OpenSSH 真实传输 + 忠实 Comware
# V7 CLI 文本 + net-snmp H3C 风格 sysDescr），并非真实 H3C 设备（见
# docs/final-delivery/h3c-real-verification.md 的边界声明）。
#
# 凭据均为文档测试值（monitor / netcheckauth / netcheckpriv / simpass），
# 可通过环境变量在运行时注入覆盖，不固化自定义口令。
ARG ALPINE_TAG=3.22
FROM alpine:${ALPINE_TAG}

# 凭据（默认=文档测试值；可用环境变量注入覆盖）
ARG SSH_USER=monitor
ARG SSH_PASSWORD=simpass
ARG SNMP_USER=monitor
ARG SNMP_AUTH_KEY=netcheckauth
ARG SNMP_PRIV_KEY=netcheckpriv

RUN apk add --no-cache openssh net-snmp net-snmp-tools python3 py3-pip \
    && ssh-keygen -A \
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    && echo "Port 22" >> /etc/ssh/sshd_config \
    && echo "Port 2222" >> /etc/ssh/sshd_config

# 平台采集器依赖（SNMP 验证：pysnmp 走真实 UDP，与宿主 venv 版本一致；
# pydantic-settings/sqlalchemy 用于加载采集器模块）
RUN pip3 install --no-cache-dir --break-system-packages \
        pysnmp==7.1.28 pydantic-settings==2.14.2 sqlalchemy==2.0.51 \
        cryptography==50.0.0 \
    && python3 -c "import pysnmp, pydantic_settings, sqlalchemy, cryptography; print('collector deps ok', cryptography.__version__)"

# Comware CLI 仿真作为用户 shell：paramiko exec_command 经 OpenSSH
# 以 `shell -c "cmd"` 路由到仿真脚本（ForceCommand 会丢弃 exec_command
# 的命令参数，故不能用于本链路）。
COPY comware-cli-sim.sh /usr/local/bin/comware-cli-sim.sh
RUN chmod 755 /usr/local/bin/comware-cli-sim.sh \
    && adduser -D -s /usr/local/bin/comware-cli-sim.sh "$SSH_USER" \
    && echo "$SSH_USER:$SSH_PASSWORD" | chpasswd

# SNMPv3 authPriv 用户 + H3C 风格 sysDescr/sysName（环境变量可覆盖）
RUN cat > /etc/snmp/snmpd.conf <<SNMP
createUser ${SNMP_USER} SHA-256 ${SNMP_AUTH_KEY} AES ${SNMP_PRIV_KEY}
rouser ${SNMP_USER} priv
sysLocation sim-lab
sysContact p1-verification
SNMP

COPY h3c-entry.sh /h3c-entry.sh
RUN chmod +x /h3c-entry.sh

ENTRYPOINT ["sh", "/h3c-entry.sh"]