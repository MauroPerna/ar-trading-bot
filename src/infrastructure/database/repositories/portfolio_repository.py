import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.portfolio_model import PortfolioModel
from src.domain.portfolio.dtos.portfolio_dto import PortfolioDTO

logger = logging.getLogger(__name__)


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------ EXISTENTES ------------------

    async def get_current_portfolio(self) -> Optional[PortfolioModel]:
        stmt = select(PortfolioModel).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def ensure_default_portfolio(
        self,
        initial_cash: float = 0.0,
    ) -> PortfolioModel:
        """
        Si no existe portfolio, crea uno vacío con el cash inicial.
        Devuelve siempre un PortfolioModel.
        """
        portfolio = await self.get_current_portfolio()
        if portfolio:
            return portfolio

        portfolio = PortfolioModel(
            cash_balance=initial_cash,
            positions={},
        )

        self.session.add(portfolio)
        await self.session.commit()
        await self.session.refresh(portfolio)

        logger.info(
            f"💰 Initial portfolio created with cash={initial_cash:.2f}"
        )
        return portfolio

    # ------------------ NUEVOS MÉTODOS PARA DOMINIO / FAKEBROKER ------------------

    @staticmethod
    def _model_to_dto(model: PortfolioModel) -> PortfolioDTO:
        return PortfolioDTO(
            cash_balance=model.cash_balance,
            positions=model.positions or {},
        )

    async def get_portfolio_dto(
        self,
        initial_cash: float = 0.0,
    ) -> PortfolioDTO:
        """
        Devuelve el portfolio como DTO de dominio.
        Si no existe en DB, crea uno con el cash inicial.
        """
        model = await self.ensure_default_portfolio(initial_cash=initial_cash)
        return self._model_to_dto(model)

    async def save_portfolio_dto(self, dto: PortfolioDTO) -> PortfolioDTO:
        """
        Persiste en DB el estado del portfolio a partir de un PortfolioDTO.
        Devuelve el DTO final (por si algún día hay lógica extra).
        """
        model = await self.ensure_default_portfolio()

        model.cash_balance = dto.cash_balance
        model.positions = dto.positions

        await self.session.commit()
        await self.session.refresh(model)

        return self._model_to_dto(model)

    async def update_cash(self, new_cash: float) -> PortfolioDTO:
        """
        Actualiza solo el cash_balance y devuelve el DTO actualizado.
        """
        model = await self.ensure_default_portfolio()
        model.cash_balance = new_cash

        await self.session.commit()
        await self.session.refresh(model)

        return self._model_to_dto(model)

    async def update_position(self, symbol: str, quantity: float) -> PortfolioDTO:
        """
        Actualiza solo la cantidad de una posición (puede ser 0).
        """
        model = await self.ensure_default_portfolio()
        positions = model.positions or {}

        positions[symbol] = quantity
        model.positions = positions

        await self.session.commit()
        await self.session.refresh(model)

        return self._model_to_dto(model)
