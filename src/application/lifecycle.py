from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from apscheduler.triggers.cron import CronTrigger
from src.application.container import container
from src.infrastructure.scheduler.scheduler import JobScheduler
from src.infrastructure.scheduler.cron_expression_enum import CronSchedule
from src.infrastructure.database.repositories.portfolio_repository import PortfolioRepository
from src.infrastructure.database.repositories.portfolio_weights_repository import PortfolioWeightsRepository
from src.infrastructure.database.repositories.symbol_strategy_repository import SymbolStrategyRepository
from src.infrastructure.config.settings import settings
from src.domain.strategies.strategies_module import StrategiesModule, StrategyPerTickerJob
from src.domain.signals.signals_module import SignalsModule, GenerateSignalsJob
from src.domain.portfolio.portfolio_module import PortfolioModule, PortfolioWeigthsJob
from src.domain.trading.trading_module import TradingModule
from src.domain.trading.trading_stream import setup_trading_stream

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application...")
    scheduler: JobScheduler = container.scheduler()

    try:
        # 1) Inicializar DB primero
        await container.db_client().init()
        logger.info("Database initialized successfully")

        # 2) En development, asegurar que exista un portfolio por defecto
        if settings.is_development:
            async with container.db_client().get_session() as session:
                repo = PortfolioRepository(session)
                await repo.ensure_default_portfolio(initial_cash=1_000_000.0)
            logger.info("Default portfolio ensured (development mode)")

        # 3) Instanciar trading service y conectar el stream ANTES del scheduler
        trading: TradingModule = app.state.trading_module
        trading_service = trading.trading_service()
        setup_trading_stream(trading_service)
        logger.info("Trading stream setup completed")

        # 4) Arrancar scheduler
        await scheduler.start()
        logger.info("Scheduler started")

        # 5) Schedule StrategyPerTickerJob
        strategies_module: StrategiesModule = app.state.strategies_module
        strategy_job: StrategyPerTickerJob = strategies_module.strategy_per_ticker_job()
        scheduler.scheduler.add_job(
            strategy_job.run,
            CronTrigger.from_crontab(str(CronSchedule.MONTHLY_FIRST_DAY)),
            id="strategy_per_ticker_job",
            replace_existing=True,
        )
        logger.info("StrategyPerTickerJob scheduled")

        # 6) Schedule GenerateSignalsJob
        signals_module: SignalsModule = app.state.signals_module
        generate_signals_job: GenerateSignalsJob = signals_module.generate_signals_job()
        scheduler.scheduler.add_job(
            generate_signals_job.run,
            CronTrigger.from_crontab(str(CronSchedule.EVERY_HOUR)),
            id="generate_signals_job",
            replace_existing=True,
        )
        logger.info("GenerateSignalsJob scheduled")

        # 7) Schedule PortfolioWeigthsJob
        portfolio_module: PortfolioModule = app.state.portfolio_module
        portfolio_weights_job: PortfolioWeigthsJob = portfolio_module.portfolio_weights_job()
        scheduler.scheduler.add_job(
            portfolio_weights_job.run,
            CronTrigger.from_crontab(str(CronSchedule.MONTHLY_FIRST_DAY)),
            id="portfolio_weights_job",
            replace_existing=True,
        )
        logger.info("PortfolioWeigthsJob scheduled")

        # 8) Run StrategyPerTickerJob if no active strategies exist
        async with container.db_client().get_session() as session:
            strategy_repo = SymbolStrategyRepository(session)
            existing_strategies = await strategy_repo.get_all_active_strategies(timeframe="1h")

        if not existing_strategies:
            logger.info("No active strategies found, running initial StrategyPerTickerJob...")
            await strategy_job.run()
            logger.info("Initial StrategyPerTickerJob completed")

        # 9) Run PortfolioWeightsJob if no weights exist
        async with container.db_client().get_session() as session:
            weights_repo = PortfolioWeightsRepository(session)
            existing_weights = await weights_repo.get_active_weights(timeframe="1h")

        if not existing_weights:
            logger.info("No portfolio weights found, running initial PortfolioWeightsJob...")
            await portfolio_weights_job.run()
            logger.info("Initial PortfolioWeightsJob completed")

        yield

    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        raise

    finally:
        logger.info("Shutting down application...")

        try:
            await scheduler.shutdown()
            logger.info("Scheduler shut down successfully")
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {e}")

        await container.db_client().close()
        logger.info("Application shut down successfully")
