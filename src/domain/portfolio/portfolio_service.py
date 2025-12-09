from __future__ import annotations
import logging
from typing import Optional

from src.commons.enums.signal_enums import SignalTypeEnum
from src.domain.portfolio.optimizers.base_optimizer import BaseOptimizer
from src.domain.portfolio.risk.constraints import (
    PortfolioConstraints,
    validate_weights,
)
from src.infrastructure.data.ohlcv_base import OHLCVService
from src.infrastructure.database.client import PostgresClient
from src.infrastructure.database.repositories.portfolio_weights_repository import (
    PortfolioWeightsRepository,
)
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.infrastructure.broker.broker_base import BrokerClient
from src.domain.portfolio.dtos.portfolio_dto import PortfolioDTO

logger = logging.getLogger(__name__)


class PortfolioService:
    def __init__(
        self,
        db_client: PostgresClient,
        extractor: OHLCVService,
        optimizer: Optional[BaseOptimizer],
        broker: BrokerClient,
    ):
        self.optimizer = optimizer
        self.db_client = db_client
        self.extractor = extractor
        self.broker = broker
        self.constraints = PortfolioConstraints()

    async def compute_order_size(self, signal: SignalDTO) -> float:
        """
        Given a signal, calculates order size (in asset units).

        Convention:
        - BUY  → positive size (quantity to buy)
        - SELL → negative size (quantity to sell)
        - HOLD → size 0.0 (no operation)
        """
        try:
            # HOLD: no operation
            if signal.signal_type == SignalTypeEnum.HOLD:
                logger.info(f"HOLD signal for {signal.symbol}, no operation.")
                return 0.0

            # Invalid price
            if signal.price is None or signal.price <= 0:
                logger.warning(
                    f"Signal without valid price for {signal.symbol}: {signal.price}"
                )
                return 0.0

            # 1) Get portfolio from broker (source of truth)
            portfolio: PortfolioDTO = await self.broker.get_portfolio()
            if portfolio is None:
                logger.warning(
                    "Could not get portfolio from broker, no operations.")
                return 0.0

            # 2) Read target weights from DB (optimizer / timeframe)
            async with self.db_client.get_session() as session:
                portfolio_weights_repo = PortfolioWeightsRepository(session)
                current_weights = await portfolio_weights_repo.get_active_weights(
                    timeframe="1h",
                    optimizer_name=(
                        self.optimizer.__class__.__name__
                        if self.optimizer
                        else None
                    ),
                ) or {}

            # 3) Basic info about current position
            symbol = signal.symbol
            side = signal.signal_type

            # Assuming PortfolioDTO.positions is Dict[str, float] -> quantity
            quantity_on_portfolio = portfolio.positions.get(symbol, 0.0)

            # --- SELL CASE ---
            if side == SignalTypeEnum.SELL:
                if quantity_on_portfolio <= 0.0:
                    logger.info(f"No position to sell for {symbol}.")
                    return 0.0

                logger.info(
                    f"Full position close for {symbol}: {quantity_on_portfolio} units."
                )
                # SELL returns negative size
                return -float(quantity_on_portfolio)

            # --- BUY CASE ---
            if side == SignalTypeEnum.BUY:
                total_portfolio_value = await self.calculate_total_value(portfolio)

                if total_portfolio_value is None or total_portfolio_value <= 0:
                    logger.warning(
                        "Total portfolio value is zero or negative, no BUY operation."
                    )
                    return 0.0

                target_weight = current_weights.get(symbol, 0.0)

                if target_weight <= 0:
                    logger.info(
                        f"Target weight for {symbol} is 0, no BUY order generated."
                    )
                    return 0.0

                # Target and current position value
                target_value = total_portfolio_value * target_weight
                current_value = quantity_on_portfolio * signal.price
                value_to_invest = target_value - current_value

                # If already above target, don't buy more
                if value_to_invest <= 0:
                    logger.info(
                        f"{symbol} is already above target weight. "
                        f"current={current_value:.2f}, target={target_value:.2f}"
                    )
                    return 0.0

                cash_available = portfolio.cash_balance

                if cash_available <= 0:
                    logger.warning(
                        f"No cash available to buy {symbol}. "
                        f"Cash balance: {cash_available:.2f}"
                    )
                    return 0.0

                # Limit by available cash
                actual_value_to_invest = min(value_to_invest, cash_available)

                if actual_value_to_invest < value_to_invest:
                    logger.info(
                        f"Cash insuficiente para alcanzar target completo de {symbol}. "
                        f"Necesario: {value_to_invest:.2f}, Disponible: {cash_available:.2f}, "
                        f"Invirtiendo: {actual_value_to_invest:.2f}"
                    )

                raw_order_size = actual_value_to_invest / signal.price

                # Peso incremental sobre el total de la cartera
                incremental_weight = (
                    raw_order_size * signal.price
                ) / total_portfolio_value

                # Validamos contra constraints (riesgo, max weight, etc.)
                validated_weights = validate_weights(
                    {symbol: incremental_weight},
                    self.constraints,
                )

                final_incremental_weight = validated_weights.get(symbol, 0.0)

                validated_order_size = (
                    final_incremental_weight * total_portfolio_value / signal.price
                )

                logger.info(
                    f"Computed BUY order size for {symbol}: {validated_order_size:.4f} units "
                    f"(target_weight={target_weight:.4f}, "
                    f"current_qty={quantity_on_portfolio}, "
                    f"price={signal.price}, "
                    f"cash_available={cash_available:.2f})"
                )
                return float(validated_order_size)

            logger.warning(
                f"Signal type {signal.signal_type} not recognized, no operation.")
            return 0.0

        except Exception as e:
            logger.error(f"Error computing order size: {e}")
            raise

    async def calculate_total_value(self, portfolio: PortfolioDTO) -> float:
        """
        Calcula el valor total del portfolio (cash + valor de posiciones).
        """
        total_value = portfolio.cash_balance

        # Asumo que positions es Dict[str, float]
        for symbol, quantity in (portfolio.positions or {}).items():
            price = await self.extractor.get_lastest_price(
                symbol,
                timeframe="1h",
            )
            if price is None:
                logger.warning(
                    f"No OHLCV data for {symbol}, skipping valuation."
                )
                continue

            position_value = quantity * price
            total_value += position_value

        return total_value
