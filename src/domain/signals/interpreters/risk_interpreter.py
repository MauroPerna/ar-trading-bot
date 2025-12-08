import logging
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from src.domain.signals.interpreters.base_interpreter import BaseStrategyInterpreter
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum

logger = logging.getLogger(__name__)

RISK_SIGNAL_TTL_DAYS = 90


class RiskInterpreter(BaseStrategyInterpreter):
    """
    Evalúa riesgo: volatilidad (ATR), condiciones desfavorables y calidad del análisis.
    Genera ALERT o HOLD según gravedad.
    """

    def interpret(
        self,
        df: pd.DataFrame,
        config: StrategyConfigDTO,
    ) -> List[SignalDTO]:

        logger.info("⚠️ Evaluando condiciones de riesgo...")

        signals: List[SignalDTO] = []

        if df.empty:
            return signals

        # Si la estrategia NO usa ATR o riesgo, no emitimos señales
        uses_risk = (
            config.params.risk.stop_loss_pct is not None
            or config.params.risk.take_profit_pct is not None
            or "ATR_14" in df.columns
        )

        if not uses_risk:
            return signals

        latest = df.iloc[-1]
        symbol = config.symbol
        now = datetime.now()
        expires_at = now + timedelta(days=RISK_SIGNAL_TTL_DAYS)
        price = float(latest.get("Close", 0))

        # ============================
        #        VOLATILIDAD (ATR)
        # ============================

        if "ATR_14" in df.columns and len(df) >= 20:
            current_atr = latest.get("ATR_14")
            avg_atr = df["ATR_14"].tail(20).mean()

            if current_atr and avg_atr and not pd.isna(current_atr) and not pd.isna(avg_atr):
                atr_ratio = current_atr / avg_atr

                # Riesgo alto → precaución
                if atr_ratio > 1.5:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.RISK,
                            signal_type=SignalTypeEnum.ALERT,
                            confidence=0.75,
                            strength=SignalStrengthEnum.STRONG,
                            price=price,
                            meta={
                                "kind": "volatility_warning",
                                "condition": "high_volatility",
                                "atr_ratio": round(atr_ratio, 2),
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

                # Volatilidad extremadamente baja → HOLD (riesgo de falsa señal)
                elif atr_ratio < 0.6:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.RISK,
                            signal_type=SignalTypeEnum.HOLD,
                            confidence=0.6,
                            strength=SignalStrengthEnum.MODERATE,
                            price=price,
                            meta={
                                "kind": "volatility_warning",
                                "condition": "low_volatility",
                                "atr_ratio": round(atr_ratio, 2),
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        # ============================
        #     CALIDAD DE DATOS
        # ============================
        indicator_count = len([
            col for col in df.columns
            if col not in ["Open", "High", "Low", "Close", "Volume"]
        ])

        if indicator_count < 10:
            signals.append(
                SignalDTO(
                    symbol=symbol,
                    signal_source=SignalSourceEnum.RISK,
                    signal_type=SignalTypeEnum.ALERT,
                    confidence=0.4,
                    strength=SignalStrengthEnum.WEAK,
                    price=price,
                    meta={
                        "kind": "data_quality",
                        "issue": "low_indicator_density",
                        "indicator_count": indicator_count,
                        "strategy_name": config.strategy_name,
                    },
                    created_at=now,
                    expires_at=expires_at,
                )
            )

        logger.info(f"✅ Risk analysis: {len(signals)} risk signals generados")
        return signals
