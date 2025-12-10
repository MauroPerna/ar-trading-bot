import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.portfolio.portfolio_service import PortfolioService
from src.domain.portfolio.dtos.portfolio_dto import PortfolioDTO
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
def mock_optimizer():
    """Mock del optimizador."""
    optimizer = MagicMock()
    optimizer.__class__.__name__ = "HRPOptimizer"
    return optimizer


@pytest.fixture
def mock_extractor():
    """Mock del extractor OHLCVService."""
    extractor = MagicMock()
    extractor.get_lastest_price = AsyncMock(return_value=150.0)
    return extractor


@pytest.fixture
def mock_broker():
    """Mock del BrokerClient."""
    broker = MagicMock()
    broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=10000.0,
        positions={},
    ))
    return broker


@pytest.fixture
def portfolio_service(mock_db_client, mock_extractor, mock_optimizer, mock_broker):
    """Instancia del servicio con mocks."""
    return PortfolioService(
        db_client=mock_db_client,
        extractor=mock_extractor,
        optimizer=mock_optimizer,
        broker=mock_broker,
    )


def create_mock_weights_repo(weights_dict):
    """Helper para crear mock de weights que retorna lista de objetos."""
    if weights_dict is None:
        return None
    weights_list = []
    for symbol, weight in weights_dict.items():
        w = MagicMock()
        w.symbol = symbol
        w.weight = weight
        weights_list.append(w)
    return weights_list


# ==================== TESTS DE SEÑALES BUY ====================


@pytest.mark.asyncio
async def test_buy_signal_first_purchase(portfolio_service, mock_broker):
    """
    Señal BUY para símbolo no existente en portfolio (primera compra).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=10000.0,
        positions={},
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.15})
        )

        order_size = await portfolio_service.compute_order_size(signal)

        expected_order = 10000.0 * 0.15 / 150.0  # 10 units
        assert pytest.approx(order_size, rel=1e-2) == expected_order
        assert order_size > 0


@pytest.mark.asyncio
async def test_buy_signal_incremental_purchase(portfolio_service, mock_broker, mock_extractor):
    """
    Señal BUY para símbolo que ya tiene posición (compra incremental).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=5000.0,
        positions={"AAPL": 20.0},  # 20 * 150 = 3,000
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.EXTREME,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.50})
        )

        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        # Total portfolio value: 5000 (cash) + 20*150 (AAPL) = 8000
        # Target: 8000 * 0.50 = 4000
        # Current value: 20 * 150 = 3000
        # Need: 4000 - 3000 = 1000
        # Order size: 1000 / 150 = 6.67 units
        expected_order = 1000.0 / 150.0
        assert pytest.approx(order_size, rel=1e-2) == expected_order


@pytest.mark.asyncio
async def test_buy_signal_already_above_target(portfolio_service, mock_broker, mock_extractor):
    """
    Señal BUY pero la posición ya está por encima del target weight.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=2500.0,
        positions={"AAPL": 50.0},  # 50 * 150 = 7,500
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.VOLUME,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.7,
        strength=SignalStrengthEnum.MODERATE,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.50})
        )

        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        # Total: 2500 + 7500 = 10000
        # Target: 10000 * 0.50 = 5000
        # Current: 50 * 150 = 7500
        # Ya está por encima, no comprar
        assert order_size == 0.0


@pytest.mark.asyncio
async def test_buy_signal_zero_target_weight(portfolio_service, mock_broker):
    """
    Señal BUY pero el target weight es 0 (no está en el portfolio óptimo).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=10000.0,
        positions={},
    ))

    signal = SignalDTO(
        symbol="TSLA",
        signal_source=SignalSourceEnum.VOLATILITY,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.6,
        strength=SignalStrengthEnum.WEAK,
        price=200.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo(
                {"AAPL": 0.30, "MSFT": 0.40, "GOOGL": 0.30})
        )

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


# ==================== TESTS DE SEÑALES SELL ====================


@pytest.mark.asyncio
async def test_sell_signal_full_position(portfolio_service, mock_broker):
    """
    Señal SELL con posición existente (cierre completo).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=5000.0,
        positions={"AAPL": 30.0},
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.RISK,
        signal_type=SignalTypeEnum.SELL,
        confidence=0.85,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:
        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(return_value=[])

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == -30.0


@pytest.mark.asyncio
async def test_sell_signal_no_position(portfolio_service, mock_broker):
    """
    Señal SELL pero no hay posición del símbolo.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=10000.0,
        positions={"MSFT": 20.0},  # Solo MSFT
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.STRUCTURE,
        signal_type=SignalTypeEnum.SELL,
        confidence=0.75,
        strength=SignalStrengthEnum.MODERATE,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:
        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(return_value=[])

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


