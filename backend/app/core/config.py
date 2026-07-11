from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "netcheck-backend"
    version: str = "0.1.0"
    database_url: str = "sqlite:///./data/netcheck.db"
    reports_dir: str = "/app/reports"
    ping_timeout: float = 3.0
    tcp_timeout: float = 3.0
    http_timeout: float = 5.0
    slow_response_threshold: float = 2000.0

    model_config = SettingsConfigDict(env_prefix="NETCHECK_")


settings = Settings()
