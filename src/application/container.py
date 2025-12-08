from dependency_injector import containers, providers
from src.infrastructure.database.client import PostgresClient
from src.infrastructure.config.settings import Settings
from src.infrastructure.broker.broker_iol import IOLClient
from src.infrastructure.broker.broker_fake import FakeBrokerClient
from src.infrastructure.data.yfinance import YFinanceService
from src.infrastructure.scheduler.scheduler import JobScheduler


class Container(containers.DeclarativeContainer):
    config = providers.Singleton(Settings)

    db_client = providers.Singleton(
        PostgresClient,
        db_url=config().async_database_url,
        pool_size=config().db_pool_size,
        max_overflow=config().db_max_overflow,
        pool_timeout=config().db_pool_timeout,
        pool_recycle=config().db_pool_recycle,
        echo=config().db_echo,
    )

    extractor = providers.Singleton(
        YFinanceService,
    )

    broker = providers.Singleton(
        FakeBrokerClient, db_client=db_client, price_provider=extractor)

    scheduler = providers.Singleton(
        JobScheduler,
        timezone=config().scheduler_timezone,
    )


container = Container()
