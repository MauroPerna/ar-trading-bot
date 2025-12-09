from typing import Dict, List, Optional, Union
from src.domain.etl.dtos.enriched_data import EnrichedData
from src.domain.strategies.dtos.backtest_report import BacktestReport
from src.domain.strategies.services.engine import BacktestEngine
from src.domain.strategies.services.ranking import rank_reports

import logging

logger = logging.getLogger(__name__)


class BacktestService:
    def __init__(self, engine: BacktestEngine):
        self.engine = engine

    def run_for_enriched(
        self,
        data: Union[EnrichedData, Dict[str, EnrichedData]],
        strategy_names: Optional[List[str]] = None,
        strategy_params: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Dict[str, List[BacktestReport]]:
        """
        Recibe:
          - EnrichedData       → un solo activo
          - Dict[str, EnrichedData] → varios activos

        Devuelve siempre:
          { asset: [BacktestReport, ...] (rankeados) }
        """
        if isinstance(data, EnrichedData):
            reports = self.engine.run_for_asset(
                df=data.ohlcv,
                asset=data.asset,
                strategy_names=strategy_names,
                strategy_params=strategy_params,
            )
            ranked = rank_reports(reports)
            return {data.asset: ranked}

        results: Dict[str, List[BacktestReport]] = {}

        for sym, enriched in data.items():
            try:
                reports = self.engine.run_for_asset(
                    df=enriched.ohlcv,
                    asset=enriched.asset,
                    strategy_names=strategy_names,
                    strategy_params=strategy_params,
                )
                ranked = rank_reports(reports)
                results[sym] = ranked
            except Exception as e:
                logger.error(f"❌ Backtest failed for {sym}: {e}")
                results[sym] = []

        return results
