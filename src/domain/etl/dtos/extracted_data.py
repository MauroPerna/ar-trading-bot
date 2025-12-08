from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd


@dataclass
class ExtractedData:
    ohlcv: pd.DataFrame
    metadata: Dict[str, Any]
    asset: str
    timeframe: str
