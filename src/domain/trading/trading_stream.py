import logging
import asyncio
from rx import operators as ops

from src.domain.signals.signals_bus import signal_bus
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.domain.trading.trading_service import TradingService

logger = logging.getLogger(__name__)


def setup_trading_stream(trading_service: TradingService) -> None:
    """
    Conecta el bus de señales con el TradingService usando RxPy.
    """

    def _handle_signal_async(signal: SignalDTO) -> None:
        logger.info(
            f"🔔 Nueva señal recibida en trading stream: "
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
        # agrupar por símbolo
        ops.group_by(lambda s: s.symbol),
        # dentro de cada símbolo, evitamos repeticiones muy parecidas
        ops.flat_map(
            lambda group: group.pipe(
                ops.distinct_until_changed(_distinct_key),
            )
        ),
    ).subscribe(
        on_next=_handle_signal_async,
        on_error=lambda e: logger.error(f"❌ Error en trading stream: {e}"),
        on_completed=lambda: logger.info("✔️ trading stream completado"),
    )

    logger.info("🔗 Trading stream conectado a signal_bus")
