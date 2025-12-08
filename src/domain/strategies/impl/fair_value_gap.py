import pandas as pd
from src.domain.strategies.impl.base import ConfigurableStrategy
from src.domain.strategies.dtos.config_dto import (
    StrategyParamsDTO,
    Condition,
    RiskSettings,
)


class FairValueGapStrategy(ConfigurableStrategy):
    """
    Estrategia mejorada de Fair Value Gap con:
    - Filtros de calidad del gap
    - Gestión de riesgo
    - Confirmación de momentum
    """

    CONFIG = StrategyParamsDTO(
        strategy_name="FairValueGapStrategy",
        entry_rules=[
            # Gap alcista presente
            Condition(indicator="fvg_type", operator="==", value=1),
            Condition(indicator="fvg_size", operator=">", value=0),

            Condition(indicator="RSI_14", operator=">", value=60),
            Condition(
                indicator="MACD_12_26_9",
                operator=">",
                value="MACDs_12_26_9",
            ),
        ],
        exit_rules=[
            Condition(indicator="fvg_type", operator="==", value=-1),
            Condition(indicator="RSI_14", operator="<", value=35),
        ],
        risk=RiskSettings(
            risk_reward_ratio=2.0,
            position_sizing="volatility_based",
        ),
        metadata={
            "use_momentum_filter": True,
            "risk_per_trade": 0.05,
            "description": "FVG con filtros de calidad y momentum (RSI + MACD)",
        },
    )

    # === Atributos de implementación concreta ===
    use_momentum_filter = True
    risk_reward_ratio = 2.0  # RR 2:1

    def init(self):
        self.fvg_type = self.I(lambda: self.data.fvg_type, name="FVG_Type")
        self.fvg_start = self.I(lambda: self.data.fvg_start, name="FVG_Start")
        self.fvg_end = self.I(lambda: self.data.fvg_end, name="FVG_End")
        self.fvg_size = self.I(lambda: self.data.fvg_size, name="FVG_Size")

        # RSI
        self.rsi = (
            self.I(lambda: self.data.RSI_14, name="RSI")
            if hasattr(self.data, "RSI_14")
            else None
        )

        # MACD
        if hasattr(self.data, "MACD_12_26_9") and hasattr(
            self.data, "MACDs_12_26_9"
        ):
            self.macd = self.I(lambda: self.data.MACD_12_26_9, name="MACD")
            self.macd_signal = self.I(
                lambda: self.data.MACDs_12_26_9, name="MACD_Signal"
            )
        else:
            self.macd = None
            self.macd_signal = None

    # --------------------------------------------------------------------

    def has_momentum_confirmation(self, fvg_type):
        """Verifica confirmación de momentum si está habilitada"""
        if not self.use_momentum_filter:
            return True

        # --- RSI ---
        if self.rsi is not None:
            rsi_val = self.rsi[-1]
            if fvg_type == 1 and rsi_val <= 60:
                return False
            if fvg_type == -1 and rsi_val >= 40:
                return False

        # --- MACD ---
        if self.macd is not None and self.macd_signal is not None:
            macd_val, sig_val = self.macd[-1], self.macd_signal[-1]
            if fvg_type == 1 and macd_val <= sig_val:
                return False
            if fvg_type == -1 and macd_val >= sig_val:
                return False

        return True

    # --------------------------------------------------------------------

    def calculate_position_size(self, gap_size, current_price):
        """
        Size debe cumplir:
        - entero >= 1   → válido
        """
        risk_per_trade = 0.05
        stop_distance = gap_size * 0.5

        if stop_distance <= 0:
            return 1  # fallback seguro

        raw_size = (risk_per_trade * self.equity) / stop_distance

        # Size entero en rango seguro
        size = int(max(1, min(1000, raw_size)))

        return size

    # --------------------------------------------------------------------

    def next(self):
        current_price = self.data.Close[-1]
        current_fvg = self.fvg_type[-1]
        current_gap_size = self.fvg_size[-1]

        if pd.isna(current_fvg) or pd.isna(current_gap_size):
            return

        # ============================
        #       ENTRADA LONG
        # ============================
        if not self.position and current_fvg == 1:
            if self.has_momentum_confirmation(1):

                position_size = self.calculate_position_size(
                    current_gap_size, current_price
                )

                gap_start = self.fvg_start[-1]
                if pd.isna(gap_start):
                    return

                stop_loss = gap_start * 0.995
                take_profit = current_price + (
                    (current_price - stop_loss) * self.risk_reward_ratio
                )

                self.buy(size=position_size, sl=stop_loss, tp=take_profit)

        # ============================
        #       ENTRADA SHORT
        # ============================
        elif not self.position and current_fvg == -1:
            if self.has_momentum_confirmation(-1):

                position_size = self.calculate_position_size(
                    current_gap_size, current_price
                )

                gap_start = self.fvg_start[-1]
                if pd.isna(gap_start):
                    return

                stop_loss = gap_start * 1.005
                take_profit = current_price - (
                    (stop_loss - current_price) * self.risk_reward_ratio
                )

                self.sell(size=position_size, sl=stop_loss, tp=take_profit)

        # ============================
        #   GESTION DE POSICION
        # ============================
        elif self.position:

            # Reversión por FVG opuesto
            if (self.position.is_long and current_fvg == -1) or (
                self.position.is_short and current_fvg == 1
            ):
                self.position.close()
                return

            # Manejo por momentum adverso
            if self.position.is_long:
                if self.rsi is not None and self.rsi[-1] < 35:
                    self.position.close()

            elif self.position.is_short:
                if self.rsi is not None and self.rsi[-1] > 65:
                    self.position.close()
