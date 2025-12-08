import pandas as pd
import numpy as np


class FairValueGapAnalyzer:
    def __init__(self, df: pd.DataFrame,
                 open_col: str = 'Open',
                 high_col: str = 'High',
                 low_col: str = 'Low',
                 close_col: str = 'Close',
                 lookback_period: int = 10,
                 body_multiplier: float = 2.0):
        """
        Enhanced analyzer to detect Fair Value Gaps based on advanced logic

        Args:
            df: DataFrame with OHLC
            open_col, high_col, low_col, close_col: OHLC column names
            lookback_period: Periods to calculate average body size
            body_multiplier: Multiplier to filter by significant body size
        """
        self.original_index = df.index
        self.df = df.copy()
        self.df.reset_index(drop=True, inplace=True)

        self.open_col = open_col
        self.high_col = high_col
        self.low_col = low_col
        self.close_col = close_col
        self.lookback_period = lookback_period
        self.body_multiplier = body_multiplier

        # Initialize result columns
        self.df["fvg_type"] = 0  # 0: No FVG, 1: Bullish, -1: Bearish
        self.df["fvg_start"] = np.nan  # Gap start
        self.df["fvg_end"] = np.nan    # Gap end
        self.df["fvg_size"] = np.nan   # Gap size

    def detect_fvg(self):
        """
        Detects Fair Value Gaps using enhanced logic with body filter
        """
        for i in range(2, len(self.df)):
            # Define the three candles: T-2, T-1, T
            first_high = self.df[self.high_col].iloc[i-2]  # T-2 (first candle)
            first_low = self.df[self.low_col].iloc[i-2]    # T-2 (first candle)

            # T-1 (middle candle)
            middle_open = self.df[self.open_col].iloc[i-1]
            # T-1 (middle candle)
            middle_close = self.df[self.close_col].iloc[i-1]

            third_low = self.df[self.low_col].iloc[i]      # T (third candle)
            third_high = self.df[self.high_col].iloc[i]    # T (third candle)

            # Calculate average body size in the lookback period
            start_idx = max(0, i-1-self.lookback_period)
            end_idx = i-1

            prev_bodies = (self.df[self.close_col].iloc[start_idx:end_idx] -
                           self.df[self.open_col].iloc[start_idx:end_idx]).abs()
            avg_body_size = prev_bodies.mean()

            # Ensure avg_body_size is not zero to avoid false positives
            avg_body_size = avg_body_size if avg_body_size > 0 else 0.001

            # Calculate middle candle body size
            middle_candle_body = abs(middle_close - middle_open)

            # Verify Bullish FVG
            if (third_low > first_high and
                    middle_candle_body >= avg_body_size * self.body_multiplier):

                self.df.at[i, "fvg_type"] = 1
                self.df.at[i, "fvg_start"] = first_high
                self.df.at[i, "fvg_end"] = third_low
                self.df.at[i, "fvg_size"] = third_low - first_high

            # Verify Bearish FVG
            elif (third_high < first_low and
                  middle_candle_body >= avg_body_size * self.body_multiplier):

                self.df.at[i, "fvg_type"] = -1
                self.df.at[i, "fvg_start"] = first_low
                self.df.at[i, "fvg_end"] = third_high
                self.df.at[i, "fvg_size"] = first_low - third_high

    def get_fvg_summary(self):
        """
        Gets a summary of detected FVGs
        """
        bullish_count = (self.df["fvg_type"] == 1).sum()
        bearish_count = (self.df["fvg_type"] == -1).sum()
        total_count = bullish_count + bearish_count

        if total_count > 0:
            avg_bullish_size = self.df[self.df["fvg_type"]
                                       == 1]["fvg_size"].mean()
            avg_bearish_size = self.df[self.df["fvg_type"]
                                       == -1]["fvg_size"].mean()
        else:
            avg_bullish_size = 0
            avg_bearish_size = 0

        return {
            "total_fvgs": total_count,
            "bullish_fvgs": bullish_count,
            "bearish_fvgs": bearish_count,
            "avg_bullish_size": avg_bullish_size,
            "avg_bearish_size": avg_bearish_size
        }

    def analyze(self):
        """
        Runs complete analysis and returns enriched DataFrame
        """
        self.detect_fvg()
        self.df.index = self.original_index
        return self.df
