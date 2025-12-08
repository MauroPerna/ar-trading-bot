import httpx
import time
import asyncio
from typing import Dict, Optional, Any, List
import logging

from src.infrastructure.broker.broker_base import (
    BrokerClient,
    AuthenticationError,
    IOLClientError,
)
from src.infrastructure.config.settings import Settings
from src.commons.enums.broker_enums import Instruments, Countries
from src.domain.trading.dtos.order_dto import OrderDTO
from src.domain.portfolio.dtos.portfolio_dto import PortfolioDTO  # <- solo DTO plano

logger = logging.getLogger(__name__)


class IOLClient(BrokerClient):
    BASE_URL = "https://api.invertironline.com"
    TOKEN_ENDPOINT = f"{BASE_URL}/token"

    def __init__(self, config: Settings):
        self.config = config
        transport = httpx.HTTPTransport(retries=3)
        self.client = httpx.AsyncClient(transport=transport)
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    async def init(self) -> None:
        try:
            await self.refresh()
        except Exception:
            await self.auth()

    async def auth(self) -> None:
        logger.info("Authenticating with IOL")

        async with self._token_lock:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        self.TOKEN_ENDPOINT,
                        data={
                            "username": self.config.iol_username,
                            "password": self.config.iol_password,
                            "grant_type": "password",
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    self._token = data["access_token"]
                    self._refresh_token = data["refresh_token"]
                    self._exp = time.time() + data["expires_in"] - 60

                    logger.info("Successfully authenticated with IOL")

                except httpx.HTTPStatusError as e:
                    logger.error(f"Authentication failed: {e}")
                    raise AuthenticationError(
                        f"Failed to authenticate: {e}"
                    ) from e
                except Exception as e:
                    logger.error(
                        f"Unexpected error during authentication: {e}"
                    )
                    raise AuthenticationError(f"Unexpected error: {e}") from e

    async def refresh(self) -> None:
        logger.info("Refreshing IOL token")

        async with self._token_lock:
            if not hasattr(self, "_refresh_token"):
                raise Exception("No refresh token available")

            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        self.TOKEN_ENDPOINT,
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": self._refresh_token,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    self._token = data["access_token"]
                    self._refresh_token = data["refresh_token"]
                    self._exp = time.time() + data["expires_in"] - 60

                    logger.info("Successfully refreshed IOL token")

                except httpx.HTTPStatusError as e:
                    logger.error(f"Token refresh failed: {e}")
                    await self.auth()
                except Exception as e:
                    logger.error(f"Unexpected error during refresh: {e}")
                    await self.auth()

    async def _ensure_valid_token(self) -> None:
        if not hasattr(self, "_token") or time.time() >= getattr(
            self, "_exp", 0
        ):
            await self.init()

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------
    async def get_portfolio(self) -> PortfolioDTO:
        """
        Devuelve un PortfolioDTO con:
        - cash_balance: efectivo disponible
        - positions: Dict[symbol, quantity]
        directamente desde IOL (source of truth).
        """
        await self._ensure_valid_token()

        logger.debug("Fetching portfolio data from IOL")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/api/v2/estadocuenta",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                response.raise_for_status()
                data = response.json()

                logger.debug("Portfolio data fetched successfully from IOL")
                return self._map_iol_portfolio_to_dto(data)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.info("Token expired, refreshing and retrying")
                    await self.refresh()

                    response = await client.get(
                        f"{self.BASE_URL}/api/v2/estadocuenta",
                        headers={"Authorization": f"Bearer {self._token}"},
                    )
                    response.raise_for_status()
                    data = response.json()

                    return self._map_iol_portfolio_to_dto(data)
                else:
                    logger.error(f"Request failed: {e}")
                    raise IOLClientError(
                        f"Failed to get portfolio: {e}"
                    ) from e

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise IOLClientError(
                    f"Unexpected error getting portfolio: {e}"
                ) from e

    def _map_iol_portfolio_to_dto(self, data: Dict[str, Any]) -> PortfolioDTO:
        """
        Mapea la respuesta cruda de IOL a PortfolioDTO.

        Asunciones (ajustá si la API real difiere):
        - data["efectivo"]["saldo"] -> efectivo disponible
        - data["posiciones"] -> lista de objetos con:
            - "simbolo" / "ticker"
            - "cantidad"
        """
        # efectivo
        try:
            efectivo = float(data.get("efectivo", {}).get("saldo", 0.0))
        except Exception:
            logger.warning(
                "No se pudo parsear efectivo de la respuesta de IOL, usando 0.0")
            efectivo = 0.0

        positions_dict: Dict[str, float] = {}

        raw_positions = data.get("posiciones", []) or []
        for p in raw_positions:
            symbol = p.get("simbolo") or p.get("ticker") or ""
            if not symbol:
                continue
            try:
                qty = float(p.get("cantidad", 0.0))
            except Exception:
                qty = 0.0

            positions_dict[symbol] = qty

        return PortfolioDTO(
            cash_balance=efectivo,
            positions=positions_dict,
        )

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------
    async def get_instruments(
        self,
        instrument: Instruments,
        country: Optional[Countries] = Countries.ARGENTINA,
    ) -> List[Dict[str, Any]]:
        await self._ensure_valid_token()

        logger.debug(
            f"Fetching {instrument.value} instruments for {country.value}"
        )

        url = (
            f"{self.BASE_URL}/api/v2/Cotizaciones/"
            f"{instrument.value}/{country.value}/Todos"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                response.raise_for_status()
                data = response.json()

                logger.debug("Instruments data fetched successfully")
                if isinstance(data, list):
                    return data
                return [data]

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.info("Token expired, refreshing and retrying")
                    await self.refresh()

                    response = await client.get(
                        url,
                        headers={"Authorization": f"Bearer {self._token}"},
                    )
                    response.raise_for_status()
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    return [data]
                else:
                    logger.error(f"Request failed: {e}")
                    raise IOLClientError(
                        f"Failed to get instruments: {e}"
                    ) from e

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise IOLClientError(
                    f"Unexpected error getting instruments: {e}"
                ) from e

    # ------------------------------------------------------------------
    # Orders – todavía sin implementación
    # ------------------------------------------------------------------
    async def place_order(self, order: OrderDTO) -> OrderDTO:
        raise NotImplementedError("place_order is not implemented yet")

    async def get_order(self, broker_id: str) -> OrderDTO:
        raise NotImplementedError("get_order is not implemented yet")

    async def cancel_order(self, broker_id: str) -> OrderDTO:
        raise NotImplementedError("cancel_order is not implemented yet")

    async def positions(self) -> List[Dict[str, Any]]:
        raise NotImplementedError("positions is not implemented yet")
