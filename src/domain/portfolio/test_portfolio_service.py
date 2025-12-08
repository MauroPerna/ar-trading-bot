"""
Tests para PortfolioService.compute_order_size

Cubre diferentes escenarios:
- Señales de BUY con diferentes target weights
- Señales de SELL
- Casos edge: portfolio vacío, precios inválidos, sin weights activos

VERSIÓN CORREGIDA: Mockea correctamente extractor.get_lastest_price()
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.portfolio.portfolio_service import PortfolioService
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import (
    SignalTypeEnum,
    SignalStrengthEnum,
    SignalSourceEnum,
)
from src.infrastructure.database.models.portfolio_model import PortfolioModel


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
    # Mockear el método get_lastest_price como AsyncMock por defecto
    extractor.get_lastest_price = AsyncMock(return_value=150.0)
    return extractor


@pytest.fixture
def portfolio_service(mock_db_client, mock_extractor, mock_optimizer):
    """Instancia del servicio con mocks."""
    return PortfolioService(
        db_client=mock_db_client,
        extractor=mock_extractor,
        optimizer=mock_optimizer,
    )


# ==================== TESTS DE SEÑALES BUY ====================


@pytest.mark.asyncio
async def test_buy_signal_first_purchase(portfolio_service):
    """
    Señal BUY para símbolo no existente en portfolio (primera compra).
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=10000.0,
        positions={},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.15}
        )

        # No hay posiciones, así que get_lastest_price no se llamará
        # pero lo dejamos mockeado por si acaso

        order_size = await portfolio_service.compute_order_size(signal)

        expected_order = 10000.0 * 0.15 / 150.0  # 10 units
        assert pytest.approx(order_size, rel=1e-2) == expected_order
        assert order_size > 0


@pytest.mark.asyncio
async def test_buy_signal_incremental_purchase(portfolio_service):
    """
    Señal BUY para símbolo que ya tiene posición (compra incremental).

    Portfolio tiene posiciones, así que calculate_total_value se llamará
    y necesitará extractor.get_lastest_price()
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=5000.0,
        positions={"AAPL": 20.0},  # 20 * 150 = 3,000
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.EXTREME,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.50}
        )

        # CRÍTICO: Mockear get_lastest_price para que retorne el precio de AAPL
        mock_extractor = portfolio_service.extractor
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
async def test_buy_signal_already_above_target(portfolio_service):
    """
    Señal BUY pero la posición ya está por encima del target weight.
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=2500.0,
        positions={"AAPL": 50.0},  # 50 * 150 = 7,500
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.VOLUME,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.7,
        strength=SignalStrengthEnum.MODERATE,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.50}
        )

        # Mockear get_lastest_price
        mock_extractor = portfolio_service.extractor
        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        # Total: 2500 + 7500 = 10000
        # Target: 10000 * 0.50 = 5000
        # Current: 50 * 150 = 7500
        # Ya está por encima, no comprar
        assert order_size == 0.0


@pytest.mark.asyncio
async def test_buy_signal_zero_target_weight(portfolio_service):
    """
    Señal BUY pero el target weight es 0 (no está en el portfolio óptimo).
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=10000.0,
        positions={},
    )

    signal = SignalDTO(
        symbol="TSLA",
        signal_source=SignalSourceEnum.VOLATILITY,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.6,
        strength=SignalStrengthEnum.WEAK,
        price=200.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.30, "MSFT": 0.40, "GOOGL": 0.30}
        )

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


# ==================== TESTS DE SEÑALES SELL ====================


@pytest.mark.asyncio
async def test_sell_signal_full_position(portfolio_service):
    """
    Señal SELL con posición existente (cierre completo).
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=5000.0,
        positions={"AAPL": 30.0},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.RISK,
        signal_type=SignalTypeEnum.SELL,
        confidence=0.85,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(return_value={})

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == -30.0


