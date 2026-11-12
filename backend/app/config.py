"""Configuración. El trading real no tiene ruta de código en v1: real_trading_allowed es siempre False."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/radar.db"
    data_dir: str = "./data"
    binance_spot_url: str = "https://data-api.binance.vision"
    binance_futures_url: str = "https://fapi.binance.com"
    http_timeout: float = 10.0
    use_system_trust: bool = False  # USE_SYSTEM_TRUST=true en Windows con inspección TLS
    cookie_secure: bool = False  # true cuando se sirva por HTTPS con dominio
    session_ttl_hours: int = 12
    real_trading_enabled: bool = False
    real_order_execution_enabled: bool = False
    paper_auto_trading_enabled: bool = False
    research_workers: int = 1
    paper_initial_usdt: float = 100.0
    algo_allocation_fraction: float = 0.05
    paper_fee_rate: float = 0.001
    paper_slippage_bps: float = 5.0
    timezone_display: str = "America/Lima"

    @property
    def real_trading_allowed(self) -> bool:
        """Siempre False en v1: el camino live no está implementado."""
        return False

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