# ==================== TESTS DE CASOS EDGE ====================


@pytest.mark.asyncio
async def test_no_portfolio_from_broker(portfolio_service, mock_broker):
    """
    Broker no retorna portfolio (None).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=None)

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    order_size = await portfolio_service.compute_order_size(signal)

    assert order_size == 0.0


@pytest.mark.asyncio
async def test_invalid_price_in_signal(portfolio_service):
    """
    Señal con precio inválido (None o negativo).
    """
    # --- Señal sin precio ---
    signal_no_price = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=None,
    )

    order_size = await portfolio_service.compute_order_size(signal_no_price)
    assert order_size == 0.0

    # --- Señal con precio negativo ---
    signal_negative_price = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=-100.0,
    )

    order_size = await portfolio_service.compute_order_size(signal_negative_price)
    assert order_size == 0.0


@pytest.mark.asyncio
async def test_zero_total_portfolio_value(portfolio_service, mock_broker):
    """
    Portfolio con valor total en 0 o negativo.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=0.0,
        positions={},
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.15})
        )

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


@pytest.mark.asyncio
async def test_no_active_weights(portfolio_service, mock_broker):
    """
    No hay weights activos del optimizador.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=10000.0,
        positions={},
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.VOLATILITY,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(return_value=None)

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


# ==================== TESTS DE VALIDACIÓN DE CONSTRAINTS ====================


@pytest.mark.asyncio
async def test_buy_with_constraints_validation(portfolio_service, mock_broker):
    """
    Señal BUY que debe pasar por validate_weights (constraints).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=10000.0,
        positions={},
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=100.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo, patch(
        "src.domain.portfolio.portfolio_service.validate_weights"
    ) as mock_validate:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.20})
        )

        mock_validate.return_value = {"AAPL": 0.20}

        order_size = await portfolio_service.compute_order_size(signal)

        mock_validate.assert_called_once()

        # Order size esperado: 20 units (10000 * 0.20 / 100)
        assert pytest.approx(order_size, rel=1e-2) == 20.0


# ==================== TEST DE MÚLTIPLES POSICIONES ====================


@pytest.mark.asyncio
async def test_multiple_positions_portfolio(portfolio_service, mock_broker, mock_extractor):
    """
    Portfolio con múltiples posiciones, señal para una de ellas.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=5000.0,
        positions={
            "AAPL": 20.0,   # @ 150 = 3,000
            "MSFT": 30.0,   # @ 200 = 6,000
            "GOOGL": 10.0,  # @ 600 = 6,000
        },
    ))

    signal = SignalDTO(
        symbol="MSFT",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.EXTREME,
        price=200.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({
                "AAPL": 0.30,
                "MSFT": 0.40,
                "GOOGL": 0.30,
            })
        )

        async def get_price_side_effect(symbol, **_):
            """Retorna precios diferentes según el símbolo."""
            prices = {
                "AAPL": 150.0,
                "MSFT": 200.0,
                "GOOGL": 600.0,
            }
            return prices.get(symbol, 100.0)

        mock_extractor.get_lastest_price = get_price_side_effect

        order_size = await portfolio_service.compute_order_size(signal)

        # Total portfolio: 5000 + (20*150) + (30*200) + (10*600)
        #                = 5000 + 3000 + 6000 + 6000 = 20000
        # Target for MSFT: 20000 * 0.40 = 8000
        # Current MSFT value: 30 * 200 = 6000
        # Need: 8000 - 6000 = 2000
        # Order size: 2000 / 200 = 10 units
        expected_order = 2000.0 / 200.0
        assert pytest.approx(order_size, rel=1e-2) == expected_order


# ==================== TEST DE EXCEPCIÓN ====================


@pytest.mark.asyncio
async def test_exception_handling(portfolio_service, mock_broker):
    """
    Se lanza una excepción durante el proceso.
    """
    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    mock_broker.get_portfolio = AsyncMock(
        side_effect=Exception("Broker connection error")
    )

    with pytest.raises(Exception, match="Broker connection error"):
        await portfolio_service.compute_order_size(signal)


# ==================== TESTS DE CASH LIMITADO ====================


@pytest.mark.asyncio
async def test_buy_signal_insufficient_cash(portfolio_service, mock_broker, mock_extractor):
    """
    Señal BUY con cash insuficiente para alcanzar el target completo.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=300.0,  # Solo $300 disponible
        positions={
            "AAPL": 50.0,  # $7,500
            "MSFT": 10.0,  # $2,000
        },
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.80, "MSFT": 0.20})
        )

        async def get_price_side_effect(symbol, **_):
            prices = {"AAPL": 150.0, "MSFT": 200.0}
            return prices.get(symbol, 100.0)

        mock_extractor.get_lastest_price = get_price_side_effect

        order_size = await portfolio_service.compute_order_size(signal)

        # Total value: 300 + 7500 + 2000 = 9800
        # Target: 9800 * 0.80 = 7840
        # Current: 7500
        # Necesita: 340
        # Solo tiene: 300
        # Debería comprar: 300 / 150 = 2 units
        expected_order = 300.0 / 150.0
        assert pytest.approx(order_size, rel=1e-2) == expected_order


