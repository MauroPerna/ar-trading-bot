import logging
from typing import Optional, Union
from datetime import datetime, date, timedelta
import math

import numpy as np
import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.strategies.dtos.config_dto import (
    StrategyConfigDTO,
    StrategyParamsDTO,
)
from src.infrastructure.database.models.symbol_strategy_model import (
    SymbolStrategyModel,
)

logger = logging.getLogger(__name__)


class SymbolStrategyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==========================
    #        QUERIES
    # ==========================

    async def get_active_strategy(
        self,
        symbol: str,
        timeframe: str = "1d",
    ) -> Optional[SymbolStrategyModel]:
        """
        Devuelve la fila activa cruda (modelo SQLAlchemy).
        """
        stmt = (
            select(SymbolStrategyModel)
            .where(
                SymbolStrategyModel.symbol == symbol,
                SymbolStrategyModel.timeframe == timeframe,
                SymbolStrategyModel.is_active.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_strategy_config(
        self,
        symbol: str,
        timeframe: str = "1d",
    ) -> Optional[StrategyConfigDTO]:
        """
        Devuelve la estrategia activa ya mapeada a un DTO tipado.
        """
        model = await self.get_active_strategy(symbol, timeframe)
        if not model:
            return None

        params_dict = model.params or {}
        params_dto = StrategyParamsDTO.model_validate(params_dict)

        return StrategyConfigDTO(
            id=model.id,
            symbol=model.symbol,
            timeframe=model.timeframe,
            strategy_name=model.strategy_name,
            params=params_dto,
            sharpe_ratio=model.sharpe_ratio,
            max_drawdown_pct=model.max_drawdown_pct,
            return_pct=model.return_pct,
        )

    async def get_all_active_strategies(
        self,
        timeframe: str = "1d",
    ) -> list[StrategyConfigDTO]:
        """
        Devuelve todas las estrategias activas para un timeframe dado.
        """
        stmt = (
            select(SymbolStrategyModel)
            .where(
                SymbolStrategyModel.timeframe == timeframe,
                SymbolStrategyModel.is_active.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()

        configs = []
        for model in models:
            params_dict = model.params or {}
            params_dto = StrategyParamsDTO.model_validate(params_dict)

            config = StrategyConfigDTO(
                id=model.id,
                symbol=model.symbol,
                timeframe=model.timeframe,
                strategy_name=model.strategy_name,
                params=params_dto,
                sharpe_ratio=model.sharpe_ratio,
                max_drawdown_pct=model.max_drawdown_pct,
                return_pct=model.return_pct,
            )
            configs.append(config)

        return configs

    # ==========================
    #        COMMANDS
    # ==========================

    async def deactivate_all_for_symbol(
        self,
        symbol: str,
        timeframe: str = "1d",
    ) -> None:
        """
        Marca como inactivas todas las estrategias activas para (symbol, timeframe).
        El commit se hace en upsert_best_strategy.
        """
        stmt = (
            update(SymbolStrategyModel)
            .where(
                SymbolStrategyModel.symbol == symbol,
                SymbolStrategyModel.timeframe == timeframe,
                SymbolStrategyModel.is_active.is_(True),
            )
            .values(is_active=False)
        )
        await self.session.execute(stmt)

    async def upsert_best_strategy(
        self,
        *,
        symbol: str,
        timeframe: str,
        strategy_name: str,
        params: Union[StrategyParamsDTO, dict, None],
        metrics: dict,
    ) -> SymbolStrategyModel:
        """
        Persiste la mejor estrategia para un (symbol, timeframe):
        - desactiva las anteriores
        - guarda params (config) y metrics (raw_stats) en JSON
        - guarda columnas agregadas (Sharpe, DD, Return)
        """
        # Desactivar anteriores
        await self.deactivate_all_for_symbol(symbol, timeframe)

        # Métricas agregadas que usamos en columnas dedicadas
        sharpe = float(metrics.get("Sharpe Ratio", 0) or 0)
        max_dd = float(metrics.get("Max. Drawdown [%]", 0) or 0)
        ret_pct = float(metrics.get("Return [%]", 0) or 0)

        # Podar cosas pesadas / no serializables que vienen de backtesting.py
        metrics_clean = {
            k: v
            for k, v in metrics.items()
            if k not in ("_equity_curve", "_trades", "_strategy")
        }

        # params puede venir como dict o como StrategyParamsDTO
        if hasattr(params, "model_dump"):  # Pydantic model
            params_dict = params.model_dump()
        else:
            params_dict = params or {}

        # Asegurar que params y metrics sean JSON-serializables
        params_json = self._to_jsonable(params_dict)
        metrics_json = self._to_jsonable(metrics_clean)

        model = SymbolStrategyModel(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            params=params_json,
            metrics=metrics_json,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            return_pct=ret_pct,
            is_active=True,
        )

        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)

        logger.info(
            f"💾 Saved best strategy for {symbol}/{timeframe}: "
            f"{strategy_name} (Sharpe={sharpe:.2f}, Ret={ret_pct:.2f}%, DD={max_dd:.2f}%)"
        )

        return model

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
                # Postgres JSON no acepta NaN/Inf → lo mapeamos a null
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

        # tipos básicos (str, int, bool, None, etc)
        return obj
