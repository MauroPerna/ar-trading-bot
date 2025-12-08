from fastapi import FastAPI
from dependency_injector import providers
from src.application.container import container as root_container


def register_modules(app: FastAPI):
    # Register Health Module
    from src.domain.health.module import HealthModule
    from src.domain.health.controller import router as health_router

    health_container = HealthModule(
        root=providers.DependenciesContainer(
            db_client=root_container.db_client,
        )
    )
    health_container.wire(modules=["src.domain.health.controller"])

    app.include_router(health_router)
    app.state.health_container = health_container

    # Register Feature Module
    from src.domain.etl.features_module import FeaturesModule

    feature_module = FeaturesModule(
        root=providers.DependenciesContainer(
            db_client=root_container.db_client,
            broker=root_container.broker,
            config=root_container.config,
            extractor=root_container.extractor,
        ),
    )

    app.state.feature_module = feature_module

    # Register Strategies Module
    from src.domain.strategies.strategies_module import StrategiesModule

    strategies_module = StrategiesModule(
        root=providers.DependenciesContainer(
            db_client=root_container.db_client,
            pipeline_service=feature_module.service,
        ),
    )

    app.state.strategies_module = strategies_module

    # Register Signals Module
    from src.domain.signals.signals_module import SignalsModule

    signals_module = SignalsModule(
        root=providers.DependenciesContainer(
            db_client=root_container.db_client,
            pipeline_service=feature_module.service,
        ),
    )

    app.state.signals_module = signals_module

    # Register Portfolio Module
    from src.domain.portfolio.portfolio_module import PortfolioModule

    portfolio_module = PortfolioModule(
        root=providers.DependenciesContainer(
            db_client=root_container.db_client,
            pipeline_service=feature_module.service,
            extractor=root_container.extractor,
            broker=root_container.broker,
        ),
    )

    app.state.portfolio_module = portfolio_module

    # Register Trading Module
    from src.domain.trading.trading_module import TradingModule

    trading_module = TradingModule(
        root=providers.DependenciesContainer(
            db_client=root_container.db_client,
            portfolio=portfolio_module.portfolio_service,
            broker=root_container.broker,
        ),
    )

    app.state.trading_module = trading_module
