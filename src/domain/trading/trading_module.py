from dependency_injector import containers, providers
from .trading_service import TradingService


class TradingModule(containers.DeclarativeContainer):
    root = providers.DependenciesContainer()

    trading_service = providers.Factory(
        TradingService,
        db_client=root.db_client,
        portfolio=root.portfolio,
        broker=root.broker,
    )
