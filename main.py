import uvicorn
import logging.config
from src.application.app import create_app
from src.infrastructure.config.settings import settings

logging.config.dictConfig(settings.get_logging_config())
logger = logging.getLogger(__name__)


app = create_app()

if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} in {settings.environment} mode")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
        workers=1,
    )
