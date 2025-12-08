import pandas as pd
from backtesting.lib import crossover

from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class MACDStrategy(ConfigurableStrategy):

    CONFIG = StrategyParamsDTO(
        strategy_name="MACDStrategy",
        entry_rules=[
            Condition(
                indicator="MACD_12_26_9",
                operator="crossover",
                value="MACDs_12_26_9",
            ),
        ],
        exit_rules=[
            Condition(
                indicator="MACD_12_26_9",
                operator="crossunder",
                value="MACDs_12_26_9",
            ),
        ],
        risk=RiskSettings(
            position_sizing="fixed",
        ),
        metadata={"description": "Simple MACD crossover strategy"},
    )

    def init(self):
        self.macd = self.I(lambda: self.data.MACD_12_26_9, name="MACD")
        self.signal = self.I(
            lambda: self.data.MACDs_12_26_9, name="MACD_Signal")

    def next(self):
        # Entrada
        if not self.position and crossover(self.macd, self.signal):
            self.buy()

        # Salida
        elif self.position and crossover(self.signal, self.macd):
            self.position.close()
