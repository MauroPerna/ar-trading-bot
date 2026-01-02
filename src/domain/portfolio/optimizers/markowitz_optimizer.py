from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, expected_returns, risk_models

from src.domain.portfolio.optimizers.base_optimizer import BaseOptimizer
from src.domain.portfolio.risk.constraints import PortfolioConstraints

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarkowitzConfig:
    """
    Configuración para la optimización tipo Markowitz (Mean-Variance / Tangency portfolio).

    Notas importantes sobre UNIDADES:
      - expected_returns.mean_historical_return() anualiza por defecto si frequency=252.
      - risk_free_rate debe estar en la MISMA unidad temporal que mu (típicamente anual).
    """
    risk_free_rate_annual: float = 0.03
    frequency: int = 252  # 252 (daily), 52 (weekly), 12 (monthly)

    # Limpieza y calidad de datos
    min_history_fraction: float = 0.90
    drop_assets_with_any_nan_after_align: bool = True

    # Estimación de riesgo (Sigma)
    use_shrinkage: bool = True
    shrinkage_method: str = "ledoit_wolf"

    # Output / postprocesado
    weight_cleaning: bool = True
    min_weight_threshold: float = 1e-4
    renormalize_after_threshold: bool = True

    # Sanity checks
    max_renormalized_weight_epsilon: float = 1e-9


