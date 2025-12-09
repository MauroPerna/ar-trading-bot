import logging
from typing import Optional, Dict, List
from datetime import datetime, date, timedelta
import math

import numpy as np
import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.portfolio_weights_model import (
    PortfolioWeightsModel,
)

logger = logging.getLogger(__name__)


class PortfolioWeightsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==========================
    #        QUERIES
    # ==========================

    async def get_active_weight(
        self,
        *,
        symbol: str,
        timeframe: str = "1d",
        optimizer_name: Optional[str] = None,
    ) -> Optional[PortfolioWeightsModel]:
        """
        Devuelve el peso activo para un símbolo / timeframe / (optimizer).
        """
        stmt = select(PortfolioWeightsModel).where(
            PortfolioWeightsModel.symbol == symbol,
            PortfolioWeightsModel.timeframe == timeframe,
            PortfolioWeightsModel.is_active.is_(True),
        )

        if optimizer_name:
            stmt = stmt.where(
                PortfolioWeightsModel.optimizer_name == optimizer_name
            )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_weights(
        self,
        *,
        timeframe: str = "1d",
        optimizer_name: Optional[str] = None,
    ) -> List[PortfolioWeightsModel]:
        """
        Devuelve todos los pesos activos para un timeframe dado
        (opcionalmente filtrado por optimizer).
        """
        stmt = select(PortfolioWeightsModel).where(
            PortfolioWeightsModel.timeframe == timeframe,
            PortfolioWeightsModel.is_active.is_(True),
        )

        if optimizer_name:
            stmt = stmt.where(
                PortfolioWeightsModel.optimizer_name == optimizer_name
            )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ==========================
    #        COMMANDS
    # ==========================

    async def deactivate_all(
        self,
        *,
        timeframe: str = "1d",
        optimizer_name: Optional[str] = None,
    ) -> None:
        """
        Marca como inactivos todos los pesos activos para un timeframe
        (y opcionalmente para un optimizer).
        El commit se hace en el bulk_upsert.
        """
        stmt = update(PortfolioWeightsModel).where(
            PortfolioWeightsModel.timeframe == timeframe,
            PortfolioWeightsModel.is_active.is_(True),
        )

        if optimizer_name:
            stmt = stmt.where(
                PortfolioWeightsModel.optimizer_name == optimizer_name
            )

        stmt = stmt.values(is_active=False)
        await self.session.execute(stmt)

    async def bulk_upsert_weights(
        self,
        *,
        timeframe: str,
        optimizer_name: str,
        weights: Dict[str, float],              # {symbol: weight}
        rebalance_date: Optional[datetime] = None,
        meta_per_symbol: Optional[Dict[str, dict]] = None,
    ) -> List[PortfolioWeightsModel]:
        """
        Persiste un set de pesos óptimos para un (timeframe, optimizer):

        - Desactiva los pesos previos para ese timeframe/optimizer.
        - Inserta una fila por símbolo con weight + meta.
        - Marca todos como is_active=True.

        `weights` son pesos target (0–1) por símbolo.
        `meta_per_symbol` opcionalmente puede tener info extra por símbolo.
        """
        if rebalance_date is None:
            rebalance_date = datetime.now()

        meta_per_symbol = meta_per_symbol or {}

        # Desactivar cualquier set anterior
        await self.deactivate_all(
            timeframe=timeframe,
            optimizer_name=optimizer_name,
        )

        models: List[PortfolioWeightsModel] = []

        for symbol, weight in weights.items():
            meta_raw = meta_per_symbol.get(symbol, {})
            meta_json = self._to_jsonable(meta_raw)

            model = PortfolioWeightsModel(
                symbol=symbol,
                timeframe=timeframe,
                weight=float(weight),
                optimizer_name=optimizer_name,
                rebalance_date=rebalance_date,
                is_active=True,
                meta=meta_json,
            )
            self.session.add(model)
            models.append(model)

        await self.session.commit()

        # refrescamos para tener IDs, timestamps, etc.
        for m in models:
            await self.session.refresh(m)

        logger.info(
            f"💾 Saved {len(models)} active portfolio_weights "
            f"for timeframe={timeframe}, optimizer={optimizer_name}, "
            f"rebalance_date={rebalance_date.isoformat()}"
        )

        return models

    # ==========================
    #   JSON NORMALIZATION
    # ==========================

    def _to_jsonable(self, obj):
        """
        Convierte cualquier cosa a algo JSON-serializable.

        Maneja:
        - pandas.Timestamp / datetime / date
        - pandas.Timedelta / datetime.timedelta
        - numpy.* (int, float, bool)
        - float NaN / inf / -inf  → None
        - dict / list / tuple / set
        - Series / DataFrame (por si se escapa algo)
        """
        # pandas / datetime
        if isinstance(obj, (pd.Timestamp, datetime, date)):
            return obj.isoformat()
        if isinstance(obj, (pd.Timedelta, timedelta)):
            return obj.total_seconds()

        # numpy + float: controlar NaN / inf
        if isinstance(obj, (np.floating, float)):
            val = float(obj)
            if math.isnan(val) or math.isinf(val):
                return None
            return val

        # numpy integer / bool
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)

        # pandas Series / DataFrame (defensivo)
        if isinstance(obj, pd.Series):
            return obj.apply(self._to_jsonable).to_dict()
        if isinstance(obj, pd.DataFrame):
            return {col: self._to_jsonable(obj[col].tolist())
                    for col in obj.columns}

        # contenedores
        if isinstance(obj, dict):
            return {str(k): self._to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._to_jsonable(v) for v in obj]

        # tipos básicos (str, int, bool, None, etc.)
        return obj
