import logging
from typing import List, Optional
from datetime import datetime

import pandas as pd
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.signals.dtos.signal_dto import SignalDTO
from src.infrastructure.database.models.signal_model import SignalModel

logger = logging.getLogger(__name__)


class SignalRepository:
    """Repository for signal persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, signal: SignalDTO) -> SignalDTO:
        """Save a signal and return updated DTO with DB ID."""

        model = SignalModel(
            symbol=signal.symbol,
            signal_source=signal.signal_source,
            signal_type=signal.signal_type,
            confidence=signal.confidence,
            strength=signal.strength,
            price=signal.price,
            target_price=signal.target_price,
            stop_loss=signal.stop_loss,
            meta=self._to_jsonable(signal.meta or {}),
        )

        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)

        return SignalDTO(
            id=model.id,
            created_at=model.created_at.isoformat(),
            **signal.model_dump()
        )

    async def save_batch(self, signals: List[SignalDTO]) -> None:
        """Optimized batch insert."""
        for sig in signals:
            await self.save(sig)

    async def get_latest(
        self,
        symbol: str,
        signal_type: Optional[str] = None,
    ) -> Optional[SignalDTO]:
        """Return most recent valid signal for a symbol."""

        stmt = (
            select(SignalModel)
            .where(SignalModel.symbol == symbol)
            .order_by(SignalModel.created_at.desc())
        )

        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._to_dto(model)

    async def get_by_timerange(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[SignalDTO]:
        """Query signals within a given time range."""

        stmt = (
            select(SignalModel)
            .where(
                SignalModel.symbol == symbol,
                SignalModel.created_at >= start_time,
                SignalModel.created_at <= end_time,
            )
            .order_by(SignalModel.created_at.desc())
        )

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_dto(m) for m in models]

    # ------------------------
    # HELPERS
    # ------------------------

    def _to_dto(self, model: SignalModel) -> SignalDTO:
        """Convert DB model to DTO."""

        return SignalDTO(
            id=model.id,
            symbol=model.symbol,
            signal_source=model.signal_source,
            signal_type=model.signal_type,
            strength=model.strength,
            confidence=model.confidence,
            price=model.price,
            target_price=model.target_price,
            stop_loss=model.stop_loss,
            meta=model.meta,
            created_at=model.created_at.isoformat(),
        )

    def _to_jsonable(self, value):
        """Normalize values before saving to JSON."""

        if value is None:
            return None

        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()

        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.bool_):
            return bool(value)

        if isinstance(value, dict):
            return {k: self._to_jsonable(v) for k, v in value.items()}

        if isinstance(value, (list, set, tuple)):
            return [self._to_jsonable(v) for v in value]

        return value
