import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.exc import SQLAlchemyError
from src.infrastructure.database.models import Base

logger = logging.getLogger(__name__)


class PostgresClient:
    def __init__(
        self,
        db_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        echo: bool = False,
    ):
        self._db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

        self._engine = create_async_engine(
            self._db_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
            future=True,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        self._is_initialized = False

    async def init(self, create_schema: bool = True) -> None:
        """
        Inicializa la conexión y opcionalmente crea todas las tablas.

        Llamar una vez en el startup del server.
        """
        if self._is_initialized:
            return

        logger.info("🔌 Initializing PostgreSQL connection...")

        async with self._engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

            if create_schema:
                logger.info(
                    "🧱 Creating / updating database schema...")
                await conn.run_sync(Base.metadata.create_all)

        self._is_initialized = True
        logger.info("✅ PostgreSQL client initialized successfully")

    async def close(self) -> None:
        """
        Cierra el engine y libera recursos.
        """
        if self._is_initialized:
            await self._engine.dispose()
            self._is_initialized = False
            logger.info("🔌 PostgreSQL client closed")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager para obtener una sesión async.
        """
        async with self._session_factory() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"❌ Error in DB session, rollback applied: {e}")
                raise

    async def health_check(self) -> bool:
        """
        Ejecuta SELECT 1 para verificar conectividad.
        """
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as e:
            logger.error(f"❌ Database health check failed: {e}")
            return False
