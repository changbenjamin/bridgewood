import json
from functools import lru_cache

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Bridgewood Agent Trading Leaderboard"
    api_v1_prefix: str = "/v1"
    database_url: str = "sqlite:///./bridgewood.db"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    price_refresh_seconds: int = 15
    snapshot_interval_minutes: int = 2
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_data_url: str = "https://data.alpaca.markets"
    alpaca_equity_feed: str = "iex"
    benchmark_symbol: str = "SPY"
    benchmark_starting_cash: float = 10000.0
    activity_page_size: int = 30
    execution_page_size: int = 50
    max_page_size: int = 100
    signup_rate_limit: int = 5
    signup_rate_limit_window_seconds: int = 60
    agent_create_rate_limit: int = 10
    agent_create_rate_limit_window_seconds: int = 60
    execution_report_rate_limit: int = 60
    execution_report_rate_limit_window_seconds: int = 60

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            raise TypeError("cors_origins must be a list or string.")

        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("cors_origins JSON must decode to a list.")
            return [str(item).strip() for item in parsed if str(item).strip()]

        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
