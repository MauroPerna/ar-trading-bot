import numpy as np
from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class VolumeSpikeEntryStrategy(ConfigurableStrategy):
    """
    Estrategia basada en spikes de volumen.
    Entra sólo cuando hay spike + cooldown cumplido.
    Sale cuando el spike desaparece.
    """

    CONFIG = StrategyParamsDTO(
        strategy_name="VolumeSpikeEntryStrategy",
        entry_rules=[
            Condition(
                indicator="volume_spike",
                operator="==",
                value=True
            ),
        ],
        exit_rules=[
            Condition(
                indicator="volume_spike",
                operator="==",
                value=False
            )
        ],
        risk=RiskSettings(
            stop_loss_pct=None,
            take_profit_pct=None,
            position_sizing="fixed",
            cooldown_period=5,  # 👈 sincronizado con el código original
        ),
        metadata={"description": "Entrada basada en volumen extremo"},
    )

    def init(self):
        self.spike = self.I(lambda: self.data.volume_spike, name="VolSpike")
        self.last_exit_index = -np.inf

    def next(self):
        i = len(self.data) - 1

        # ENTRY
        if (
            not self.position
            and self.spike[-1]
            and (i - self.last_exit_index) > self.CONFIG.risk.cooldown_period
        ):
            self.buy()

        # EXIT
        elif self.position and not self.spike[-1]:
            self.position.close()
            self.last_exit_index = i
