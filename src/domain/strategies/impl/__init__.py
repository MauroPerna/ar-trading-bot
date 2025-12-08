from .sma_crossover import SMACrossoverStrategy
from .sma_crossover_rsi_avgvol import SMACrossoverWithRSIAndAvgVolStrategy
from .sma_crossover_rsi_vol_tpsl import SMACrossoverRSIVolWithTPSLStrategy
from .macd import MACDStrategy
from .rsi import RSIStrategy
from .rsi_trend import RSIWithTrendSignalStrategy
from .breakout_signal import BreakoutSignalStrategy
from .fair_value_gap import FairValueGapStrategy
from .volume_spike import VolumeSpikeEntryStrategy

strategies = {
    "SMACrossoverStrategy": SMACrossoverStrategy,
    "SMACrossoverWithRSIAndAvgVolStrategy": SMACrossoverWithRSIAndAvgVolStrategy,
    "SMACrossoverRSIVolWithTPSLStrategy": SMACrossoverRSIVolWithTPSLStrategy,
    "MACDStrategy": MACDStrategy,
    "RSIStrategy": RSIStrategy,
    "RSIWithTrendSignalStrategy": RSIWithTrendSignalStrategy,
    "BreakoutSignalStrategy": BreakoutSignalStrategy,
    "FairValueGapStrategy": FairValueGapStrategy,
    "VolumeSpikeEntryStrategy": VolumeSpikeEntryStrategy,
}

__all__ = ["strategies"]