class MarkowitzOptimizer(BaseOptimizer):
    """
    MarkowitzOptimizer (pyportfolioopt) orientado a producción.

    Qué resuelve:
      - Portafolio tangente (máximo Sharpe): max_sharpe(rf) con restricciones long-only y bounds.
      - Modelo clásico de Markowitz + activo libre de riesgo (vía Sharpe).

    Decisiones explícitas:
      - mu: mean historical return anualizado (frequency configurable)
      - Sigma: shrinkage (Ledoit-Wolf) por defecto para estabilidad
      - Constraints: box constraints (0, max_w) + blacklist
      - Post-procesado: clean_weights opcional + threshold + renormalización opcional
    """

    def __init__(self, config: MarkowitzConfig | None = None) -> None:
        self.config = config or MarkowitzConfig()

    def optimize(
        self,
        *,
        prices: pd.DataFrame,
        constraints: Optional[PortfolioConstraints] = None,
    ) -> Dict[str, float]:
        cfg = self.config
        constraints = constraints or PortfolioConstraints()

        logger.info("🧮 Running MarkowitzOptimizer (robust)")

        # ===== 0) Validaciones =====
        if prices is None or prices.empty or prices.shape[1] == 0:
            logger.warning("⚠️ Empty prices DataFrame")
            return {}

        prices = prices.copy()
        prices = prices.sort_index()

        # ===== 1) Blacklist =====
        if getattr(constraints, "blacklist", None):
            before = set(prices.columns)
            prices = prices.drop(
                columns=[c for c in constraints.blacklist if c in prices.columns], errors="ignore")
            removed = sorted(before - set(prices.columns))
            if removed:
                logger.info("🧹 Blacklist applied. Removed: %s", removed)

        if prices.shape[1] == 0:
            logger.warning("⚠️ No symbols left after blacklist")
            return {}

        # ===== 2) Limpieza de datos / calidad de historial =====
        non_na_frac = prices.notna().mean(axis=0)
        keep_cols = non_na_frac[non_na_frac >=
                                cfg.min_history_fraction].index.tolist()
        dropped_for_history = sorted(set(prices.columns) - set(keep_cols))
        if dropped_for_history:
            logger.info(
                "🧹 Dropping assets due to insufficient history (< %.0f%% non-NaN): %s",
                cfg.min_history_fraction * 100,
                dropped_for_history,
            )
        prices = prices[keep_cols]

        if prices.shape[1] == 0:
            logger.warning("⚠️ No symbols left after history filter")
            return {}

        if cfg.drop_assets_with_any_nan_after_align:
            cols_with_nan = prices.columns[prices.isna().any(axis=0)].tolist()
            if cols_with_nan:
                logger.info(
                    "🧹 Dropping assets with remaining NaNs after align: %s", sorted(cols_with_nan))
                prices = prices.drop(columns=cols_with_nan)

        prices = prices.dropna(axis=0, how="any")

        if prices.shape[0] < max(30, cfg.frequency // 10):
            logger.warning(
                "⚠️ Not enough rows after cleaning: %s", prices.shape[0])
            return {}

        if prices.shape[1] < 2:
            logger.warning(
                "⚠️ Not enough assets after cleaning: %s", prices.shape[1])
            return {}

        # ===== 3) Estimación de mu y Sigma =====
        try:
            mu = expected_returns.mean_historical_return(
                prices, frequency=cfg.frequency)
        except Exception as e:
            logger.exception("❌ Error computing expected returns (mu): %s", e)
            return {}

        try:
            if cfg.use_shrinkage:
                cs = risk_models.CovarianceShrinkage(
                    prices, frequency=cfg.frequency)
                if cfg.shrinkage_method == "ledoit_wolf":
                    S = cs.ledoit_wolf()
                elif cfg.shrinkage_method == "oracle_approximating":
                    S = cs.oracle_approximating()
                else:
                    raise ValueError(
                        f"Unsupported shrinkage_method: {cfg.shrinkage_method}")
            else:
                S = risk_models.sample_cov(prices, frequency=cfg.frequency)
        except Exception as e:
            logger.exception(
                "❌ Error computing covariance matrix (Sigma): %s", e)
            return {}

        logger.info(
            "📈 mu stats (annual): min=%.4f mean=%.4f max=%.4f | n_assets=%d",
            float(mu.min()),
            float(mu.mean()),
            float(mu.max()),
            int(mu.shape[0]),
        )
        logger.info(
            "📉 Sigma diag stats: min=%.6f mean=%.6f max=%.6f",
            float(np.min(np.diag(S.values))),
            float(np.mean(np.diag(S.values))),
            float(np.max(np.diag(S.values))),
        )

        # ===== 4) Bounds / Constraints =====
        if getattr(constraints, "max_weight_per_symbol", None) is not None:
            max_w = float(constraints.max_weight_per_symbol)
            if max_w <= 0:
                logger.warning(
                    "⚠️ max_weight_per_symbol <= 0. Returning empty.")
                return {}
            weight_bounds: Tuple[float, float] = (0.0, max_w)
        else:
            max_w = 1.0
            weight_bounds = (0.0, 1.0)

        ef = EfficientFrontier(mu, S, weight_bounds=weight_bounds)

        # ===== 5) Optimización: portafolio tangente (máximo Sharpe) =====
        try:
            raw_weights = ef.max_sharpe(
                risk_free_rate=cfg.risk_free_rate_annual)
        except Exception as e:
            logger.exception("❌ Error in ef.max_sharpe(): %s", e)
            return {}

        weights = ef.clean_weights() if cfg.weight_cleaning else raw_weights

        # ===== 6) Post-procesado: threshold + renormalización controlada =====
        w_series = pd.Series({k: float(max(v, 0.0))
                             for k, v in weights.items()})

        if cfg.min_weight_threshold > 0:
            w_series = w_series[w_series >= cfg.min_weight_threshold]

        if w_series.empty or float(w_series.sum()) <= 0:
            logger.warning("⚠️ No positive weights left after thresholding.")
            return {}

        if cfg.renormalize_after_threshold:
            w_series = w_series / float(w_series.sum())

            if float(w_series.max()) > max_w + cfg.max_renormalized_weight_epsilon:
                logger.warning(
                    "⚠️ Renormalization pushed a weight above max_w (%.4f). "
                    "Consider: lower threshold, add regularization, or re-optimize with fewer assets. "
                    "max_weight=%.6f, max_w=%.6f",
                    float(w_series.max() - max_w),
                    float(w_series.max()),
                    float(max_w),
                )
                w_series = w_series.clip(lower=0.0, upper=max_w)
                s = float(w_series.sum())
                if s <= 0:
                    return {}
                w_series = w_series / s

        # ===== 7) Output =====
        result = {str(sym): float(w)
                  for sym, w in w_series.sort_values(ascending=False).items()}

        logger.info(
            "✅ MarkowitzOptimizer completed. n=%d, sum=%.6f, max=%.6f",
            len(result),
            sum(result.values()),
            max(result.values()),
        )
        return result
