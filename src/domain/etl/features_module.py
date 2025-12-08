from dependency_injector import containers, providers
from src.domain.etl.services.pipeline_service import FeaturePipelineService
from src.domain.etl.services.extractor_service import ExtractorService
from src.domain.etl.services.enricher_service import EnricherService


class FeaturesModule(containers.DeclarativeContainer):
    root = providers.DependenciesContainer()

    extractor = providers.Factory(
        ExtractorService,
        extractor=root.extractor,
    )
    transformer = providers.Factory(EnricherService)

    service = providers.Factory(
        FeaturePipelineService,
        extractor=extractor,
        transformer=transformer,
    )
