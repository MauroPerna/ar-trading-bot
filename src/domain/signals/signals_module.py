from dependency_injector import containers, providers
from .aggregator import SignalAggregator
from .signals_service import SignalService
from .jobs.generate_signals_job import GenerateSignalsJob


class SignalsModule(containers.DeclarativeContainer):
    root = providers.DependenciesContainer()

    aggregator_service = providers.Factory(
        SignalAggregator,
    )

    signals_service = providers.Factory(
        SignalService,
        db_client=root.db_client,
        aggregator=aggregator_service,
    )

    generate_signals_job = providers.Factory(
        GenerateSignalsJob,
        db_client=root.db_client,
        pipeline=root.pipeline_service,
        signals=signals_service,
    )
