from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd
from pypfopt import EfficientFrontier, risk_models, expected_returns

from src.domain.portfolio.optimizers.base_optimizer import BaseOptimizer
from src.domain.portfolio.risk.constraints import PortfolioConstraints

logger = logging.getLogger(__name__)


class MarkowitzOptimizer(BaseOptimizer):
    """
    Optimizer Markowitz "real" usando pyportfolioopt.

    Input:
      - prices: DataFrame de precios (index = fechas, columns = símbolos)
      - constraints: restricciones suaves del portafolio (MVP)

    Output:
      - dict {symbol: weight} que suma ~1.0

    Decisiones de implementación (MVP):
      - Usamos mean historical return (mu) y sample covariance (S).
      - maximizamos Sharpe ratio long-only.
      - max_weight_per_symbol (si está) se aplica como bound global (0, max_w).
      - blacklist: se ignoran esas columnas de `prices`.
    """

    def __init__(
        self,
        risk_free_rate: float = 0.03,
        weight_cleaning: bool = True,
        min_weight_threshold: float = 1e-4,
    ) -> None:
        self.risk_free_rate = risk_free_rate
        self.weight_cleaning = weight_cleaning
        self.min_weight_threshold = min_weight_threshold

    def optimize(
        self,
        *,
        prices: pd.DataFrame,
        constraints: Optional[PortfolioConstraints] = None,
    ) -> Dict[str, float]:
        logger.info("🧮 Running MarkowitzOptimizer with pyportfolioopt")

        constraints = constraints or PortfolioConstraints()

        # ===== 0) Validaciones básicas =====
        if prices.empty or prices.shape[1] == 0:
            logger.warning("⚠️ MarkowitzOptimizer: Empty prices DataFrame")
            return {}

        prices = prices.copy()

        # ===== 1) Aplicar blacklist (si existe) =====
        if constraints.blacklist:
            before_cols = set(prices.columns)
            prices = prices.drop(
                columns=[c for c in constraints.blacklist if c in prices.columns],
                errors="ignore",
            )
            removed = before_cols - set(prices.columns)
            if removed:
                logger.info(
                    f"🧹 Blacklist applied, symbols removed: {sorted(removed)}")

        if prices.shape[1] == 0:
            logger.warning(
                "⚠️ No symbols left after applying blacklist.")
            return {}

        # ===== 2) Calcular retornos esperados y matriz de covarianza =====
        try:
            mu = expected_returns.mean_historical_return(prices)
            S = risk_models.sample_cov(prices)
            logger.info(f"mu:\n{mu.sort_values(ascending=False)}")
            logger.info(f"diag(S):\n{S.values.diagonal()}")
        except Exception as e:
            logger.error(f"❌ Error calculating mu/S for Markowitz: {e}")
            return {}

        # ===== 3) Construir Efficient Frontier =====
        if constraints.max_weight_per_symbol is not None:
            max_w = float(constraints.max_weight_per_symbol)
            weight_bounds = (0.0, max_w)
        else:
            weight_bounds = (0.0, 1.0)

        ef = EfficientFrontier(mu, S, weight_bounds=weight_bounds)

        try:
            raw_weights = ef.max_sharpe(risk_free_rate=self.risk_free_rate)
            logger.info(f"raw_weights: {raw_weights}")
        except Exception as e:
            logger.error(f"❌ Error en ef.max_sharpe(): {e}")
            return {}

        if self.weight_cleaning:
            weights = ef.clean_weights()
        else:
            weights = raw_weights

        # ===== 4) Normalizar y filtrar pesos muy pequeños =====
        total_weight = sum(max(w, 0.0) for w in weights.values())
        if total_weight <= 0:
            logger.warning(
                "⚠️ MarkowitzOptimizer: total_weight <= 0 after optimization")
            return {}

        normalized: Dict[str, float] = {}
        for symbol, w in weights.items():
            w = max(w, 0.0) / total_weight
            if w < self.min_weight_threshold:
                continue
            normalized[symbol] = float(w)

        logger.info(
            "✅ MarkowitzOptimizer completed. "
            f"{len(normalized)} symbols with weight > {self.min_weight_threshold}"
        )

        return normalized
