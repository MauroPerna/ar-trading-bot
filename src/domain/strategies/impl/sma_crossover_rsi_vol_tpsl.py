from backtesting.lib import crossover
from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class SMACrossoverRSIVolWithTPSLStrategy(ConfigurableStrategy):
    """
    Cruce SMA + RSI + volumen con gestión TP/SL fija.
    """

    CONFIG = StrategyParamsDTO(
        strategy_name="SMACrossoverRSIVolWithTPSLStrategy",
        entry_rules=[
            Condition(
                indicator="SMA_5",
                operator="crossover",
                value="SMA_8"
            ),
            Condition(
                indicator="RSI_14",
                operator="<",
                value=60
            ),
            Condition(
                indicator="Volume",
                operator=">",
                value="SMA_20_VOL",
            ),
        ],
        exit_rules=[
            Condition(
                indicator="SMA_8",
                operator="crossover",
                value="SMA_5",
            ),
            Condition(
                indicator="RSI_14",
                operator=">",
                value=70,
            ),
        ],
        risk=RiskSettings(
            stop_loss_pct=0.02,   # 2% SL por defecto
            take_profit_pct=0.04,  # 4% TP por defecto
            position_sizing="fixed",
        ),
        metadata={
            "description": "SMA 5/8 + RSI + volumen + TP/SL"
        },
    )

    def init(self):
        # Indicators mapped exactly as used in CONFIG
        self.volume = self.I(lambda: self.data.Volume)
        self.avg_volume = self.I(
            lambda: self.data.SMA_20_VOL, name="SMA_20_VOL")
        self.rsi = self.I(lambda: self.data.RSI_14, name="RSI_14")
        self.sma_5 = self.I(lambda: self.data.SMA_5, name="SMA_5")
        self.sma_8 = self.I(lambda: self.data.SMA_8, name="SMA_8")

        # Load configurable risk settings
        self.tp_pct = self.params.get(
            "take_profit_pct", self.CONFIG.risk.take_profit_pct)
        self.sl_pct = self.params.get(
            "stop_loss_pct", self.CONFIG.risk.stop_loss_pct)

    def next(self):
        price = self.data.Close[-1]

        # ENTRY
        if (
            not self.position
            and crossover(self.sma_5, self.sma_8)
            and self.rsi[-1] < 60
            and self.volume[-1] > self.avg_volume[-1]
        ):
            stop_loss = price * (1 - self.sl_pct)
            take_profit = price * (1 + self.tp_pct)

            self.buy(sl=stop_loss, tp=take_profit)

        # EXIT
        elif self.position and (
            crossover(self.sma_8, self.sma_5) or self.rsi[-1] > 70
        ):
            self.position.close()
