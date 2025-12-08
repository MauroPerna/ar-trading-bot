import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.trading.dtos.order_dto import (
    OrderDTO,
    OrderStatus,
    OrderSide,
    OrderType,
)
from src.infrastructure.database.models.order_model import (
    OrderModel,
    OrderStatusEnum,
)

logger = logging.getLogger(__name__)


class OrderRepository:
    """
    Repository for order persistence.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository.

        Args:
            session: Database session
        """
        self.session = session

    async def save(self, order: OrderDTO) -> OrderDTO:
        """
        Save an order.

        Args:
            order: Order to save

        Returns:
            Saved order (mismo DTO que entra)
        """
        model = OrderModel(
            id=str(order.id),
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            order_type=order.order_type.value,
            status=OrderStatusEnum(order.status.value),
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            filled_quantity=order.filled_quantity,
            average_fill_price=order.average_fill_price,
        )

        self.session.add(model)
        await self.session.commit()

        return order

    async def get_by_id(self, order_id: UUID) -> Optional[OrderDTO]:
        """Get order by ID."""
        stmt = select(OrderModel).where(OrderModel.id == str(order_id))
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._model_to_dto(model)

    async def update_status(self, order_id: UUID, status: OrderStatus) -> None:
        """Update order status."""
        stmt = select(OrderModel).where(OrderModel.id == str(order_id))
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model:
            model.status = OrderStatusEnum(status.value)
            await self.session.commit()

    def _model_to_dto(self, model: OrderModel) -> OrderDTO:
        return OrderDTO(
            id=UUID(model.id),
            symbol=model.symbol,
            side=OrderSide(model.side),
            quantity=model.quantity,
            order_type=OrderType(model.order_type),
            status=OrderStatus(model.status.value),
            limit_price=model.limit_price,
            stop_price=model.stop_price,
            filled_quantity=model.filled_quantity,
            average_fill_price=model.average_fill_price,
        )
