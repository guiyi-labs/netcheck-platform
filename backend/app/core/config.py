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

    # ---- AI 诊断增强（可选）----
    ai_diagnosis_enabled: bool = False
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout: float = 30.0

    # ---- 其他 ----
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="NETCHECK_", env_file=".env", extra="ignore")


settings = Settings()