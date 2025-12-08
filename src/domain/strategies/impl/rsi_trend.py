import numpy as np
from backtesting import Strategy
from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class RSIWithTrendSignalStrategy(ConfigurableStrategy):

    CONFIG = StrategyParamsDTO(
        strategy_name="RSIWithTrendSignalStrategy",
        entry_rules=[
            Condition(indicator="trend_signal", operator="==", value=1),
            Condition(indicator="RSI_14", operator="<", value=60),
        ],
        exit_rules=[
            Condition(indicator="RSI_14", operator=">", value=70),
            Condition(indicator="trend_signal", operator="!=", value=1),
        ],
        risk=RiskSettings(
            cooldown_period=10,
            position_sizing="fixed",
        ),
        metadata={
            "description": "RSI con filtro de tendencia y cooldown entre operaciones"
        },
    )

    def init(self):
        self.rsi = self.I(lambda: self.data.RSI_14, name="RSI_14")
        self.trend_signal = self.I(
            lambda: self.data.trend_signal, name="Trend")
        self.last_exit_index = -np.inf

    def next(self):
        i = len(self.data) - 1
        cooldown = getattr(self.CONFIG.risk, "cooldown_period", 0)

        # Entrada
        if (
            not self.position
            and (i - self.last_exit_index) > cooldown
            and self.trend_signal[-1] == 1
            and self.rsi[-1] < 60
        ):
            self.buy()

        # Salida
        elif self.position and (
            self.rsi[-1] > 70 or self.trend_signal[-1] != 1
        ):
            self.position.close()
            self.last_exit_index = i
