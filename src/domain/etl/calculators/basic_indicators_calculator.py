import pandas as pd
import pandas_ta as ta
import numpy as np
import logging

logger = logging.getLogger(__name__)

ALL_SUPPORTED_INDICATORS = [
    "rsi", "stochrsi", "macd", "willr", "cci", "mfi", "uo",
    "ema", "sma", "adx", "psar", "slope",
    "obv", "cmf", "vwap", "ad", "eom", "volume_spike",
    "bbands", "atr", "kc",
]


class IndicatorCalculator:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.original_length = len(self.df)

        # --- Normalización del índice para evitar problemas con VWAP & cía ---
        if not isinstance(self.df.index, pd.DatetimeIndex):
            try:
                self.df.index = pd.to_datetime(self.df.index)
                logger.info(
                    "🕒 Index converted to DatetimeIndex successfully")
            except Exception as e:
                logger.warning(
                    f"⚠️ Could not convert index to DatetimeIndex: {e}"
                )

        # Si es DatetimeIndex, lo ordenamos y quitamos duplicados
        if isinstance(self.df.index, pd.DatetimeIndex):
            if not self.df.index.is_monotonic_increasing:
                self.df = self.df.sort_index()
                logger.info(
                    "📅 Index sorted ascending for time-based indicators")

            if self.df.index.has_duplicates:
                before = len(self.df)
                self.df = self.df[~self.df.index.duplicated(keep="first")]
                after = len(self.df)
                logger.warning(
                    f"⚠️ Index had duplicates, removed "
                    f"{before - after} duplicate rows"
                )

        # Validación de columnas requeridas
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [
            col for col in required_columns if col not in self.df.columns]

        if missing_columns:
            logger.warning(f"⚠️ Missing columns: {missing_columns}")

    # -------------------- MOMENTUM --------------------

    def calculate_momentum_indicators(self, indicators: list[str]):
        try:
            logger.info("📈 Calculating momentum indicators...")

            if "rsi" in indicators and len(self.df) >= 14:
                self.df.ta.rsi(length=14, append=True)

            if "stochrsi" in indicators and len(self.df) >= 14:
                self.df.ta.stochrsi(length=14, append=True)

            if "macd" in indicators and len(self.df) >= 26:
                self.df.ta.macd(append=True)

            if "willr" in indicators and len(self.df) >= 14:
                self.df.ta.willr(length=14, append=True)

            if "cci" in indicators and len(self.df) >= 20:
                self.df.ta.cci(length=20, append=True)

            if "mfi" in indicators and len(self.df) >= 14:
                self.df.ta.mfi(length=14, append=True)

            if "uo" in indicators and len(self.df) >= 28:
                self.df.ta.uo(append=True)

        except Exception as e:
            logger.error(f"❌ Error en momentum indicators: {e}")

    # -------------------- TENDENCIA --------------------

    def calculate_trend_indicators(self, indicators: list[str]):
        try:
            logger.info("📊 Calculating trend indicators...")

            if "ema" in indicators:
                for period in [5, 8, 21, 50, 200]:
                    if len(self.df) >= period:
                        self.df.ta.ema(length=period, append=True)

            if "sma" in indicators:
                for period in [5, 8, 21, 50, 200]:
                    if len(self.df) >= period:
                        self.df.ta.sma(length=period, append=True)

            if "adx" in indicators and len(self.df) >= 14:
                self.df.ta.adx(length=14, append=True)

            if "psar" in indicators and len(self.df) >= 10:
                self.df.ta.psar(append=True)

        except Exception as e:
            logger.error(f"❌ Error en trend indicators: {e}")

    # -------------------- VOLUMEN --------------------

    def calculate_volume_indicators(self, indicators: list[str]):
        try:
            logger.info("📦 Calculating volume indicators...")

            if "obv" in indicators:
                self.df.ta.obv(append=True)

            if "cmf" in indicators and len(self.df) >= 20:
                self.df.ta.cmf(length=20, append=True)

            if "vwap" in indicators:
                if isinstance(self.df.index, pd.DatetimeIndex) and self.df.index.is_monotonic_increasing:
                    self.df.ta.vwap(append=True)
                else:
                    logger.warning(
                        "[!] VWAP no calculado: se requiere un DatetimeIndex ordenado"
                    )

            if "ad" in indicators:
                self.df.ta.ad(append=True)

            if "eom" in indicators and len(self.df) >= 14:
                self.df.ta.eom(length=14, append=True)

            if "volume_spike" in indicators and len(self.df) >= 20:
                self.df.ta.sma(length=20, append=True, suffix="VOL")
                self.df['volume_spike'] = (
                    self.df['volume'] > self.df['SMA_20_VOL'] * 2.0
                )
                logger.info("✅ Volume spike calculated")

        except Exception as e:
            logger.error(f"❌ Error en volume indicators: {e}")

    # -------------------- VOLATILIDAD --------------------

    def calculate_volatility_indicators(self, indicators: list[str]):
        try:
            logger.info("⚡ Calculating volatility indicators...")

            if "bbands" in indicators and len(self.df) >= 20:
                self.df.ta.bbands(length=20, std=2, append=True)

            if "atr" in indicators and len(self.df) >= 14:
                self.df.ta.atr(length=14, append=True)

            if "kc" in indicators and len(self.df) >= 20:
                self.df.ta.kc(length=20, scalar=2, append=True)

        except Exception as e:
            logger.error(f"❌ Error en volatility indicators: {e}")

    # -------------------- VALIDACIÓN --------------------

    def validate_length(self):
        current_length = len(self.df)
        if current_length != self.original_length:
            logger.error(
                f"❌ Length mismatch: {self.original_length} → {current_length}"
            )
            raise ValueError("DataFrame length changed")
        logger.info("✅ Length validation successful")

    # -------------------- ENTRYPOINT --------------------

    def apply(self, indicators: list[str] = []) -> pd.DataFrame:
        logger.info(
            f"🚀 IndicatorAnalyzer starting with {self.original_length} records"
        )

        if not indicators:
            logger.info("🔍 No indicators specified, using all")
            indicators = ALL_SUPPORTED_INDICATORS

        try:
            self.calculate_momentum_indicators(indicators)
            self.calculate_trend_indicators(indicators)
            self.calculate_volume_indicators(indicators)
            self.calculate_volatility_indicators(indicators)
            self.validate_length()
            logger.info("✅ IndicatorAnalyzer completed")
            return self.df

        except Exception as e:
            logger.error(f"❌ IndicatorAnalyzer failed: {e}")
            raise
