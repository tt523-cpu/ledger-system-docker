from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Accounting Management API"
    app_env: str = "dev"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60 * 24
    mysql_user: str = "root"
    mysql_password: str = "root"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_db: str = "accounting"
    auto_handover_enabled: bool = True
    auto_handover_interval_seconds: int = 60
    deepseek_api_key: str | None = None
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    qwen_api_key: str | None = None
    qwen_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_vision_model: str = "qwen3.7-plus"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+mysqldb://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )


settings = Settings()
