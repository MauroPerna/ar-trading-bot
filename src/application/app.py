from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.infrastructure.config.settings import settings
from src.application.lifecycle import lifespan
from src.application.module_registry import register_modules
import logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:

    app = FastAPI(
        title="Trading API",
        description="API for algorithmic trading system",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        root_path="/api/v1",
        redirect_slashes=False,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    register_modules(app)

    return app
