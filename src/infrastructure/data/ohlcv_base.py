from typing import Protocol, Optional, List, Dict, Union
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


# ==========================
# Dominio: interfaz genérica
# ==========================

class OHLCVService(Protocol):
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
