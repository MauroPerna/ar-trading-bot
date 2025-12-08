from typing import Dict, Type, List
from src.domain.strategies.impl.base import ConfigurableStrategy
from ..impl import strategies as _strategies_dict

STRATEGY_REGISTRY: Dict[str, Type[ConfigurableStrategy]] = _strategies_dict


def list_strategy_names() -> List[str]:
    return list(STRATEGY_REGISTRY.keys())


def get_strategy_class(name: str) -> Type[ConfigurableStrategy]:
    if name not in STRATEGY_REGISTRY:
        raise KeyError(
            f"Estrategia '{name}' no encontrada en STRATEGY_REGISTRY"
        )
    return STRATEGY_REGISTRY[name]
