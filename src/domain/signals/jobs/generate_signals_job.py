import logging
from datetime import datetime, timedelta
from typing import List
import asyncio
from ..signals_service import SignalService
from src.domain.etl.services.pipeline_service import FeaturePipelineService
from src.infrastructure.database.client import PostgresClient


logger = logging.getLogger(__name__)


class GenerateSignalsJob:

    def __init__(self, db_client: PostgresClient, pipeline: FeaturePipelineService, signals: SignalService) -> None:
        self.db_client = db_client
        self.pipeline = pipeline
        self.signals = signals

    async def run(self) -> None:
        logger.info("Starting StrategyPerTickerJob at %s",
                    datetime.now().isoformat())
        symbols = self.pipeline.extractor.extractor.default_symbols
        end = datetime.now()
        start = end - timedelta(hours=200)

        for symbol in symbols:
            logger.info("Processing symbol: %s", symbol)
            df = await self.pipeline.start(symbols=symbol, indicators=[], timeframe="1h", start=start, end=end)
            await self.signals.generate_for_symbol(symbol=symbol, df=df.ohlcv)

        logger.info("Finished StrategyPerTickerJob at %s",
                    datetime.now().isoformat())
