import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Awaitable
from uuid import uuid4

from src.infrastructure.data.ohlcv_base import OHLCVService
from src.infrastructure.broker.broker_base import BrokerClient
from src.commons.enums.broker_enums import Instruments, Countries
from src.domain.trading.dtos.order_dto import OrderDTO, OrderStatus, OrderSide
from src.domain.portfolio.dtos.portfolio_dto import PortfolioDTO
from src.infrastructure.database.client import PostgresClient
from src.infrastructure.database.repositories.portfolio_repository import (
    PortfolioRepository,
)


class FakeBrokerClient(BrokerClient):
    """
    Fake broker que:
    - opera 100% contra la DB (PortfolioModel)
    - no guarda nada en memoria excepto órdenes retornadas
    - llena órdenes instantáneamente
    - obtiene precios desde un price_provider async (ej: YFinanceService)
    """

    def __init__(
        self,
        db_client: PostgresClient,
        price_provider: OHLCVService,
        initial_cash: float = 1_000_000.0,
    ):
        self.db_client = db_client
        self._price_provider = price_provider
        self._authenticated = False
        self._initial_cash = initial_cash
        self._orders: Dict[str, OrderDTO] = {}

    # ---------------------------------------------------------------------
    # Auth
    # ---------------------------------------------------------------------
    async def auth(self) -> None:
        await asyncio.sleep(0)
        self._authenticated = True

    async def _ensure_auth(self) -> None:
        if not self._authenticated:
            await self.auth()

    # ---------------------------------------------------------------------
    # Portfolio
    # ---------------------------------------------------------------------
    async def get_portfolio(self) -> PortfolioDTO:
        await self._ensure_auth()

        async with self.db_client.get_session() as session:
            repo = PortfolioRepository(session)
            return await repo.get_portfolio_dto(initial_cash=self._initial_cash)

    # ---------------------------------------------------------------------
    # Instruments
    # ---------------------------------------------------------------------
    async def get_instruments(
        self,
        instrument: Instruments,
        country: Countries,
    ) -> List[Dict[str, Any]]:
        await self._ensure_auth()
        return [{"instrument": instrument.value, "country": country.value, "data": []}]

    # ---------------------------------------------------------------------
    # Orders
    # ---------------------------------------------------------------------
    async def place_order(self, order: OrderDTO) -> OrderDTO:
        """
        Lógica:
        1) Obtener precio con price_provider (async)
        2) Crear orden ejecutada
        3) Actualizar cash + posición en DB
        4) Devolver OrderDTO ejecutada (la persistencia real la hace OrderRepository)
        """
        await self._ensure_auth()

        price = self._price_provider.get_lastest_price(order.symbol)

        if price is None:
            raise ValueError(f"No se pudo obtener precio para {order.symbol}")

        broker_id = str(uuid4())

        executed_order = order.model_copy(
            update={
                "broker_id": broker_id,
                "status": OrderStatus.FILLED,
                "filled_quantity": order.quantity,
                "average_fill_price": price,
                "updated_at": datetime.now(),
            }
        )

        notional = price * order.quantity

        # ACTUALIZAR PORTFOLIO EN DB
        async with self.db_client.get_session() as session:
            repo = PortfolioRepository(session)
            portfolio = await repo.get_portfolio_dto(initial_cash=self._initial_cash)

            cash = portfolio.cash_balance
            positions = dict(portfolio.positions)

            old_qty = positions.get(order.symbol, 0.0)

            if order.side == OrderSide.BUY:
                cash -= notional
                new_qty = old_qty + order.quantity

            elif order.side == OrderSide.SELL:
                cash += notional
                new_qty = max(0.0, old_qty - order.quantity)

            positions[order.symbol] = new_qty

            updated = PortfolioDTO(
                cash_balance=cash,
                positions=positions,
            )
            await repo.save_portfolio_dto(updated)

        # Guardamos la orden localmente (solo para consultas)
        self._orders[broker_id] = executed_order
        return executed_order

    async def get_order(self, broker_id: str) -> OrderDTO:
        await self._ensure_auth()
        if broker_id not in self._orders:
            raise KeyError(f"Order {broker_id} not found in FakeBroker")
        return self._orders[broker_id]

    async def cancel_order(self, broker_id: str) -> OrderDTO:
        await self._ensure_auth()
        if broker_id not in self._orders:
            raise KeyError(f"Order {broker_id} not found")

        order = self._orders[broker_id]
        if order.status == OrderStatus.FILLED:
            return order

        cancelled = order.model_copy(
            update={"status": OrderStatus.CANCELLED,
                    "updated_at": datetime.now()}
        )
        self._orders[broker_id] = cancelled
        return cancelled

    # ---------------------------------------------------------------------
    # Positions (enriquecidas con precio de mercado)
    # ---------------------------------------------------------------------
    async def positions(self) -> List[Dict[str, Any]]:
        await self._ensure_auth()

        portfolio = await self.get_portfolio()
        result = []

        for symbol, qty in portfolio.positions.items():
            if qty <= 0:
                continue

            price = self._price_provider.get_lastest_price(symbol)

            if price is None:
                continue

            # Sin avg_price real (FakeBroker), usamos price mismo
            result.append(
                {
                    "symbol": symbol,
                    "quantity": qty,
                    "avg_price": price,
                    "market_price": price,
                    "market_value": qty * price,
                    "unrealized_pnl": 0.0,
                }
            )

        return result
