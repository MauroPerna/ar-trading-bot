from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import Column, String, Float, DateTime, JSON, Enum

from src.infrastructure.database.models.base import BaseModel
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum

TTL_DAYS = 180


class SignalModel(BaseModel):
    """Signal database model."""

    __tablename__ = 'signals'

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    symbol = Column(String, nullable=False)
    signal_source = Column(Enum(SignalSourceEnum), nullable=True)
    signal_type = Column(Enum(SignalTypeEnum), nullable=False)
    strength = Column(Enum(SignalStrengthEnum), nullable=False)
    confidence = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    meta = Column(JSON, nullable=True)
    expires_at = Column(
        DateTime,
        nullable=False,
        index=True,
        default=lambda: datetime.now() + timedelta(days=TTL_DAYS),
    )
