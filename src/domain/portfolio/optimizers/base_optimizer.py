# src/domain/portfolio/optimizers/base_optimizer.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional

import pandas as pd

from src.domain.portfolio.risk.constraints import PortfolioConstraints


class BaseOptimizer(ABC):
    """
    Interfaz base para cualquier optimizer de portafolio.

    Recibe data histórica (prices/returns) y restricciones,
    devuelve pesos objetivo por símbolo.
    """

    @abstractmethod
    def optimize(
        self,
        *,
        prices: pd.DataFrame,
        constraints: Optional[PortfolioConstraints] = None,
    ) -> Dict[str, float]:
        """
        Dado un DataFrame de precios (index = fechas, columns = símbolos),
        devuelve un dict {symbol: target_weight} que suma ~1.0.

        El tratamiento de constraints queda a cargo de cada implementación
        (o de una capa superior que valide y ajuste).
        """
        raise NotImplementedError
