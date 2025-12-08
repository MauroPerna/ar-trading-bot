from backtesting.lib import crossover
from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class SMACrossoverWithRSIAndAvgVolStrategy(ConfigurableStrategy):
    """
    Estrategia de cruce de medias (SMA) con RSI y volumen promedio.

    Compra cuando:
      - SMA_5 cruza por encima de SMA_8
      - RSI < 60
      - Volumen > volumen promedio

    Cierra cuando:
      - SMA_8 cruza por encima de SMA_5
      - RSI > 70
    """

    CONFIG = StrategyParamsDTO(
        strategy_name="SMACrossoverWithRSIAndAvgVolStrategy",
        entry_rules=[
            # SMA_5 cruza por encima de SMA_8
            Condition(
                indicator="SMA_5",
                operator="crossover",
                value="SMA_8",
            ),
            # RSI < 60
            Condition(
                indicator="RSI_14",
                operator="<",
                value=60,
            ),
            # Volume > avg_volume
            Condition(
                indicator="Volume",
                operator=">",
                value="SMA_20_VOL",
            ),
        ],
        exit_rules=[
            # SMA_8 cruza por encima de SMA_5
            Condition(
                indicator="SMA_8",
                operator="crossover",
                value="SMA_5",
            ),
            # RSI > 70
            Condition(
                indicator="RSI_14",
                operator=">",
                value=70,
            ),
        ],
        risk=RiskSettings(
            stop_loss_pct=None,
            take_profit_pct=None,
            position_sizing="fixed",
        ),
        metadata={
            "description": "SMA 5/8 + RSI + volumen sobre promedio",
        },
    )

    def init(self):
        self.volume = self.I(lambda: self.data.Volume)
        self.avg_volume = self.I(
            lambda: self.data.SMA_20_VOL, name="SMA_20_VOL"
        )
        self.rsi = self.I(lambda: self.data.RSI_14, name="RSI_14")
        self.sma_5 = self.I(lambda: self.data.SMA_5, name="SMA_5")
        self.sma_8 = self.I(lambda: self.data.SMA_8, name="SMA_8")

    def next(self):
        # Entrada: cruce alcista + RSI bajo + volumen mayor al promedio
        if (
            not self.position
            and crossover(self.sma_5, self.sma_8)
            and self.rsi[-1] < 60
            and self.volume[-1] > self.avg_volume[-1]
        ):
            self.buy()

        # Salida: cruce bajista o RSI alto
        elif self.position and (
            crossover(self.sma_8, self.sma_5) or self.rsi[-1] > 70
        ):
            self.position.close()
