# src/infrastructure/database/models/portfolio_weights.py

from uuid import uuid4
from datetime import datetime

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


class PortfolioWeightsModel(BaseModel):
    """
    Guarda la asignación óptima de pesos por activo generada por el optimizador.

    - Se guarda por símbolo, timeframe y fecha de rebalanceo.
    - Solo un set activo debería controlar el trading.
    """

    __tablename__ = "portfolio_weights"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False, default="1d")
    weight = Column(Float, nullable=False)
    optimizer_name = Column(String, nullable=False)
    rebalance_date = Column(DateTime, nullable=False,
                            index=True, default=datetime.now)
    is_active = Column(Boolean, nullable=False, default=True)
    meta = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "rebalance_date",
            "optimizer_name",
            name="uq_weights_symbol_timeframe_date_optimizer",
        ),
    )
