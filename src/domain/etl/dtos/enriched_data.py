from dataclasses import dataclass
from typing import Dict, Any, List
import pandas as pd


@dataclass
class EnrichedData:
    ohlcv: pd.DataFrame
    metadata: Dict[str, Any]
    asset: str
    timeframe: str
    transformation_log: Dict[str, Any]
    indicators_added: List[str]
