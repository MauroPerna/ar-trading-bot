# src/domain/portfolio/optimizers/hrp_optimizer.py
from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd
from pypfopt.hierarchical_portfolio import HRPOpt

from src.domain.portfolio.optimizers.base_optimizer import BaseOptimizer
from src.domain.portfolio.risk.constraints import PortfolioConstraints

logger = logging.getLogger(__name__)


class HRPOptimizer(BaseOptimizer):
    """
    HRP (Hierarchical Risk Parity) basado en PyPortfolioOpt.

    MVP:
      - Usa retornos históricos.
      - Aplica blacklist de constraints.
      - Aplica max_weight_per_symbol como clip post-optimización.
      - Long-only, pesos normalizados que suman 1.
    """

    def __init__(self, min_weight_threshold: float = 1e-4) -> None:
        self.min_weight_threshold = min_weight_threshold

    def optimize(
        self,
        *,
        prices: pd.DataFrame,
        constraints: Optional[PortfolioConstraints] = None,
    ) -> Dict[str, float]:
        logger.info("🌳 Running HRPOptimizer (PyPortfolioOpt HRP)")

        constraints = constraints or PortfolioConstraints()

        if prices.empty or prices.shape[1] == 0:
            logger.warning("⚠️ HRPOptimizer: Empty prices DataFrame")
            return {}

        prices = prices.copy()

        # ===== 1) Aplicar blacklist =====
        if constraints.blacklist:
            before_cols = set(prices.columns)
            prices = prices.drop(
                columns=[c for c in constraints.blacklist if c in prices.columns],
                errors="ignore",
            )
            removed = before_cols - set(prices.columns)
            if removed:
                logger.info(
                    f"🧹 HRPOptimizer: blacklist applied, symbols removed: {sorted(removed)}"
                )

        if prices.shape[1] == 0:
            logger.warning(
                "⚠️ HRPOptimizer: no symbols left after blacklist"
            )
            return {}

        # ===== 2) Retornos históricos =====
        returns = prices.pct_change().dropna()
        if returns.empty:
            logger.warning(
                "⚠️ HRPOptimizer: could not calculate returns (too many NaN or few rows)"
            )
            return {}

        # ===== 3) HRPOpt =====
        try:
            hrp = HRPOpt(returns)
            raw_weights = hrp.optimize()
            weights = hrp.clean_weights()
            logger.info(f"HRPOptimizer raw_weights: {raw_weights}")
        except Exception as e:
            logger.error(f"❌ Error en HRPOptimizer (HRPOpt.optimize): {e}")
            return {}

        # ===== 4) Aplicar max_weight_per_symbol y normalizar =====
        if constraints.max_weight_per_symbol is not None:
            max_w = float(constraints.max_weight_per_symbol)
        else:
            max_w = 1.0

        clipped: Dict[str, float] = {}
        for symbol, w in weights.items():
            w = max(w, 0.0)          # long-only
            w = min(w, max_w)        # cap por símbolo
            clipped[symbol] = float(w)

        total = sum(clipped.values())
        if total <= 0:
            logger.warning(
                "⚠️ HRPOptimizer: total_weight <= 0 after clipping"
            )
            return {}

        normalized: Dict[str, float] = {}
        for symbol, w in clipped.items():
            w_norm = w / total
            if w_norm < self.min_weight_threshold:
                continue
            normalized[symbol] = float(w_norm)

        logger.info(
            "✅ HRPOptimizer completed. "
            f"{len(normalized)} symbols with weight > {self.min_weight_threshold}"
        )
        logger.info(f"Final HRP weights: {normalized}")

        return normalized
