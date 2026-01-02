from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union, Tuple

import logging

import anyio
import pandas as pd
import yfinance as yf


logger = logging.getLogger(__name__)


# ======================================================
# Dominio (para arbitraje): modelos simples y tipados
# ======================================================

@dataclass(frozen=True)
class ArbPair:
    """
    Par CEDEAR (ARS) vs subyacente/ADR (USD).

    ratio = cuántas acciones subyacentes representa 1 CEDEAR.
    (Ej: si 1 CEDEAR = 10 acciones US, ratio=10.0)
    """
    local_ba: str        # ej "YPFD.BA"
    foreign_us: str      # ej "YPF"
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

    @property
    def abs_delta_ars(self) -> float:
        return abs(self.delta_ars)

    @property
    def side(self) -> str:
        # delta > 0 => FX_impl > CCL_teo => CEDEAR "caro" vs benchmark
        # delta < 0 => CEDEAR "barato" vs benchmark
        return "SELL_CEDEAR" if self.delta_ars > 0 else "BUY_CEDEAR"


# ======================================================
# Infraestructura: yfinance (tu servicio + arbitraje)
# ======================================================

class YFinanceService:
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

    # --------------------------
    # API EXISTENTE (NO TOCAR)
    # --------------------------

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
        - interval: '1d', '1h', '5m', etc.
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
            start, end = self._default_range(self.default_lookback_days)
        else:
            start = start.strftime("%Y-%m-%d")
            end = end.strftime("%Y-%m-%d")

        df = await anyio.to_thread.run_sync(
            self.__download_in_batches,
            symbols_list,
            start,
            end,
            interval,
        )

        if df.empty:
            logger.warning(
                f"YFinanceService.get_ohlcv() returned empty DataFrame "
                f"for symbols={symbols_list}, range={start}–{end}"
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

    # --------------------------
    # Helpers internos existentes
    # --------------------------

    def _default_range(self, lookback_days: int) -> Tuple[str, str]:
        end = datetime.now().date()
        start = end - timedelta(days=lookback_days)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    @staticmethod
    def _normalize_symbols(symbols: Union[str, List[str]]) -> List[str]:
        if isinstance(symbols, str):
            symbols = [symbols]
        return [s for s in symbols if isinstance(s, str) and s.strip()]

    @staticmethod
    def _normalize_index_tz(df: pd.DataFrame) -> pd.DataFrame:
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
                    f"YFinance returned empty data for symbols={chunk}")
                continue

            if (not isinstance(df.columns, pd.MultiIndex)) and len(chunk) == 1:
                t = chunk[0]
                df = pd.concat({t: df}, axis=1)

            df = self._normalize_index_tz(df)
            parts.append(df)

        if failed:
            logger.warning(
                f"Tickers with no data in range {start_str}–{end_str}: {failed}")

        if not parts:
            return pd.DataFrame()

        parts = [self._normalize_index_tz(df) for df in parts if not df.empty]
        if not parts:
            return pd.DataFrame()

        out = pd.concat(parts, axis=1)
        out = out.loc[:, ~out.columns.duplicated()]

        if not isinstance(out.columns, pd.MultiIndex):
            logger.error(
                "Unexpected columns format (expected MultiIndex) in YFinanceService")

        return out

    # ======================================================
    # ===================== ARBITRAJE ======================
    # ======================================================

    @staticmethod
    def _normalize_index_to_utc(df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza el índice a tz-aware en UTC, ordenado.
        - Si el índice viene tz-aware: tz_convert('UTC')
        - Si viene tz-naive: asumimos que ya está en UTC y tz_localize('UTC')
        (esto es una suposición; ver nota abajo)
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)

        if df.index.tz is None:
            # OJO: suposición; si Yahoo te entrega naive pero en hora local del exchange,
            # esto puede estar mal. En ese caso hay que asignar tz por exchange.
            df = df.copy()
            df.index = df.index.tz_localize("UTC")
        else:
            df = df.copy()
            df.index = df.index.tz_convert("UTC")

        return df.sort_index()

    @staticmethod
    def _download_last_close_ts_sync(
        symbol: str,
        interval: str,
        lookback_days: int,
    ) -> Optional[Tuple[float, pd.Timestamp]]:
        """
        Descarga OHLCV del símbolo y devuelve (último close, timestamp última vela).
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_days)

        df = yf.download(
            tickers=symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=False,
        )

        if df is None or df.empty:
            return None

        df = YFinanceService._normalize_index_to_utc(df)

        if isinstance(df.columns, pd.MultiIndex):
            if (symbol, "Close") not in df.columns:
                print(
                    f"(symbol,'Close') not in columns for {symbol}: {df.columns}")
                return None
            ser = df[(symbol, "Close")].dropna()
        else:
            if "Close" not in df.columns:
                print(f"'Close' not in columns for {symbol}: {df.columns}")
                return None
            ser = df["Close"].dropna()

        if ser.empty:
            return None

        ts = ser.index[-1]
        close = float(ser.iloc[-1])
        return close, ts

    async def _latest_close_and_ts_yf(
        self,
        symbol: str,
        interval: str,
        lookback_days: int,
    ) -> Optional[Tuple[float, pd.Timestamp]]:
        """
        Wrapper async: ejecuta el sync downloader en thread.
        """
        return await anyio.to_thread.run_sync(
            self._download_last_close_ts_sync,
            symbol,
            interval,
            lookback_days,
        )

    @staticmethod
    def _implied_fx(p_ba: float, p_us: float, ratio: float) -> Optional[float]:
        if p_ba <= 0 or p_us <= 0 or ratio <= 0:
            return None
        return (p_ba * ratio) / p_us

    @staticmethod
    def _ts_diff_minutes(a: pd.Timestamp, b: pd.Timestamp) -> float:
        return abs((a - b).total_seconds()) / 60.0

    async def get_theoretical_ccl(
        self,
        benchmarks: List[ArbPair],
        interval: str = "5m",
        lookback_days: int = 10,
        min_required_pairs: int = 2,
    ) -> float:
        """
        CCL teórico ponderado (ARS/USD) usando benchmarks (pares ADR/CEDEAR).
        """
        fx_w: List[Tuple[float, float]] = []

        for p in benchmarks:
            close_ba_ts = await self._latest_close_and_ts_yf(p.local_ba, interval, lookback_days)
            close_us_ts = await self._latest_close_and_ts_yf(p.foreign_us, interval, lookback_days)
            if not close_ba_ts or not close_us_ts:
                continue

            p_ba, ts_ba = close_ba_ts
            p_us, ts_us = close_us_ts

            # TODO: hay que llevar ambas velas al mismo horario UTC y asegurarse que corresponden al mismo momento de tiempo.
            # if self._ts_diff_minutes(ts_ba, ts_us) > max_ts_diff_minutes:
            #     continue

            fx = self._implied_fx(p_ba, p_us, p.ratio)
            if fx is None:
                continue

            fx_w.append((fx, p.weight))

        if len(fx_w) < min_required_pairs:
            raise ValueError(
                f"Not enough benchmark pairs to compute theoretical CCL. "
                f"got={len(fx_w)} required={min_required_pairs}"
            )

        wsum = sum(w for _, w in fx_w)
        if wsum <= 0:
            raise ValueError("Invalid benchmark weights sum")

        ccl = sum(fx * w for fx, w in fx_w) / wsum
        return float(ccl)

    async def detect_arbitrage_opportunities(
        self,
        pairs: List[ArbPair],
        benchmarks: List[ArbPair],
        interval: str = "5m",
        lookback_days: int = 10,
        min_delta_ars: float = 50.0,
    ) -> List[ArbitrageOpportunity]:
        """
        Oportunidad si |FX_impl - CCL_teo| >= min_delta_ars (ej 50 pesos).
        """
        ccl_teo = await self.get_theoretical_ccl(
            benchmarks=benchmarks,
            interval=interval,
            lookback_days=lookback_days,
        )

        opps: List[ArbitrageOpportunity] = []

        for p in pairs:
            close_ba_ts = await self._latest_close_and_ts_yf(p.local_ba, interval, lookback_days)
            close_us_ts = await self._latest_close_and_ts_yf(p.foreign_us, interval, lookback_days)
            if not close_ba_ts or not close_us_ts:
                continue

            p_ba, ts_ba = close_ba_ts
            p_us, ts_us = close_us_ts

            # TODO: hay que llevar ambas velas al mismo horario UTC y asegurarse que corresponden al mismo momento de tiempo.
            # if self._ts_diff_minutes(ts_ba, ts_us) > max_ts_diff_minutes:
            #     continue

            fx = self._implied_fx(p_ba, p_us, p.ratio)
            if fx is None:
                continue

            delta = fx - ccl_teo
            if abs(delta) >= min_delta_ars:
                opps.append(ArbitrageOpportunity(
                    local_ba=p.local_ba,
                    foreign_us=p.foreign_us,
                    fx_impl=float(fx),
                    ccl_teo=float(ccl_teo),
                    delta_ars=float(delta),
                    ts_ba=ts_ba,
                    ts_us=ts_us,
                ))

        opps.sort(key=lambda o: o.abs_delta_ars, reverse=True)
        return opps
