from dependency_injector import containers, providers
from .services.service import BacktestService
from .services.engine import BacktestEngine
from .services.research_orchestrator import ResearchOrchestrator
from .jobs.strategy_per_ticker_job import StrategyPerTickerJob


class StrategiesModule(containers.DeclarativeContainer):
    root = providers.DependenciesContainer()

    backtest_engine = providers.Factory(
        BacktestEngine,
    )

    backtest_service = providers.Factory(
        BacktestService,
        engine=backtest_engine,
    )

    orchestrator_service = providers.Factory(
        ResearchOrchestrator,
        backtest_service=backtest_service,
        db_client=root.db_client,
    )

    strategy_per_ticker_job = providers.Factory(
        StrategyPerTickerJob,
        db_client=root.db_client,
        pipeline=root.pipeline_service,
        orchestrator=orchestrator_service,
    )