@pytest.mark.asyncio
async def test_sell_signal_no_position(portfolio_service):
    """
    Señal SELL pero no hay posición del símbolo.
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=10000.0,
        positions={"MSFT": 20.0},  # Solo MSFT
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.STRUCTURE,
        signal_type=SignalTypeEnum.SELL,
        confidence=0.75,
        strength=SignalStrengthEnum.MODERATE,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(return_value={})

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


# ==================== TESTS DE CASOS EDGE ====================


@pytest.mark.asyncio
async def test_no_portfolio_in_db(portfolio_service):
    """
    No existe portfolio en la base de datos.
    """
    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=None
        )

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


@pytest.mark.asyncio
async def test_invalid_price_in_signal(portfolio_service):
    """
    Señal con precio inválido (None o negativo).
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=10000.0,
        positions={},
    )

    # --- Señal sin precio ---
    signal_no_price = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=None,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
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

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        order_size = await portfolio_service.compute_order_size(
            signal_negative_price
        )

        assert order_size == 0.0


@pytest.mark.asyncio
async def test_zero_total_portfolio_value(portfolio_service):
    """
    Portfolio con valor total en 0 o negativo.
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=0.0,
        positions={},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.15}
        )

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


@pytest.mark.asyncio
async def test_no_active_weights(portfolio_service):
    """
    No hay weights activos del optimizador.
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=10000.0,
        positions={},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.VOLATILITY,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(return_value=None)

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


# ==================== TESTS DE VALIDACIÓN DE CONSTRAINTS ====================


@pytest.mark.asyncio
async def test_buy_with_constraints_validation(portfolio_service):
    """
    Señal BUY que debe pasar por validate_weights (constraints).
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=10000.0,
        positions={},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=100.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo, patch(
        "src.domain.portfolio.portfolio_service.validate_weights"
    ) as mock_validate:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.20}
        )

        mock_validate.return_value = {"AAPL": 0.20}

        order_size = await portfolio_service.compute_order_size(signal)

        mock_validate.assert_called_once()

        # Order size esperado: 20 units (10000 * 0.20 / 100)
        assert pytest.approx(order_size, rel=1e-2) == 20.0


# ==================== TEST DE MÚLTIPLES POSICIONES ====================


@pytest.mark.asyncio
async def test_multiple_positions_portfolio(portfolio_service):
    """
    Portfolio con múltiples posiciones, señal para una de ellas.
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=5000.0,
        positions={
            "AAPL": 20.0,   # @ 150 = 3,000
            "MSFT": 30.0,   # @ 200 = 6,000
            "GOOGL": 10.0,  # @ 600 = 6,000
        },
    )

    signal = SignalDTO(
        symbol="MSFT",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.EXTREME,
        price=200.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={
                "AAPL": 0.30,
                "MSFT": 0.40,
                "GOOGL": 0.30,
            }
        )

        # CRÍTICO: Mockear get_lastest_price para retornar precios según el símbolo
        mock_extractor = portfolio_service.extractor

        async def get_price_side_effect(symbol, **kwargs):
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
async def test_exception_handling(portfolio_service):
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

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception, match="Database error"):
            await portfolio_service.compute_order_size(signal)


# ==================== TESTS DE CASH LIMITADO ====================


@pytest.mark.asyncio
async def test_buy_signal_insufficient_cash(portfolio_service):
    """
    Señal BUY con cash insuficiente para alcanzar el target completo.

    Escenario:
    - Portfolio: $10,000 total
    - Cash: $300 disponible
    - Posiciones: AAPL 50 units @ $150 = $7,500
                  MSFT 10 units @ $200 = $2,000
    - Total value: 300 + 7,500 + 2,000 = 9,800
    - Target weight AAPL: 80% = $7,840
    - Current AAPL value: $7,500
    - Necesita: $340
    - Cash disponible: $300 ❌ Insuficiente

    Resultado esperado: Solo compra lo que puede con $300
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=300.0,  # Solo $300 disponible
        positions={
            "AAPL": 50.0,  # $7,500
            "MSFT": 10.0,  # $2,000
        },
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.80, "MSFT": 0.20}
        )

        # Mock extractor para calcular total value
        mock_extractor = portfolio_service.extractor

        async def get_price_side_effect(symbol, **kwargs):
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
async def test_buy_signal_no_cash_available(portfolio_service):
    """
    Señal BUY pero NO hay cash disponible (cash = 0).

    Escenario:
    - Cash: $0
    - Posiciones existentes: AAPL 50 units @ $150 = $7,500
    - Target weight AAPL: 80% 

    Resultado esperado: order_size = 0 (no puede comprar sin cash)
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=0.0,  # ❌ Sin cash
        positions={"AAPL": 50.0},  # $7,500
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.9,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.80}
        )

        mock_extractor = portfolio_service.extractor
        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        # Sin cash, no puede comprar nada
        assert order_size == 0.0


