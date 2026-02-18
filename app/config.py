from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "PixelDock32"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    secret_key: str = "change-me"
    access_token_expire_minutes: int = 720
    admin_username: str = "admin"
    admin_password: str = "admin1234"

    database_url: str = "sqlite+aiosqlite:///./pixeldock32.db"

    tz: str = "Europe/Vienna"

    led_count: int = 256
    led_pin: int = 18
    led_freq_hz: int = 800000
    led_dma: int = 10
    led_invert: bool = False
    led_brightness: int = 64
    led_channel: int = 0

    panel_rows: int = 8
    panel_columns: int = 32
    chain_panels: int = 4
    panel_width: int = 8
    panel_height: int = 8
    data_starts_right: bool = True
    serpentine: bool = True
    first_pixel_offset: int = 0

    btc_api_url: str = "https://api.coingecko.com/api/v3/simple/price"
    btc_block_height_api_url: str = "https://blockstream.info/api/blocks/tip/height"
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_lat: float = 47.2682
    weather_lon: float = 11.3923
    weather_postcode: str = "6020"
    weather_country: str = "AT"

    poll_btc_seconds: int = Field(default=60, ge=15)
    poll_weather_seconds: int = Field(default=300, ge=60)
    render_fps: int = Field(default=20, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
