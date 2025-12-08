import logging
import pandas as pd
from typing import Optional, List

from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.infrastructure.database.repositories.symbol_strategy_repository import SymbolStrategyRepository
from src.infrastructure.database.client import PostgresClient
from src.domain.signals.aggregator import SignalAggregator
from src.domain.signals.signals_bus import signal_bus

# interpreters
from src.domain.signals.interpreters.base_interpreter import BaseStrategyInterpreter
from src.domain.signals.interpreters.structure_interpreter import StructureInterpreter
from src.domain.signals.interpreters.volume_interpreter import VolumeInterpreter
from src.domain.signals.interpreters.volatility_interpreter import VolatilityInterpreter
from src.domain.signals.interpreters.trend_interpreter import TrendInterpreter
from src.domain.signals.interpreters.momentum_interpreter import MomentumInterpreter
from src.domain.signals.interpreters.risk_interpreter import RiskInterpreter

logger = logging.getLogger(__name__)


class SignalService:
    """
    Genera señales en tiempo real basadas en la estrategia activa.
    """

    def __init__(self, db_client: PostgresClient, aggregator: SignalAggregator):
        self.db_client = db_client
        self.aggregator = aggregator

        self.interpreters: List[BaseStrategyInterpreter] = [
            StructureInterpreter(),
            VolumeInterpreter(),
            TrendInterpreter(),
            MomentumInterpreter(),
            RiskInterpreter(),
            VolatilityInterpreter(),
        ]

    async def generate_for_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        timeframe: str = "1h",
    ) -> Optional[SignalDTO]:

        if df.empty:
            logger.info(f"❌ Empty DF for {symbol}, no signal")
            return None

        async with self.db_client.get_session() as session:
            strategy_repo = SymbolStrategyRepository(session)

            config: Optional[StrategyConfigDTO] = await strategy_repo.get_active_strategy_config(
                symbol=symbol,
                timeframe=timeframe,
            )

        if not config:
            logger.info(
                f"ℹ️ No active strategy for {symbol}/{timeframe}")
            return None

        logger.info(
            f"🎯 Generating signal using strategy: {config.strategy_name}")

        # ======== 1) Ejecutar interpreters ========
        all_signals: List[SignalDTO] = []

        for interpreter in self.interpreters:
            try:
                result = interpreter.interpret(df=df, config=config)

                if result:
                    if isinstance(result, list):
                        all_signals.extend(result)
                    else:
                        all_signals.append(result)

            except Exception as e:
                logger.error(
                    f"⚠️ Error en {interpreter.__class__.__name__}: {e}")

        if not all_signals:
            logger.info("🤷 No signals detected")
            return []

        # ======== 2) Fusionar señales ========
        best = self.aggregator.aggregate(all_signals)

        if not best:
            logger.info("🤝 Aggregator found no clear consensus → None")
            return None

        logger.info(
            f"📌 Final signal selected → {best.signal_type.value.upper()} "
            f"({best.strength.value}, conf={best.confidence:.2f})"
        )

        signal_bus.on_next(best)

        return best
