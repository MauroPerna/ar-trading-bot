"""
Order Database Model

SQLAlchemy model for orders.
"""

from sqlalchemy import Column, String, Float, DateTime, Enum as SQLEnum
from uuid import uuid4
import enum

from src.infrastructure.database.models.base import BaseModel


class OrderStatusEnum(str, enum.Enum):
    """Order status enum."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderModel(BaseModel):
    """Order database model."""
    
    __tablename__ = 'orders'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    order_type = Column(String, nullable=False)
    status = Column(SQLEnum(OrderStatusEnum), nullable=False, default=OrderStatusEnum.PENDING)
    limit_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, default=0.0)
    average_fill_price = Column(Float, default=0.0)
