import logging
from datetime import datetime
from typing import List
import asyncio
from src.domain.strategies.services.research_orchestrator import ResearchOrchestrator
from src.domain.etl.services.pipeline_service import FeaturePipelineService
from src.infrastructure.database.client import PostgresClient


logger = logging.getLogger(__name__)


class StrategyPerTickerJob:

    def __init__(self, db_client: PostgresClient, pipeline: FeaturePipelineService, orchestrator: ResearchOrchestrator) -> None:
        self.db_client = db_client
        self.pipeline = pipeline
        self.orchestrator = orchestrator

    async def run(self) -> None:
        logger.info("Starting StrategyPerTickerJob at %s",
                    datetime.now().isoformat())
        df = await self.pipeline.start(symbols=None, indicators=[])
        await self.orchestrator.run_and_persist(
            data=df,
            strategy_names=None,
            strategy_params=None,
            timeframe="1h",
        )
        logger.info("Finished StrategyPerTickerJob at %s",
                    datetime.now().isoformat())
