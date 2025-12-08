from backtesting import Strategy
from typing import ClassVar
from src.domain.strategies.dtos.config_dto import StrategyParamsDTO


class ConfigurableStrategy(Strategy):
    CONFIG: ClassVar[StrategyParamsDTO]

    @classmethod
    def get_config(cls) -> StrategyParamsDTO:
        return cls.CONFIG

    @property
    def params(self):
        raw = getattr(self, '_params', None)
        if raw is None:
            return {}
        try:
            return dict(raw)
        except Exception:
            return {}
