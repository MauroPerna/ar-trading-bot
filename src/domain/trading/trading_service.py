import logging
from typing import Optional
from src.domain.trading.dtos.order_dto import OrderDTO, OrderType, OrderStatus
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.infrastructure.database.repositories.signal_repository import SignalRepository
from src.infrastructure.database.repositories.order_repository import OrderRepository
from src.infrastructure.database.client import PostgresClient
from src.infrastructure.broker.broker_base import BrokerClient
from src.domain.portfolio.portfolio_service import PortfolioService


logger = logging.getLogger(__name__)


class TradingService:
    def __init__(self, db_client: PostgresClient, portfolio: PortfolioService, broker: BrokerClient):
        self.db_client = db_client
        self.portfolio = portfolio
        self.broker = broker

    async def handle_signal(self, signal: Optional[SignalDTO]) -> None:
        try:
            if signal is None:
                logger.warning("Received None signal, skipping.")
                return

            logger.info(
                f"Processing signal: {signal.symbol} - {signal.signal_type.value} "
                f"({signal.strength.value}, conf={signal.confidence:.2f})"
            )

            # 1) Compute sizing
            order_size = await self.portfolio.compute_order_size(signal)

            if not order_size:
                logger.info(
                    f"The {signal.signal_type.value} signal for {signal.symbol} was not executed due to zero order size."
                )
                return

            # 2) Create local order object
            order = OrderDTO(
                symbol=signal.symbol,
                side=signal.signal_type,
                quantity=order_size,
                order_type=OrderType.MARKET,
                limit_price=signal.price,
                status=OrderStatus.PENDING,
            )

            # 3) Send order to broker
            executed_order = await self.broker.place_order(order)

            # 4) Save everything in DB in one atomic session
            async with self.db_client.get_session() as session:
                signal_repo = SignalRepository(session)
                order_repo = OrderRepository(session)

                await signal_repo.save(signal)
                await order_repo.save(executed_order)

            logger.info(
                f"Order executed: {executed_order.symbol} {executed_order.side.value} "
                f"{executed_order.filled_quantity} @ {executed_order.average_fill_price}"
            )

        except Exception as e:
            logger.error(f"Error handling signal {signal}: {e}")
            raise e
