import logging
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from src.domain.signals.interpreters.base_interpreter import BaseStrategyInterpreter
from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum

logger = logging.getLogger(__name__)

VOLATILITY_SIGNAL_TTL_DAYS = 90


class VolatilityInterpreter(BaseStrategyInterpreter):
    """
    Genera señales basadas en volatilidad usando ATR y Bollinger Bands.
    """

    def interpret(
        self,
        df: pd.DataFrame,
        config: StrategyConfigDTO,
    ) -> List[SignalDTO]:
        logger.info("⚡ Analizando volatility signals...")
        signals: List[SignalDTO] = []

        if df.empty:
            return signals

        entry_rules = config.params.entry_rules
        exit_rules = config.params.exit_rules
        all_rules = entry_rules + exit_rules

        volatility_indicators = {
            "ATR_14",
            "BBL_20_2.0",
            "BBU_20_2.0",
        }

        uses_volatility = any(
            rule.indicator in volatility_indicators for rule in all_rules)
        if not uses_volatility:
            return signals

        latest = df.iloc[-1]
        symbol = config.symbol
        now = datetime.now()
        expires_at = now + timedelta(days=VOLATILITY_SIGNAL_TTL_DAYS)
        close_price = float(latest.get(
            "Close")) if "Close" in df.columns else None

        # ============================
        #        BOLLINGER BANDS
        # ============================
        if all(c in df.columns for c in ["BBL_20_2.0", "BBU_20_2.0", "Close"]):
            bb_lower = latest.get("BBL_20_2.0")
            bb_upper = latest.get("BBU_20_2.0")
            close = latest.get("Close")

            if bb_lower and bb_upper and close and not pd.isna(close):
                # Precio bajo → potencial rebote
                if close <= bb_lower:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.VOLATILITY,
                            signal_type=SignalTypeEnum.BUY,
                            confidence=0.65,
                            strength=SignalStrengthEnum.MODERATE,
                            price=close_price,
                            meta={
                                "kind": "bollinger_band",
                                "position": "lower_band",
                                "interpretation": "oversold_potential_reversal",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

                # Precio alto → posible corrección
                elif close >= bb_upper:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.VOLATILITY,
                            signal_type=SignalTypeEnum.SELL,
                            confidence=0.65,
                            strength=SignalStrengthEnum.MODERATE,
                            price=close_price,
                            meta={
                                "kind": "bollinger_band",
                                "position": "upper_band",
                                "interpretation": "overbought_pullback_likely",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        # ============================
        #             ATR
        # ============================
        if "ATR_14" in df.columns and len(df) >= 20:
            current_atr = latest.get("ATR_14")
            avg_atr = df["ATR_14"].tail(20).mean()

            if current_atr and avg_atr and not pd.isna(current_atr) and not pd.isna(avg_atr):
                atr_factor = current_atr / avg_atr

                if atr_factor > 1.5:
                    # Volatilidad expandiéndose → riesgo pero oportunidad
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.VOLATILITY,
                            signal_type=SignalTypeEnum.ALERT,
                            confidence=0.7,
                            strength=SignalStrengthEnum.EXTREME,
                            price=close_price,
                            meta={
                                "kind": "atr_spike",
                                "atr_ratio": round(atr_factor, 2),
                                "interpretation": "high_volatility_regime",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

                elif atr_factor < 0.7:
                    # Contracción → posible squeeze → breakout pronto
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.VOLATILITY,
                            signal_type=SignalTypeEnum.ALERT,
                            confidence=0.6,
                            strength=SignalStrengthEnum.MODERATE,
                            price=close_price,
                            meta={
                                "kind": "atr_contraction",
                                "atr_ratio": round(atr_factor, 2),
                                "interpretation": "low_volatility_breakout_warning",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        logger.info(
            f"✅ Volatility analysis: {len(signals)} signals detectados")
        return signals
