import logging
from typing import List, Optional
from src.infrastructure.database.client import PostgresClient

logger = logging.getLogger(__name__)


class HealthService:
    def __init__(self, db_client: PostgresClient):
        self.db_client = db_client

    async def check_database_health(self) -> bool:
        try:
            return await self.db_client.health_check()
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
