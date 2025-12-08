from typing import Callable, Optional
import logging
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError


logger = logging.getLogger(__name__)


class JobScheduler:
    """
    Scheduler for programmed tasks
    """

    def __init__(
        self,
        timezone: str = "America/Argentina/Buenos_Aires",
    ):
        self.timezone = timezone
        self.scheduler: Optional[AsyncIOScheduler] = None

        logger.info(f"JobScheduler initialized with timezone: {timezone}")

    async def start(self) -> None:
        logger.info("Starting scheduler...")

        if self.scheduler and self.scheduler.running:
            logger.warning("The scheduler is already running")
            return

        self.scheduler = AsyncIOScheduler(
            timezone=ZoneInfo(self.timezone),
            job_defaults={"coalesce": True, "max_instances": 1},
        )

        self.scheduler.start()
        logger.info(f"Scheduler running in timezone: {self.timezone}")

    async def shutdown(self) -> None:
        if self.scheduler and self.scheduler.running:
            logger.info("Shutting down scheduler...")
            try:
                self.scheduler.shutdown(wait=False)
                logger.info("Scheduler shut down correctly")
            except JobLookupError as e:
                logger.error(f"Error shutting down scheduler: {e}")
