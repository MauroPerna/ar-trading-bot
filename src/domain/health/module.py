from dependency_injector import containers, providers
from .service import HealthService


class HealthModule(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=[".controller"])
    root = providers.DependenciesContainer()
    service = providers.Factory(
        HealthService,
        db_client=root.db_client,
    )