@pytest.mark.asyncio
async def test_buy_signal_partial_cash_multiple_symbols(portfolio_service):
    """
    Señal BUY con cash limitado en portfolio con múltiples posiciones.

    Escenario:
    - Cash: $500
    - Posiciones: AAPL 10 units @ $150 = $1,500
                  MSFT 5 units @ $200 = $1,000
                  GOOGL 2 units @ $600 = $1,200
    - Total value: 500 + 1,500 + 1,000 + 1,200 = $4,200
    - Target MSFT: 40% = $1,680
    - Current MSFT: $1,000
    - Necesita: $680
    - Cash disponible: $500 ❌ Solo puede invertir $500

    Resultado: Compra solo $500 worth de MSFT = 2.5 units
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=500.0,  # $500 disponible
        positions={
            "AAPL": 10.0,   # $1,500
            "MSFT": 5.0,    # $1,000
            "GOOGL": 2.0,   # $1,200
        },
    )

    signal = SignalDTO(
        symbol="MSFT",
        signal_source=SignalSourceEnum.TREND,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.85,
        strength=SignalStrengthEnum.STRONG,
        price=200.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={
                "AAPL": 0.30,
                "MSFT": 0.40,
                "GOOGL": 0.30,
            }
        )

        mock_extractor = portfolio_service.extractor

        async def get_price_side_effect(symbol, **kwargs):
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
async def test_buy_signal_exact_cash_needed(portfolio_service):
    """
    Señal BUY donde el cash disponible es exactamente lo que se necesita.

    Escenario:
    - Cash: $1,000
    - Posiciones: AAPL 20 units @ $150 = $3,000
    - Total value: 1,000 + 3,000 = $4,000
    - Target AAPL: 100% = $4,000
    - Current AAPL: $3,000
    - Necesita: $1,000
    - Cash disponible: $1,000 ✅ Perfecto!

    Resultado: Compra exactamente $1,000 / $150 = 6.67 units
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=1000.0,
        positions={"AAPL": 20.0},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.95,
        strength=SignalStrengthEnum.EXTREME,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 1.00}  # 100% en AAPL
        )

        mock_extractor = portfolio_service.extractor
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
async def test_buy_signal_negative_cash_balance(portfolio_service):
    """
    Señal BUY con cash balance negativo (edge case raro pero posible).

    Escenario:
    - Cash: -$100 (cuenta en negativo)
    - Posiciones: AAPL 50 units @ $150 = $7,500

    Resultado esperado: order_size = 0 (no puede comprar con cash negativo)
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=-100.0,  # ❌ Cash negativo
        positions={"AAPL": 50.0},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.BUY,
        confidence=0.8,
        strength=SignalStrengthEnum.STRONG,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo, patch(
        "src.domain.portfolio.portfolio_service.PortfolioWeightsRepository"
    ) as MockWeightsRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        mock_weights_repo = MockWeightsRepo.return_value
        mock_weights_repo.get_active_weights = AsyncMock(
            return_value={"AAPL": 0.90}
        )

        mock_extractor = portfolio_service.extractor
        mock_extractor.get_lastest_price = AsyncMock(return_value=150.0)

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


@pytest.mark.asyncio
async def test_hold_signal_no_action(portfolio_service):
    """
    Señal HOLD (no se espera acción de compra o venta).
    """
    portfolio = PortfolioModel(
        id="portfolio-1",
        cash_balance=5000.0,
        positions={"AAPL": 20.0},
    )

    signal = SignalDTO(
        symbol="AAPL",
        signal_source=SignalSourceEnum.MOMENTUM,
        signal_type=SignalTypeEnum.HOLD,
        confidence=0.5,
        strength=SignalStrengthEnum.MODERATE,
        price=150.0,
    )

    with patch(
        "src.domain.portfolio.portfolio_service.PortfolioRepository"
    ) as MockPortfolioRepo:

        mock_portfolio_repo = MockPortfolioRepo.return_value
        mock_portfolio_repo.get_current_portfolio = AsyncMock(
            return_value=portfolio
        )

        order_size = await portfolio_service.compute_order_size(signal)

        assert order_size == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
