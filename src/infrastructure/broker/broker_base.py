from typing import Protocol, Optional, List, Dict, Any
from src.commons.enums.broker_enums import Instruments, Countries
from src.domain.trading.dtos.order_dto import OrderDTO
from src.domain.portfolio.dtos.portfolio_dto import PortfolioDTO


class BrokerClient(Protocol):
    async def auth(self) -> None: ...
    async def get_portfolio(self) -> PortfolioDTO: ...

    async def get_instruments(
        self,
        instrument: Instruments,
        country: Countries,
    ) -> List[Dict[str, Any]]: ...

    async def place_order(self, order: OrderDTO) -> OrderDTO: ...
    async def get_order(self, broker_id: str) -> OrderDTO: ...
    async def cancel_order(self, broker_id: str) -> OrderDTO: ...
    async def positions(self) -> List[Dict[str, Any]]: ...


class IOLClientError(Exception):
    """Custom exception for IOL client errors."""
    pass


class AuthenticationError(IOLClientError):
    """Authentication error with IOL."""
    pass
