from __future__ import annotations
from .ohlcv_base import OHLCVService
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Protocol, Optional, List, Dict, Union

import logging

import anyio
import pandas as pd
import yfinance as yf


logger = logging.getLogger(__name__)


# ==========================
# Infraestructura: yfinance
# ==========================

class YFinanceService(OHLCVService):
    DEFAULT_CEDEARS: List[str] = [
        "AAPL.BA", "TSLA.BA", "MSFT.BA", "NVDA.BA", "BABA.BA", "MELI.BA", "SPY.BA", "QQQ.BA",
    ]

    def __init__(
        self,
        default_symbols: Optional[List[str]] = None,
        default_lookback_days: int = 365,
    ) -> None:
        self.default_symbols = default_symbols or self.DEFAULT_CEDEARS
        self.default_lookback_days = default_lookback_days

    # -------- helpers internos --------

    def _default_range(self, lookback_days: Optional[int] = None) -> tuple[str, str]:
        """Rango por defecto [hoy - lookback_days, hoy]."""
        days = lookback_days or self.default_lookback_days
        end = date.today()
        start = end - timedelta(days=days)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    @staticmethod
    def _normalize_symbols(
        symbols: Optional[Union[str, List[str]]]
    ) -> List[str]:
        if symbols is None:
            raise ValueError("symbols no puede ser None aquí")
        if isinstance(symbols, str):
            symbols = [symbols]
        return [s for s in symbols if isinstance(s, str) and s.strip()]

    @staticmethod
    def _normalize_index_tz(df: pd.DataFrame) -> pd.DataFrame:
        """Asegura DatetimeIndex tz-naive y ordenado."""
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)

        if df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_localize(None)

        return df.sort_index()

    def __download_in_batches(
        self,
        symbols: List[str],
        start_str: str,
        end_str: str,
        interval: str,
        batch_size: int = 40,
        use_threads: bool = False,
    ) -> pd.DataFrame:
        """Función síncrona que realmente llama a yfinance."""
        if not symbols:
            return pd.DataFrame()

        parts: List[pd.DataFrame] = []
        failed: List[str] = []

        for i in range(0, len(symbols), batch_size):
            chunk = symbols[i: i + batch_size]

            df = yf.download(
                tickers=chunk,
                start=start_str,
                end=end_str,
                interval=interval,
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=use_threads,
            )

            if df is None or df.empty:
                failed.extend(chunk)
                logger.warning(
                    f"YFinance returned empty data for symbols={chunk}"
                )
                continue

            # Si es un solo ticker y columnas no son MultiIndex, las envolvemos
            if (not isinstance(df.columns, pd.MultiIndex)) and len(chunk) == 1:
                t = chunk[0]
                df = pd.concat({t: df}, axis=1)

            df = self._normalize_index_tz(df)
            parts.append(df)

        if failed:
            logger.warning(
                f"Tickers with no data in range {start_str}–{end_str}: {failed}"
            )

        if not parts:
            return pd.DataFrame()

        # Normalizamos por las dudas todos antes de concatenar
        parts = [self._normalize_index_tz(df) for df in parts if not df.empty]

        if not parts:
            return pd.DataFrame()

        out = pd.concat(parts, axis=1)
        out = out.loc[:, ~out.columns.duplicated()]

        # sanity check de formato
        if not isinstance(out.columns, pd.MultiIndex):
            logger.error(
                "Formato de columnas inesperado en YFinanceService (no es MultiIndex)"
            )

        return out

    # -------- API pública --------

    async def get_ohlcv(
        self,
        symbols: Union[str, List[str], None] = None,
        interval: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data de Yahoo Finance como panel.

        - symbols: string único o lista de símbolos. Si es None, usa default_symbols.
        - interval: '1d', '1h', etc.
        - start/end: datetimes; si no se pasan, usa lookback por defecto.
        """
        if symbols is None:
            symbols_list = self.default_symbols
        else:
            symbols_list = self._normalize_symbols(symbols)

        if not symbols_list:
            logger.warning("get_ohlcv() called without valid symbols")
            return pd.DataFrame()

        if start is None or end is None:
            start_str, end_str = self._default_range()
        else:
            start_str = start.strftime("%Y-%m-%d")
            end_str = end.strftime("%Y-%m-%d")

        df = await anyio.to_thread.run_sync(
            self.__download_in_batches,
            symbols_list,
            start_str,
            end_str,
            interval,
        )

        if df.empty:
            logger.warning(
                f"YFinanceService.get_ohlcv() returned empty DataFrame "
                f"for symbols={symbols_list}, range={start_str}–{end_str}"
            )

        return df

    async def get_lastest_price(
        self,
        symbol: str,
        interval: str = "1h",
    ) -> Optional[float]:
        """
        Devuelve el último precio conocido para el símbolo dado.
        Si no hay datos, devuelve None.
        """
        df = await self.get_ohlcv(
            symbols=symbol,
            interval=interval,
            start=datetime.now() - timedelta(days=3),
            end=datetime.now(),
        )

        if df.empty:
            logger.warning(
                f"No OHLCV data found for symbol {symbol} "
                f"in interval {interval}"
            )
            return None

        try:
            last_close = df[(symbol, "Close")].iloc[-1]
            return float(last_close)
        except Exception as e:
            logger.error(
                f"Error getting latest price for {symbol} from OHLCV: {e}"
            )
            return None
