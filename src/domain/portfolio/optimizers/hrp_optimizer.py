from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd
from pypfopt.hierarchical_portfolio import HRPOpt

from src.domain.portfolio.optimizers.base_optimizer import BaseOptimizer
from src.domain.portfolio.risk.constraints import PortfolioConstraints

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HRPConfig:
    """
    Configuración para HRP (Hierarchical Risk Parity).

    HRP:
      - Usa retornos históricos para estimar correlaciones/covarianzas y clusterizar.
      - NO invierte Sigma.

    Este wrapper agrega:
      - limpieza de datos
      - blacklist
      - control de max weight (heurístico) + chequeos
      - threshold + renormalización segura
    """
    # Datos
    use_log_returns: bool = True
    min_history_fraction: float = 0.90
    min_rows: int = 60

    # Output
    min_weight_threshold: float = 1e-4
    renormalize_after_threshold: bool = True

    # Bounds / sanity
    max_renormalized_weight_epsilon: float = 1e-9


class HRPOptimizer(BaseOptimizer):
    def __init__(self, config: HRPConfig | None = None) -> None:
        self.config = config or HRPConfig()

    def optimize(
        self,
        *,
        prices: pd.DataFrame,
        constraints: Optional[PortfolioConstraints] = None,
    ) -> Dict[str, float]:
        cfg = self.config
        constraints = constraints or PortfolioConstraints()

        logger.info("🌳 Running HRPOptimizer (robust)")

        if prices is None or prices.empty or prices.shape[1] == 0:
            logger.warning("⚠️ HRPOptimizer: Empty prices DataFrame")
            return {}

        prices = prices.copy().sort_index()

        # ===== 1) Blacklist =====
        if getattr(constraints, "blacklist", None):
            before = set(prices.columns)
            prices = prices.drop(
                columns=[c for c in constraints.blacklist if c in prices.columns], errors="ignore")
            removed = sorted(before - set(prices.columns))
            if removed:
                logger.info("🧹 Blacklist applied. Removed: %s", removed)

        if prices.shape[1] < 2:
            logger.warning(
                "⚠️ HRPOptimizer: need at least 2 assets after blacklist")
            return {}

        # ===== 2) Filtro por historial =====
        non_na_frac = prices.notna().mean(axis=0)
        keep_cols = non_na_frac[non_na_frac >=
                                cfg.min_history_fraction].index.tolist()
        dropped = sorted(set(prices.columns) - set(keep_cols))
        if dropped:
            logger.info(
                "🧹 Dropping assets due to insufficient history (< %.0f%% non-NaN): %s",
                cfg.min_history_fraction * 100,
                dropped,
            )
        prices = prices[keep_cols]

        if prices.shape[1] < 2:
            logger.warning(
                "⚠️ HRPOptimizer: not enough assets after history filter")
            return {}

        prices = prices.dropna(axis=0, how="any")

        # ===== 3) Retornos =====
        if cfg.use_log_returns:
            returns = np.log(prices / prices.shift(1)).dropna()
        else:
            returns = prices.pct_change().dropna()

        if returns.shape[0] < cfg.min_rows:
            logger.warning(
                "⚠️ HRPOptimizer: not enough return rows: %d", returns.shape[0])
            return {}

        # ===== 4) HRP =====
        try:
            hrp = HRPOpt(returns)
            raw = hrp.optimize()
            weights = hrp.clean_weights()
        except Exception as e:
            logger.exception(
                "❌ HRPOptimizer: error in HRPOpt.optimize(): %s", e)
            return {}

        w = pd.Series({k: float(max(v, 0.0)) for k, v in weights.items()})
        if w.empty or float(w.sum()) <= 0:
            return {}

        # ===== 5) Max weight (heurístico) =====
        max_w = float(
            getattr(constraints, "max_weight_per_symbol", 1.0) or 1.0)
        if max_w <= 0:
            logger.warning("⚠️ max_weight_per_symbol <= 0. Returning empty.")
            return {}

        w_capped = w.clip(lower=0.0, upper=max_w)

        s = float(w_capped.sum())
        if s <= 0:
            logger.warning("⚠️ HRPOptimizer: all weights capped to zero")
            return {}
        w_capped = w_capped / s

        if float(w_capped.max()) > max_w + cfg.max_renormalized_weight_epsilon:
            logger.warning(
                "⚠️ HRPOptimizer: max weight exceeded after renormalization.")

        # ===== 6) Threshold + renormalización =====
        if cfg.min_weight_threshold > 0:
            w_capped = w_capped[w_capped >= cfg.min_weight_threshold]

        if w_capped.empty or float(w_capped.sum()) <= 0:
            return {}

        if cfg.renormalize_after_threshold:
            w_capped = w_capped / float(w_capped.sum())

        result = {str(sym): float(val)
                  for sym, val in w_capped.sort_values(ascending=False).items()}
        logger.info("✅ HRPOptimizer completed. n=%d, sum=%.6f, max=%.6f", len(
            result), sum(result.values()), max(result.values()))
        return result
