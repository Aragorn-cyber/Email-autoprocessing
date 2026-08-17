from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "邮件 AI 助手"
    database_url: str = "sqlite:///./data/email_ai_assistant.db"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    llm_concurrency: int = Field(default=10, ge=1, le=10)
    llm_max_tokens: int = Field(default=8192, ge=512, le=32768)
    llm_body_char_limit: int = Field(default=4000, ge=500, le=20000)
    llm_retry_backoff_seconds: float = Field(default=1.0, ge=0.0, le=10.0)
    default_scan_window_days: int = Field(default=7, ge=1, le=90)
    important_score_threshold: int = 8
    general_score_threshold: int = 4
    whitelist_senders: str = ""
    blacklist_senders: str = ""

    whitelist_score: int = 5
    deadline_score: int = 3
    action_required_score: int = 2
    blacklist_score: int = -5
    bulk_mail_score: int = -3

    @property
    def whitelist_sender_patterns(self) -> tuple[str, ...]:
        return self._split_patterns(self.whitelist_senders)

    @property
    def blacklist_sender_patterns(self) -> tuple[str, ...]:
        return self._split_patterns(self.blacklist_senders)

    def ensure_local_directories(self) -> None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix) or self.database_url.endswith(":memory:"):
            return
        database_path = Path(self.database_url.removeprefix(prefix))
        database_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _split_patterns(value: str) -> tuple[str, ...]:
        return tuple(item.strip().lower() for item in value.split(",") if item.strip())


@lru_cache
def get_settings() -> ApplicationSettings:
    return ApplicationSettings()

