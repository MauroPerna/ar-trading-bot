from typing import Dict, List, Optional, Union
from src.domain.etl.dtos.enriched_data import EnrichedData
from src.domain.strategies.dtos.backtest_report import BacktestReport
from src.domain.strategies.services.service import BacktestService
from src.domain.strategies.services.registry import get_strategy_class
from src.infrastructure.database.repositories.symbol_strategy_repository import (
    SymbolStrategyRepository,
)
from src.infrastructure.database.client import PostgresClient
import logging

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    """
    Orquesta:
      - correr backtests
      - rankear
      - persistir mejor estrategia por símbolo
    """

    def __init__(
        self,
        backtest_service: BacktestService,
        db_client: PostgresClient,
        default_timeframe: str = "1d",
    ) -> None:
        self.backtest_service = backtest_service
        self.db_client = db_client
        self.default_timeframe = default_timeframe

    async def run_and_persist(
        self,
        data: Union[EnrichedData, Dict[str, EnrichedData]],
        strategy_names: Optional[List[str]] = None,
        strategy_params: Optional[Dict[str, Dict[str, float]]] = None,
        timeframe: Optional[str] = None,
    ) -> Dict[str, List[BacktestReport]]:

        results = self.backtest_service.run_for_enriched(
            data=data,
            strategy_names=strategy_names,
            strategy_params=strategy_params,
        )

        tf = timeframe or getattr(data, "timeframe", self.default_timeframe)

        async with self.db_client.get_session() as session:
            repo = SymbolStrategyRepository(session)

            for symbol, reports in results.items():
                if not reports:
                    logger.warning(
                        f"⚠️ No reports for {symbol}, nothing persisted"
                    )
                    continue

                best = reports[0]
                raw_stats = best.metadata.get("raw_stats", {})

                strategy_cls = get_strategy_class(best.strategy_name)
                config_dto = strategy_cls.get_config()
                config_dict = config_dto.model_dump()

                await repo.upsert_best_strategy(
                    symbol=symbol,
                    timeframe=tf,
                    strategy_name=best.strategy_name,
                    params=config_dict,
                    metrics=raw_stats,
                )

        return results
