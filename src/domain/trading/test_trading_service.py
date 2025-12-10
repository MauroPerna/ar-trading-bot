import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.domain.trading.trading_service import TradingService
from src.domain.trading.dtos.order_dto import OrderDTO, OrderType, OrderStatus, OrderSide
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import (
    SignalTypeEnum,
    SignalStrengthEnum,
    SignalSourceEnum,
)


@pytest.fixture
def mock_db_client():
    """Mock del cliente de base de datos."""
    client = MagicMock()
    session = AsyncMock()
    client.get_session.return_value.__aenter__.return_value = session
    client.get_session.return_value.__aexit__.return_value = None
    return client


@pytest.fixture
def mock_portfolio_service():
    """Mock del PortfolioService."""
    portfolio = MagicMock()
    portfolio.compute_order_size = AsyncMock(return_value=10.0)
    return portfolio


@pytest.fixture
def mock_broker():
    """Mock del BrokerClient."""
    broker = MagicMock()

    async def place_order_side_effect(order: OrderDTO) -> OrderDTO:
        """Simula ejecución de orden."""
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_fill_price = order.limit_price or 100.0
        order.broker_id = f"broker-{uuid4().hex[:8]}"
        return order

    broker.place_order = AsyncMock(side_effect=place_order_side_effect)
    return broker


@pytest.fixture
def trading_service(mock_db_client, mock_portfolio_service, mock_broker):
    """Instancia del servicio con mocks."""
    return TradingService(
        db_client=mock_db_client,
        portfolio=mock_portfolio_service,
        broker=mock_broker,
    )


def create_signal(
    symbol: str = "AAPL",
    signal_type: SignalTypeEnum = SignalTypeEnum.BUY,
    confidence: float = 0.8,
    strength: SignalStrengthEnum = SignalStrengthEnum.STRONG,
    price: float = 150.0,
    source: SignalSourceEnum = SignalSourceEnum.MOMENTUM,
) -> SignalDTO:
    """Helper para crear señales de prueba."""
    return SignalDTO(
        symbol=symbol,
        signal_source=source,
        signal_type=signal_type,
        confidence=confidence,
        strength=strength,
        price=price,
    )


# ==================== TESTS DE SEÑALES BUY ====================


@pytest.mark.asyncio
async def test_buy_signal_creates_order(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal BUY con order_size > 0 debe crear y ejecutar orden.
    """
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalTypeEnum.BUY,
        price=150.0,
    )

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=10.0)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ) as MockOrderRepo:

        mock_signal_repo = MockSignalRepo.return_value
        mock_signal_repo.save = AsyncMock()

        mock_order_repo = MockOrderRepo.return_value
        mock_order_repo.save = AsyncMock()

        await trading_service.handle_signal(signal)

        # Verificar que se calculó el order size
        mock_portfolio_service.compute_order_size.assert_called_once_with(
            signal)

        # Verificar que se envió la orden al broker
        mock_broker.place_order.assert_called_once()
        order_sent = mock_broker.place_order.call_args[0][0]
        assert order_sent.symbol == "AAPL"
        assert order_sent.quantity == 10.0
        assert order_sent.order_type == OrderType.MARKET

        # Verificar que se guardó en DB
        mock_signal_repo.save.assert_called_once()
        mock_order_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_buy_signal_with_high_confidence(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal BUY con alta confianza procesa correctamente.
    """
    signal = create_signal(
        symbol="MSFT",
        signal_type=SignalTypeEnum.BUY,
        confidence=0.95,
        strength=SignalStrengthEnum.EXTREME,
        price=300.0,
    )

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=5.0)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ) as MockOrderRepo:

        MockSignalRepo.return_value.save = AsyncMock()
        MockOrderRepo.return_value.save = AsyncMock()

        await trading_service.handle_signal(signal)

        mock_broker.place_order.assert_called_once()
        order_sent = mock_broker.place_order.call_args[0][0]
        assert order_sent.symbol == "MSFT"
        assert order_sent.quantity == 5.0
        assert order_sent.limit_price == 300.0


# ==================== TESTS DE SEÑALES SELL ====================


