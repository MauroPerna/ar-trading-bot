from backtesting.lib import crossover
from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class SMACrossoverStrategy(ConfigurableStrategy):
    """
    Estrategia simple basada en cruce de medias móviles (SMA 5 y SMA 8).
    """

    CONFIG = StrategyParamsDTO(
        strategy_name="SMACrossoverStrategy",
        entry_rules=[
            Condition(
                indicator="SMA_5",
                operator="crossover",
                value="SMA_8"
            ),
        ],
        exit_rules=[
            Condition(
                indicator="SMA_8",
                operator="crossover",
                value="SMA_5"
            ),
        ],
        risk=RiskSettings(
            stop_loss_pct=None,
            take_profit_pct=None,
            position_sizing="fixed"
        ),
        metadata={"description": "Cruce de medias móviles SMA_5 / SMA_8"},
    )

    def init(self):
        self.sma_5 = self.I(lambda: self.data.SMA_5, name="SMA_5")
        self.sma_8 = self.I(lambda: self.data.SMA_8, name="SMA_8")

    def next(self):
        # ENTRY
        if not self.position and crossover(self.sma_5, self.sma_8):
            self.buy()

        # EXIT
        elif self.position and crossover(self.sma_8, self.sma_5):
            self.position.close()
