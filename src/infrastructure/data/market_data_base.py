from typing import Protocol, Optional, List, Dict, Union
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


# ==========================
# Dominio: interfaz genérica
# ==========================

@dataclass
class OHLCVDataPoint:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class ArbPair:
    local_ba: str      # "YPFD.BA"
    foreign_us: str    # "YPF"
    ratio: float
    weight: float = 1.0
    benchmark: bool = False


@dataclass(frozen=True)
class ArbitrageOpportunity:
    local_ba: str
    foreign_us: str
    fx_impl: float
    ccl_teo: float
    delta_ars: float
    ts_ba: pd.Timestamp
    ts_us: pd.Timestamp


class MarketDataService(Protocol):
    async def get_ohlcv(
        self,
        symbols: Union[str, List[str]],
        interval: str = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Devuelve un panel OHLCV en formato:
            index: DatetimeIndex (tz-naive, ordenado)
            columns: MultiIndex [symbol, field]  (por ej. ('AAPL.BA', 'Open'))
        """
        ...

    async def get_lastest_price(
        self,
        symbol: str,
        interval: str = "1h",
    ) -> Optional[float]:
        """
        Devuelve el último precio conocido para el símbolo dado.
        Si no hay datos, devuelve None.
        """
        ...

    # ---- arbitraje ----
    async def get_theoretical_ccl(
        self,
        benchmarks: List[ArbPair],
        interval: str = "5m",
        max_ts_diff_minutes: int = 10,
        lookback_days: int = 10,
        min_required_pairs: int = 2,
    ) -> float: ...

    async def detect_arbitrage_opportunities(
        self,
        pairs: List[ArbPair],
        benchmarks: List[ArbPair],
        interval: str = "5m",
        max_ts_diff_minutes: int = 10,
        lookback_days: int = 10,
        min_delta_ars: float = 40.0,
    ) -> List[ArbitrageOpportunity]: ...
