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
    rest_base_url: str = Field(default="https://api.hyperliquid-testnet.xyz")
    websocket_base_url: str = Field(default="wss://api.hyperliquid-testnet.xyz/ws")
    log_level: str = Field(default="INFO")
    sqlite_path: str = Field(default="./data/hyperbot.db")
    account_address: str | None = Field(default=None)
    api_private_key: str | None = Field(default=None)
    api_testnet: bool = Field(default=True)
    grid_levels: int = Field(default=8)
    grid_range_pct: float = Field(default=0.04)
    grid_density_power: float = Field(default=1.5)
    grid_size_power: float = Field(default=1.0)
    grid_base_size: float = Field(default=0.01)
    grid_compound: bool = Field(default=False)
    grid_paper_mode: bool = Field(default=True)
    grid_recenter_threshold: float = Field(default=0.01)
    grid_recenter_cooldown: float = Field(default=60.0)
    grid_leverage_min: float = Field(default=1.5)
    grid_leverage_max: float = Field(default=5.0)

    def model_post_init(self, __context: object) -> None:
        if self.api_testnet:
            self.rest_base_url = "https://api.hyperliquid-testnet.xyz"
            self.websocket_base_url = "wss://api.hyperliquid-testnet.xyz/ws"
        else:
            self.rest_base_url = "https://api.hyperliquid.xyz"
            self.websocket_base_url = "wss://api.hyperliquid.xyz/ws"

    def get_database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path}"
