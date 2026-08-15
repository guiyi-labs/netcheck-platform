from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "netcheck-backend"
    version: str = "0.2.0"
    database_url: str = "sqlite:///./data/netcheck.db"
    reports_dir: str = "/app/reports"
    backup_dir: str = "/app/backups"

    # ---- 检测参数 ----
    ping_timeout: float = 3.0
    tcp_timeout: float = 3.0
    http_timeout: float = 5.0
    slow_response_threshold: float = 2000.0
    # 巡检执行并发：同一运行内并行检测的资产数
    check_concurrency: int = 8
    # 待执行运行队列上限：超过后新的运行直接标记 failed（避免排队堆积）
    run_queue_maxsize: int = 1000
    # TLS 证书检测：剩余天数低于该值判定为即将过期（警告）
    tls_expiry_warning_days: int = 30

    # ---- 登录安全 ----
    token_ttl_hours: float = 24.0
    login_max_attempts: int = 5
    login_lock_minutes: float = 15.0
    password_min_length: int = 8

    # ---- 告警通知（可选）----
    notification_enabled: bool = False
    notification_min_level: str = "warning"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_use_ssl: bool = True
    webhook_url: str = ""
    webhook_headers: str = ""
    # Webhook 平台适配：generic（通用 JSON）/ dingtalk（钉钉）/ wecom（企业微信）/ feishu（飞书）
    webhook_scheme: str = "generic"

    # ---- AI 诊断增强（可选）----
    ai_diagnosis_enabled: bool = False
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout: float = 30.0

    # ---- 设备采集（N1：SNMPv3 / SSH 只读）----
    # 凭据加密密钥（AES-256-GCM）；不设置时凭据只加密为占位标记并标记不可用
    secret_key: str = ""
    # SNMPv3 采集上限
    snmp_timeout: float = 5.0
    snmp_retries: int = 1
    snmp_max_interfaces: int = 64
    snmp_max_requests: int = 30
    # SSH 采集上限
    ssh_timeout: float = 10.0
    ssh_max_output_bytes: int = 524288
    # 单次批量采集设备数上限
    device_collect_max_batch: int = 8
    # 配置快照保留上限（N2.1 P1）：每台设备保留最新 N 份，超出清理最旧
    config_snapshot_retention: int = 20
    # 配置 diff 查询上限（N2.1 P1）：最大返回上下文行数与总行数
    config_diff_max_rows: int = 2000
    config_diff_context_lines: int = 3

    # ---- 其他 ----
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="NETCHECK_", env_file=".env", extra="ignore")


settings = Settings()