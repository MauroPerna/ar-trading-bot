"""
Trade Database Model

SQLAlchemy model for trades.
"""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from uuid import uuid4

from src.infrastructure.database.models.base import BaseModel


class TradeModel(BaseModel):
    """Trade database model."""
    
    __tablename__ = 'trades'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    order_id = Column(String, ForeignKey('orders.id'), nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