@pytest.mark.asyncio
async def test_sell_signal_creates_order(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal SELL con order_size > 0 debe crear y ejecutar orden de venta.
    """
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalTypeEnum.SELL,
        price=145.0,
    )

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=15.0)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ) as MockOrderRepo:

        MockSignalRepo.return_value.save = AsyncMock()
        MockOrderRepo.return_value.save = AsyncMock()

        await trading_service.handle_signal(signal)

        mock_broker.place_order.assert_called_once()
        order_sent = mock_broker.place_order.call_args[0][0]
        assert order_sent.symbol == "AAPL"
        assert order_sent.quantity == 15.0
        assert order_sent.side == OrderSide.SELL


# ==================== TESTS DE SEÑALES SIN ACCIÓN ====================


@pytest.mark.asyncio
async def test_signal_with_zero_order_size_no_action(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal con order_size = 0 no debe crear orden.
    """
    signal = create_signal(symbol="AAPL", signal_type=SignalTypeEnum.BUY)

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=0.0)

    await trading_service.handle_signal(signal)

    # No se debe llamar al broker
    mock_broker.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_signal_with_none_order_size_no_action(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal con order_size = None no debe crear orden.
    """
    signal = create_signal(symbol="AAPL", signal_type=SignalTypeEnum.BUY)

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=None)

    await trading_service.handle_signal(signal)

    mock_broker.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_hold_signal_no_action(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal HOLD debe retornar order_size = 0 y no crear orden.
    """
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalTypeEnum.HOLD,
    )

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=0.0)

    await trading_service.handle_signal(signal)

    mock_broker.place_order.assert_not_called()


# ==================== TESTS DE SEÑALES NONE ====================


