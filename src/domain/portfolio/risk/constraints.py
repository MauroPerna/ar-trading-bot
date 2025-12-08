from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PositionLimit(BaseModel):
    """Restricciones por símbolo."""
    max_weight: Optional[float] = None        # peso máx (0–1)
    max_notional: Optional[float] = None      # no lo usamos acá
    max_quantity: Optional[float] = None      # no lo usamos acá


class PortfolioConstraints(BaseModel):
    """
    Conjunto de restricciones de riesgo / exposición del portafolio.
    Esto se lo pasamos al sizing / optimizer.
    """
    max_gross_exposure: Optional[float] = None
    max_leverage: Optional[float] = None
    max_positions: Optional[int] = None
    max_weight_per_symbol: Optional[float] = None

    per_symbol: Dict[str, PositionLimit] = Field(default_factory=dict)
    blacklist: List[str] = Field(default_factory=list)


def validate_weights(
    weights: Dict[str, float],
    constraints: PortfolioConstraints,
) -> Dict[str, float]:
    """
    Recibe un dict {symbol: weight} y devuelve otro dict con los pesos
    recortados según constraints.

    - Clampeamos a [0, 1]
    - Respetamos:
        - blacklist
        - max_weight_per_symbol global
        - per_symbol.max_weight
    """
    validated: Dict[str, float] = {}

    # Max positions (opcional, si querés limitar cantidad de símbolos)
    if constraints.max_positions is not None and len(weights) > constraints.max_positions:
        pass

    for symbol, w in weights.items():
        # blacklisted → lo descartamos
        if symbol in constraints.blacklist:
            continue

        w_clipped = max(0.0, float(w))  # nada negativo

        # límite global por símbolo
        if constraints.max_weight_per_symbol is not None:
            w_clipped = min(w_clipped, float(
                constraints.max_weight_per_symbol))

        # límite específico por símbolo
        per_sym = constraints.per_symbol.get(symbol)
        if per_sym and per_sym.max_weight is not None:
            w_clipped = min(w_clipped, float(per_sym.max_weight))

        if w_clipped > 0:
            validated[symbol] = w_clipped

    return validated
