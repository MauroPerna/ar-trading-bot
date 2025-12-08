from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    DateTime,
    JSON,
    UniqueConstraint,
)

from src.infrastructure.database.models.base import BaseModel


class SymbolStrategyModel(BaseModel):
    __tablename__ = "symbol_strategies"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))

    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False, default="1d")

    strategy_name = Column(String, nullable=False)
    params = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)

    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    backtested_at = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "is_active",
            name="uq_symbol_timeframe_active_strategy",
        ),
    )
