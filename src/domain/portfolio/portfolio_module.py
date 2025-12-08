from dependency_injector import containers, providers
from src.domain.portfolio.portfolio_service import PortfolioService
from src.domain.portfolio.optimizers.hrp_optimizer import HRPOptimizer
from src.domain.portfolio.optimizers.base_optimizer import BaseOptimizer
from src.domain.portfolio.jobs.portfolio_weigths_job import PortfolioWeigthsJob


class PortfolioModule(containers.DeclarativeContainer):
    root = providers.DependenciesContainer()

    default_optimizer: providers.Provider[BaseOptimizer] = providers.Factory(
        HRPOptimizer,
    )

    portfolio_weights_job = providers.Factory(
        PortfolioWeigthsJob,
        db_client=root.db_client,
        pipeline=root.pipeline_service,
        optimizer=default_optimizer,
    )

    portfolio_service = providers.Factory(
        PortfolioService,
        db_client=root.db_client,
        extractor=root.extractor,
        optimizer=default_optimizer,
        broker=root.broker
    )
