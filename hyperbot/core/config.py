from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HYPERBOT_", extra="ignore")

    app_name: str = Field(default="hyperbot")
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")
    exchange_name: str = Field(default="hyperliquid")
    enable_websocket: bool = Field(default=True)
    rest_base_url: str = Field(default="https://api.hyperliquid.xyz")
    websocket_base_url: str = Field(default="wss://api.hyperliquid.xyz/ws")
    log_level: str = Field(default="INFO")
    sqlite_path: str = Field(default="./data/hyperbot.db")
    api_wallet_address: str | None = Field(default=None)
    api_private_key: str | None = Field(default=None)
    api_testnet: bool = Field(default=False)

    def get_database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path}"
