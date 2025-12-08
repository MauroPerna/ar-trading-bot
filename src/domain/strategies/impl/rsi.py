from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class RSIStrategy(ConfigurableStrategy):
    """
    Estrategia basada en RSI: 
    Buy cuando RSI < 30 (oversold)
    Sell cuando RSI > 70 (overbought)
    """

    CONFIG = StrategyParamsDTO(
        strategy_name="RSIStrategy",
        entry_rules=[
            Condition(indicator="RSI_14", operator="<", value=30),
        ],
        exit_rules=[
            Condition(indicator="RSI_14", operator=">", value=70),
        ],
        risk=RiskSettings(
            stop_loss_pct=None,
            take_profit_pct=None,
            position_sizing="fixed",
        ),
        metadata={
            "description": "Estrategia simple basada en RSI clásico (30/70)"},
    )

    def init(self):
        self.rsi = self.I(lambda: self.data.RSI_14, name="RSI_14")

    def next(self):
        if not self.position and self.rsi[-1] < 30:
            self.buy()
        elif self.position and self.rsi[-1] > 70:
            self.position.close()
