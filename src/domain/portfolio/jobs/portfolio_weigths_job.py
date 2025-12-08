import logging
from datetime import datetime, timedelta
from typing import List
import asyncio
import pandas as pd
from src.domain.etl.services.pipeline_service import FeaturePipelineService
from src.infrastructure.database.client import PostgresClient
from src.domain.portfolio.optimizers.base_optimizer import BaseOptimizer
from src.infrastructure.database.repositories.portfolio_repository import PortfolioRepository
from src.infrastructure.database.repositories.portfolio_weights_repository import PortfolioWeightsRepository


logger = logging.getLogger(__name__)


class PortfolioWeigthsJob:

    def __init__(self, db_client: PostgresClient, pipeline: FeaturePipelineService, optimizer: BaseOptimizer) -> None:
        self.db_client = db_client
        self.pipeline = pipeline
        self.optimizer = optimizer

    async def run(self) -> None:
        portfolio_weights_repo: PortfolioWeightsRepository
        end = datetime.now()
        start = end - timedelta(hours=4320)
        data = await self.pipeline.start(symbols=None, timeframe="1h", start=start, end=end, indicators=["rsi"])
        adj_close_frames = []

        async with self.db_client.get_session() as session:
            portfolio_weights_repo = PortfolioWeightsRepository(session)

        for symbol, enriched in data.items():
            df = enriched.ohlcv[["adj_close"]].copy()
            df.rename(columns={"adj_close": symbol}, inplace=True)
            adj_close_frames.append(df)

        prices_df = pd.concat(adj_close_frames, axis=1).sort_index()

        weights = self.optimizer.optimize(
            prices=prices_df)

        await portfolio_weights_repo.bulk_upsert_weights(weights=weights, timeframe="1h", optimizer_name=self.optimizer.__class__.__name__)

        return
