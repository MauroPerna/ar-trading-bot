import os
import pytest
import logging
from src.application.container import container
from src.commons.enums.broker_enums import Instruments, Countries
from src.domain.portfolio.dtos.portfolio_dto import PortfolioDTO
from src.infrastructure.broker.broker_fake import FakeBrokerClient

pytestmark = pytest.mark.integration
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_auth():
    client = container.broker()

    if isinstance(client, FakeBrokerClient):
        return

    await client.auth()

    token = getattr(client, "_token", None)
    exp = getattr(client, "_exp", 0)

    logger.info(f"Token obtained: {'***' if token else 'None'}")
    logger.info(f"Expiration obtained: {exp}")

    assert token
    assert exp > 0


@pytest.mark.asyncio
async def test_get_portfolio():
    client = container.broker()
    portfolio = await client.get_portfolio()

    logger.info(f"Portfolio obtained: {portfolio}")

    assert isinstance(portfolio, PortfolioDTO)


# @pytest.mark.asyncio
# async def test_get_instruments():
#     client = container.broker()
#     response = []
#     instruments = [Instruments.OPCIONES, Instruments.ACCIONES, Instruments.FUTUROS, Instruments.CEDEARS,
#                    Instruments.TITULOS_PUBLICOS, Instruments.ADRS, Instruments.ON, Instruments.letras]

#     for instrument in instruments:
#         result = await client.get_instruments(instrument)
#         response.extend(result)

#     assert isinstance(response, list)
#     assert len(response) > 0
