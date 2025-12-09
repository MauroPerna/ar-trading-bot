import logging
import asyncio
from rx import operators as ops

from src.domain.signals.signals_bus import signal_bus
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.domain.trading.trading_service import TradingService

logger = logging.getLogger(__name__)


def setup_trading_stream(trading_service: TradingService) -> None:
    """
    Connects signal bus to TradingService using RxPy.
    """

    def _handle_signal_async(signal: SignalDTO) -> None:
        logger.info(
            f"🔔 New signal received in trading stream: "
            f"{signal.symbol} - {signal.signal_type.value} "
            f"({signal.strength.value}, conf={signal.confidence:.2f})"
        )
        asyncio.create_task(trading_service.handle_signal(signal))

    def _distinct_key(s: SignalDTO):
        return (
            s.symbol,
            s.signal_type,
            s.strength,
            round(s.confidence, 2),
        )

    signal_bus.pipe(
        ops.filter(lambda s: s is not None),
        # group by symbol
        ops.group_by(lambda s: s.symbol),
        # within each symbol, avoid similar repetitions
        ops.flat_map(
            lambda group: group.pipe(
                ops.distinct_until_changed(_distinct_key),
            )
        ),
    ).subscribe(
        on_next=_handle_signal_async,
        on_error=lambda e: logger.error(f"❌ Error in trading stream: {e}"),
        on_completed=lambda: logger.info("✔️ Trading stream completed"),
    )

    logger.info("🔗 Trading stream connected to signal_bus")