@pytest.mark.asyncio
async def test_buy_signal_no_cash_available(portfolio_service, mock_broker, mock_extractor):
    """
    Señal BUY pero NO hay cash disponible (cash = 0).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=0.0,  # Sin cash
        positions={"AAPL": 50.0},  # $7,500
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.80})
        )

        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        # Sin cash, no puede comprar nada
        assert order_size == 0.0


@pytest.mark.asyncio
async def test_buy_signal_partial_cash_multiple_symbols(portfolio_service, mock_broker, mock_extractor):
    """
    Señal BUY con cash limitado en portfolio con múltiples posiciones.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=500.0,  # $500 disponible
        positions={
            "AAPL": 10.0,   # $1,500
            "MSFT": 5.0,    # $1,000
            "GOOGL": 2.0,   # $1,200
        },
    ))

    signal = SignalDTO(
        symbol="MSFT",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.85,
        strength=SignalStrengthEnum.STRONG,
        price=200.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({
                "AAPL": 0.30,
                "MSFT": 0.40,
                "GOOGL": 0.30,
            })
        )

        async def get_price_side_effect(symbol, **_):
            prices = {
                "AAPL": 150.0,
                "MSFT": 200.0,
                "GOOGL": 600.0,
            }
            return prices.get(symbol, 100.0)

        mock_extractor.get_lastest_price = get_price_side_effect

        order_size = await portfolio_service.compute_order_size(signal)

        # Total: 500 + 1500 + 1000 + 1200 = 4200
        # Target MSFT: 4200 * 0.40 = 1680
        # Current MSFT: 1000
        # Necesita: 680
        # Solo tiene: 500
        # Compra: 500 / 200 = 2.5 units
        expected_order = 500.0 / 200.0
        assert pytest.approx(order_size, rel=1e-2) == expected_order


@pytest.mark.asyncio
async def test_buy_signal_exact_cash_needed(portfolio_service, mock_broker, mock_extractor):
    """
    Señal BUY donde el cash disponible es exactamente lo que se necesita.
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=1000.0,
        positions={"AAPL": 20.0},
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.95,
        strength=SignalStrengthEnum.EXTREME,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo(
                {"AAPL": 1.00})  # 100% en AAPL
        )

        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        # Total: 1000 + 3000 = 4000
        # Target: 4000 * 1.00 = 4000
        # Current: 3000
        # Necesita: 1000
        # Tiene: 1000
        # Compra: 1000 / 150 = 6.67 units
        expected_order = 1000.0 / 150.0
        assert pytest.approx(order_size, rel=1e-2) == expected_order


@pytest.mark.asyncio
async def test_buy_signal_negative_cash_balance(portfolio_service, mock_broker, mock_extractor):
    """
    Señal BUY con cash balance negativo (edge case raro pero posible).
    """
    mock_broker.get_portfolio = AsyncMock(return_value=PortfolioDTO(
        cash_balance=-100.0,  # Cash negativo
        positions={"AAPL": 50.0},
    ))

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value=create_mock_weights_repo({"AAPL": 0.90})
        )

        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


@pytest.mark.asyncio
async def test_hold_signal_no_action(portfolio_service):
    """
    Señal HOLD (no se espera acción de compra o venta).
    """
    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.HOLD,
        confidence=0.5,
        strength=SignalStrengthEnum.MODERATE,
        price=150.0,
    )

    order_size = await portfolio_service.compute_order_size(signal)

    assert order_size == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
