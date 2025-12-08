import pandas as pd
import numpy as np
import pandas_ta as ta


class VolumeSpikeAnalyzer:
    def __init__(self, df: pd.DataFrame, volume_col: str = 'Volume', window: int = 20, threshold: float = 2.0):
        self.df = df.copy()
        self.volume_col = volume_col
        self.window = window
        self.threshold = threshold
        self.df['volume_spike'] = False

    def compute_volume_spikes(self):
        self.df['volume_sma'] = ta.sma(
            self.df[self.volume_col], length=self.window)
        self.df['volume_spike'] = self.df[self.volume_col] > (
            self.df['volume_sma'] * self.threshold)
        return self.df

    def analyze(self):
        return self.compute_volume_spikes()
