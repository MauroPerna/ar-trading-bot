from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class OrderType(Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class OrderDTO(BaseModel):
    """
    Trading order DTO (Pydantic model).
    """

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default_factory=uuid4)
    broker_id: Optional[str] = None
    symbol: str
    side: OrderSide
    quantity: float = Field(..., gt=0.0)
    order_type: OrderType

    limit_price: Optional[float] = None
    stop_price: Optional[float] = None

    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.FILLED

    @property
    def remaining_quantity(self) -> float:
        """Get remaining unfilled quantity."""
        return self.quantity - self.filled_quantity
