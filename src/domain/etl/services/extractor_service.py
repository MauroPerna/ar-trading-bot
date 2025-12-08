import pandas as pd
import logging
from typing import Optional, Union, List, Dict
from datetime import datetime

from src.infrastructure.data.yfinance import YFinanceService
from src.domain.etl.dtos.extracted_data import ExtractedData

logger = logging.getLogger(__name__)


class ExtractorService:
    def __init__(self, extractor: YFinanceService):
        self.extractor = extractor

    async def extract(
        self,
        symbols: Optional[Union[str, List[str]]] = None,
        timeframe: Optional[str] = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Union[ExtractedData, Dict[str, ExtractedData]]:

        if symbols is None:
            symbols_list: List[str] = self.extractor.default_symbols
        elif isinstance(symbols, str):
            symbols_list = [symbols]
        else:
            symbols_list = symbols

        panel_df = await self.extractor.get_ohlcv(symbols_list, interval=timeframe, start=start, end=end)

        logger.info(
            f"📥 Extracted {len(panel_df)} rows for symbols={symbols_list}")

        is_multi = isinstance(panel_df.columns, pd.MultiIndex)
        extracted_map: Dict[str, ExtractedData] = {}

        for sym in symbols_list:
            if is_multi:
                if sym not in panel_df.columns.get_level_values(0):
                    logger.warning(
                        f"⚠️ Symbol {sym} no encontrado en panel_df")
                    continue
                df = panel_df[sym].copy()
            else:
                df = panel_df.copy()

            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            })

            df.columns.name = None
            df.index = pd.to_datetime(df.index)
            df.index.name = "timestamp"

            extracted_map[sym] = ExtractedData(
                ohlcv=df,
                metadata={"source": "yfinance"},
                asset=sym,
                timeframe="1d",
            )

        if len(extracted_map) == 1:
            return next(iter(extracted_map.values()))

        return extracted_map
