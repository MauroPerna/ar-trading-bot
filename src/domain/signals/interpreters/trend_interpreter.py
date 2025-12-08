import logging
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from src.domain.signals.interpreters.base_interpreter import BaseStrategyInterpreter
from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum

logger = logging.getLogger(__name__)

TREND_SIGNAL_TTL_DAYS = 180


class TrendInterpreter(BaseStrategyInterpreter):
    """
    Interpreta señales de tendencia: cruces de EMA, fuerza de ADX, señal de tendencia.
    Genera señales de tipo BUY / SELL / ALERT según la información de tendencia.
    """

    def interpret(
        self,
        df: pd.DataFrame,
        config: StrategyConfigDTO,
    ) -> List[SignalDTO]:
        logger.info("📊 Analizando trend signals...")
        signals: List[SignalDTO] = []

        if df.empty:
            return signals

        entry_rules = config.params.entry_rules
        exit_rules = config.params.exit_rules
        all_rules = entry_rules + exit_rules

        trend_indicators = {
            "EMA_5",
            "EMA_8",
            "ADX_14",
            "DMP_14",
            "DMN_14",
            "trend_signal",
        }

        uses_trend = any(
            rule.indicator in trend_indicators for rule in all_rules)
        if not uses_trend:
            return signals

        latest = df.iloc[-1]
        symbol = config.symbol
        now = datetime.now()
        expires_at = now + timedelta(days=TREND_SIGNAL_TTL_DAYS)
        close_price = float(latest.get(
            "Close")) if "Close" in df.columns else None

        # ============================
        #      EMA 5 / EMA 8
        # ============================
        if (
            all(col in df.columns for col in ["EMA_5", "EMA_8"])
            and len(df) >= 2
        ):
            ema5_curr = latest.get("EMA_5")
            ema8_curr = latest.get("EMA_8")
            ema5_prev = df.iloc[-2].get("EMA_5")
            ema8_prev = df.iloc[-2].get("EMA_8")

            if all(
                val is not None and not pd.isna(val)
                for val in [ema5_curr, ema8_curr, ema5_prev, ema8_prev]
            ):
                # Golden cross → sesgo alcista
                if ema5_curr > ema8_curr and ema5_prev <= ema8_prev:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.TREND,
                            signal_type=SignalTypeEnum.BUY,
                            confidence=0.8,
                            strength=SignalStrengthEnum.MODERATE,
                            price=close_price,
                            meta={
                                "kind": "ema_cross",
                                "pair": "5_8",
                                "direction": "golden",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )
                # Death cross → sesgo bajista
                elif ema5_curr < ema8_curr and ema5_prev >= ema8_prev:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.TREND,
                            signal_type=SignalTypeEnum.SELL,
                            confidence=0.8,
                            strength=SignalStrengthEnum.MODERATE,
                            price=close_price,
                            meta={
                                "kind": "ema_cross",
                                "pair": "5_8",
                                "direction": "death",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        # ============================
        #      ADX + DMI
        # ============================
        if "ADX_14" in df.columns and not pd.isna(latest.get("ADX_14")):
            adx = latest["ADX_14"]
            if adx > 25:  # tendencia “válida”
                dmp = latest.get("DMP_14", 0)
                dmn = latest.get("DMN_14", 0)
                direction = "bullish" if dmp > dmn else "bearish"

                # Lo tratamos como contexto de alerta, no como señal dura de entrada/salida
                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.TREND,
                        signal_type=SignalTypeEnum.ALERT,
                        confidence=0.7 if adx > 40 else 0.6,
                        strength=SignalStrengthEnum.STRONG if adx > 40 else SignalStrengthEnum.MODERATE,
                        price=close_price,
                        meta={
                            "kind": "trend_strength",
                            "adx": round(float(adx), 2),
                            "direction": direction,
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )

        # ============================
        #      trend_signal custom
        # ============================
        if "trend_signal" in df.columns and not pd.isna(latest.get("trend_signal")):
            ts = latest["trend_signal"]

            if ts == 1:
                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.TREND,
                        signal_type=SignalTypeEnum.BUY,
                        confidence=0.85,
                        strength=SignalStrengthEnum.STRONG,
                        price=close_price,
                        meta={
                            "kind": "custom_trend",
                            "direction": "bullish",
                            "signal": "uptrend_confirmed",
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )
            elif ts == -1:
                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.TREND,
                        signal_type=SignalTypeEnum.SELL,
                        confidence=0.85,
                        strength=SignalStrengthEnum.STRONG,
                        price=close_price,
                        meta={
                            "kind": "custom_trend",
                            "direction": "bearish",
                            "signal": "downtrend_confirmed",
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )

        logger.info(f"✅ Trend analysis: {len(signals)} signals generados")
        return signals
