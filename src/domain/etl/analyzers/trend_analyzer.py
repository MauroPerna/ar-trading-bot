import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    def __init__(self, df: pd.DataFrame, price_col: str = 'Close', window: int = 30):
        self.df = df.copy()
        self.price_col = price_col
        self.window = window

        if len(self.df) < self.window:
            self.window = max(5, len(self.df) // 2)
            logger.warning(
                f"⚠️ Window ajustado a {self.window} debido a pocos datos"
            )

    def compute_rolling_slope(self):
        """
        Calcula pendiente rolling con mínimos cuadrados usando numpy.
        """
        original_length = len(self.df)
        slopes = np.full(original_length, np.nan)

        if original_length < self.window:
            logger.warning(
                f"⚠️ No hay suficientes datos para window={self.window}, length={original_length}"
            )
            self.df['slope'] = slopes
            return self.df

        try:
            x = np.arange(self.window, dtype=float)
            x_mean = x.mean()
            x_var = ((x - x_mean) ** 2).sum()

            for i in range(self.window, original_length):
                y = self.df[self.price_col].iloc[i -
                                                 self.window:i].values.astype(float)

                if np.isnan(y).all():
                    slopes[i] = np.nan
                    continue

                y_mean = np.nanmean(y)
                cov = np.nansum((x - x_mean) * (y - y_mean))
                slope = cov / x_var if x_var != 0 else np.nan
                slopes[i] = slope

            self.df['slope'] = slopes
            logger.info(
                f"✅ Rolling slopes calculated: {np.sum(~np.isnan(slopes))} valid values"
            )

        except Exception as e:
            logger.error(f"❌ Error calculating rolling slopes: {e}")
            self.df['slope'] = slopes

        return self.df

    def compute_trend_signal(self):
        """
        Define tendencia local asegurando longitud correcta
        """
        if 'slope' not in self.df.columns:
            logger.warning(
                "⚠️ No hay columna 'slope', asignando trend_signal=0")
            self.df['trend_signal'] = 0
            return self.df

        try:
            valid_slopes = self.df['slope'].dropna()

            if len(valid_slopes) == 0:
                logger.warning(
                    "⚠️ No hay slopes válidas, asignando trend_signal=0")
                self.df['trend_signal'] = 0
                return self.df

            threshold = valid_slopes.std() * 0.5

            def trend_signal_func(x):
                if pd.isna(x):
                    return 0
                elif x > threshold:
                    return 1
                elif x < -threshold:
                    return -1
                else:
                    return 0

            self.df['trend_signal'] = self.df['slope'].apply(trend_signal_func)

            assert len(self.df['trend_signal']) == len(self.df)

            logger.info(
                f"✅ Trend signals calculated: threshold={threshold:.6f}")

        except Exception as e:
            logger.error(f"❌ Error calculating trend signals: {e}")
            self.df['trend_signal'] = 0

        return self.df

    def analyze(self):
        original_length = len(self.df)
        logger.info(
            f"🔍 TrendAnalyzer iniciando con {original_length} registros, window={self.window}"
        )

        try:
            self.compute_rolling_slope()
            self.compute_trend_signal()

            final_length = len(self.df)
            if final_length != original_length:
                logger.error(
                    f"❌ Length mismatch después del análisis: {final_length} vs {original_length}"
                )
                raise ValueError(
                    f"DataFrame length changed from {original_length} to {final_length}"
                )

            logger.info(
                f"✅ TrendAnalyzer completed successfully: {final_length} records"
            )
            return self.df

        except Exception as e:
            logger.error(f"❌ TrendAnalyzer failed: {e}")
            self.df['slope'] = np.nan
            self.df['trend_signal'] = 0
            return self.df