@pytest.mark.asyncio
async def test_none_signal_skipped(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal None debe ser ignorada sin errores.
    """
    await trading_service.handle_signal(None)

    # No se debe calcular order size ni llamar al broker
    mock_portfolio_service.compute_order_size.assert_not_called()
    mock_broker.place_order.assert_not_called()


# ==================== TESTS DE PERSISTENCIA ====================


@pytest.mark.asyncio
async def test_signal_and_order_saved_to_db(trading_service, mock_portfolio_service, mock_broker):
    """
    Tanto la señal como la orden ejecutada deben guardarse en DB.
    """
    signal = create_signal(
        symbol="GOOGL", signal_type=SignalTypeEnum.BUY, price=2800.0)

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=2.0)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ) as MockOrderRepo:

        mock_signal_repo = MockSignalRepo.return_value
        mock_signal_repo.save = AsyncMock()

        mock_order_repo = MockOrderRepo.return_value
        mock_order_repo.save = AsyncMock()

        await trading_service.handle_signal(signal)

        # Verificar que se guardó la señal
        mock_signal_repo.save.assert_called_once_with(signal)

        # Verificar que se guardó la orden ejecutada
        mock_order_repo.save.assert_called_once()
        saved_order = mock_order_repo.save.call_args[0][0]
        assert saved_order.status == OrderStatus.FILLED
        assert saved_order.filled_quantity == 2.0


# ==================== TESTS DE MANEJO DE ERRORES ====================


@pytest.mark.asyncio
async def test_portfolio_error_propagates(trading_service, mock_portfolio_service, mock_broker):
    """
    Error en portfolio.compute_order_size debe propagarse.
    """
    signal = create_signal(symbol="AAPL", signal_type=SignalTypeEnum.BUY)

    mock_portfolio_service.compute_order_size = AsyncMock(
        side_effect=Exception("Portfolio calculation error")
    )

    with pytest.raises(Exception, match="Portfolio calculation error"):
        await trading_service.handle_signal(signal)

    mock_broker.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_broker_error_propagates(trading_service, mock_portfolio_service, mock_broker):
    """
    Error en broker.place_order debe propagarse.
    """
    signal = create_signal(symbol="AAPL", signal_type=SignalTypeEnum.BUY)

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=10.0)
    mock_broker.place_order = AsyncMock(
        side_effect=Exception("Broker connection error")
    )

    with pytest.raises(Exception, match="Broker connection error"):
        await trading_service.handle_signal(signal)


@pytest.mark.asyncio
async def test_db_save_error_propagates(trading_service, mock_portfolio_service, mock_broker):
    """
    Error al guardar en DB debe propagarse.
    """
    signal = create_signal(symbol="AAPL", signal_type=SignalTypeEnum.BUY)

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=10.0)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ):

        mock_signal_repo = MockSignalRepo.return_value
        mock_signal_repo.save = AsyncMock(
            side_effect=Exception("Database write error")
        )

        with pytest.raises(Exception, match="Database write error"):
            await trading_service.handle_signal(signal)


# ==================== TESTS DE ORDEN EJECUTADA ====================


@pytest.mark.asyncio
async def test_executed_order_has_correct_attributes(trading_service, mock_portfolio_service, mock_broker):
    """
    La orden ejecutada debe tener los atributos correctos del broker.
    """
    signal = create_signal(
        symbol="TSLA",
        signal_type=SignalTypeEnum.BUY,
        price=250.0,
    )

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=8.0)

    # Simular respuesta del broker con precio de ejecución diferente
    async def broker_execution(order: OrderDTO) -> OrderDTO:
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_fill_price = 251.50  # Slippage
        order.broker_id = "BROKER-12345"
        return order

    mock_broker.place_order = AsyncMock(side_effect=broker_execution)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ) as MockOrderRepo:

        MockSignalRepo.return_value.save = AsyncMock()
        mock_order_repo = MockOrderRepo.return_value
        mock_order_repo.save = AsyncMock()

        await trading_service.handle_signal(signal)

        saved_order = mock_order_repo.save.call_args[0][0]
        assert saved_order.broker_id == "BROKER-12345"
        assert saved_order.average_fill_price == 251.50
        assert saved_order.filled_quantity == 8.0
        assert saved_order.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_partial_fill_order(trading_service, mock_portfolio_service, mock_broker):
    """
    Orden parcialmente ejecutada debe reflejar el fill parcial.
    """
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalTypeEnum.BUY,
        price=150.0,
    )

    mock_portfolio_service.compute_order_size = AsyncMock(return_value=100.0)

    async def partial_fill(order: OrderDTO) -> OrderDTO:
        order.status = OrderStatus.PARTIALLY_FILLED
        order.filled_quantity = 75.0  # Solo 75 de 100
        order.average_fill_price = 150.25
        order.broker_id = "BROKER-PARTIAL"
        return order

    mock_broker.place_order = AsyncMock(side_effect=partial_fill)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ) as MockOrderRepo:

        MockSignalRepo.return_value.save = AsyncMock()
        mock_order_repo = MockOrderRepo.return_value
        mock_order_repo.save = AsyncMock()

        await trading_service.handle_signal(signal)

        saved_order = mock_order_repo.save.call_args[0][0]
        assert saved_order.status == OrderStatus.PARTIALLY_FILLED
        assert saved_order.filled_quantity == 75.0
        assert saved_order.quantity == 100.0


# ==================== TESTS DE MÚLTIPLES SÍMBOLOS ====================


@pytest.mark.asyncio
async def test_multiple_signals_different_symbols(trading_service, mock_portfolio_service, mock_broker):
    """
    Múltiples señales para diferentes símbolos deben procesarse correctamente.
    """
    signals = [
        create_signal(
            symbol="AAPL", signal_type=SignalTypeEnum.BUY, price=150.0),
        create_signal(
            symbol="MSFT", signal_type=SignalTypeEnum.BUY, price=300.0),
        create_signal(symbol="GOOGL",
                      signal_type=SignalTypeEnum.SELL, price=2800.0),
    ]

    order_sizes = [10.0, 5.0, 3.0]
    call_count = 0

    async def dynamic_order_size(signal):
        nonlocal call_count
        size = order_sizes[call_count]
        call_count += 1
        return size

    mock_portfolio_service.compute_order_size = AsyncMock(
        side_effect=dynamic_order_size)

    with patch(
        "src.domain.trading.trading_service.SignalRepository"
    ) as MockSignalRepo, patch(
        "src.domain.trading.trading_service.OrderRepository"
    ) as MockOrderRepo:

        MockSignalRepo.return_value.save = AsyncMock()
        MockOrderRepo.return_value.save = AsyncMock()

        for signal in signals:
            await trading_service.handle_signal(signal)

        assert mock_broker.place_order.call_count == 3
        assert mock_portfolio_service.compute_order_size.call_count == 3


# ==================== TESTS DE SEÑALES EXIT/ALERT ====================


@pytest.mark.asyncio
async def test_exit_signal_with_zero_order_size(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal EXIT debe ser manejada por portfolio_service.
    Si compute_order_size retorna 0, no se genera orden.

    Nota: EXIT no mapea directamente a OrderSide (solo BUY/SELL).
    El portfolio_service debe decidir qué hacer con EXIT signals.
    """
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalTypeEnum.EXIT,
        price=140.0,
    )

    # EXIT debería ser manejado por portfolio_service
    # Si retorna 0, no se genera orden
    mock_portfolio_service.compute_order_size = AsyncMock(return_value=0.0)

    await trading_service.handle_signal(signal)

    mock_broker.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_alert_signal_no_order(trading_service, mock_portfolio_service, mock_broker):
    """
    Señal ALERT no debe generar orden (solo informativa).
    """
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalTypeEnum.ALERT,
        price=155.0,
    )

    # Alert debería retornar 0 en order_size
    mock_portfolio_service.compute_order_size = AsyncMock(return_value=0.0)

    await trading_service.handle_signal(signal)

    mock_broker.place_order.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
