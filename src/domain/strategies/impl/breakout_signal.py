import pandas as pd
from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import StrategyParamsDTO, Condition, RiskSettings


class BreakoutSignalStrategy(ConfigurableStrategy):
    """
    Estrategia de quiebre alcista con confirmación de momentum (MACD)
    """

    CONFIG = StrategyParamsDTO(
        strategy_name="BreakoutSignalStrategy",
        entry_rules=[
            Condition(indicator="trend_signal", operator="==", value=1),
            Condition(indicator="MACD_12_26_9",
                      operator=">", value="MACDs_12_26_9"),
            Condition(indicator="Close", operator=">",
                      value="main_resistance"),
        ],
        exit_rules=[
            Condition(indicator="trend_signal", operator="==", value=-1),
            Condition(indicator="MACD_12_26_9",
                      operator="<", value="MACDs_12_26_9"),
        ],
        risk=RiskSettings(
            stop_loss_pct=None,
            take_profit_pct=None,
            position_sizing="fixed",
        ),
        metadata={"description": "Breakout con MACD y trend_signal"},
    )

    def init(self):
        self.close = self.I(lambda: self.data.Close)
        self.macd = self.I(lambda: self.data.MACD_12_26_9, name="MACD")
        self.macd_signal = self.I(
            lambda: self.data.MACDs_12_26_9, name="MACD_signal"
        )
        self.trend_signal = self.I(
            lambda: self.data.trend_signal, name="TrendSignal"
        )
        self.main_resistance = self.I(
            lambda: self.data.main_resistance, name="MainResistance"
        )

    def next(self):
        if pd.isna(self.main_resistance[-1]):
            return

        if not self.position:
            if (
                self.trend_signal[-1] == 1
                and self.macd[-1] > self.macd_signal[-1]
                and self.close[-1] > self.main_resistance[-1]
            ):
                self.buy()
        elif (
            self.trend_signal[-1] == -1
            or self.macd[-1] < self.macd_signal[-1]
        ):
            self.position.close()
