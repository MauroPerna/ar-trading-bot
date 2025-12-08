import logging
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from src.domain.signals.interpreters.base_interpreter import BaseStrategyInterpreter
from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum

logger = logging.getLogger(__name__)

MOMENTUM_SIGNAL_TTL_DAYS = 180


class MomentumInterpreter(BaseStrategyInterpreter):
    """
    Interpreta indicadores de momentum: RSI, MACD, Williams %R y Stochastic RSI
    """

    def interpret(
        self,
        df: pd.DataFrame,
        config: StrategyConfigDTO,
    ) -> List[SignalDTO]:
        logger.info("📈 Analizando momentum signals...")
        signals: List[SignalDTO] = []

        if df.empty:
            return signals

        # 1) Ver si la estrategia realmente usa indicadores de momentum
        entry_rules = config.params.entry_rules
        exit_rules = config.params.exit_rules
        all_rules = entry_rules + exit_rules

        momentum_indicators = {
            "RSI_14",
            "MACD_12_26_9",
            "MACDs_12_26_9",
            "WILLR_14",
            "STOCHRSIk_14_14_3_3",
        }

        has_momentum_rules = any(
            rule.indicator in momentum_indicators for rule in all_rules
        )
        if not has_momentum_rules:
            return signals

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest

        symbol = config.symbol
        price = float(latest.get("Close")) if "Close" in df.columns else None
        now = datetime.now()
        expires_at = now + timedelta(days=MOMENTUM_SIGNAL_TTL_DAYS)

        # ============================
        #             RSI
        # ============================
        if "RSI_14" in df.columns and not pd.isna(latest.get("RSI_14")):
            rsi = float(latest["RSI_14"])

            # RSI oversold → posible BUY
            if rsi < 30:
                confidence = min(1.0, (30 - rsi) / 30)
                strength = (
                    SignalStrengthEnum.STRONG if rsi < 20 else SignalStrengthEnum.MODERATE
                )

                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.MOMENTUM,
                        signal_type=SignalTypeEnum.BUY,
                        confidence=confidence,
                        strength=strength,
                        price=price,
                        meta={
                            "kind": "momentum",
                            "indicator": "RSI_14",
                            "condition": "oversold",
                            "value": round(rsi, 2),
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )

            elif rsi > 70:
                confidence = min(1.0, (rsi - 70) / 30)
                strength = (
                    SignalStrengthEnum.STRONG if rsi > 80 else SignalStrengthEnum.MODERATE
                )

                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.MOMENTUM,
                        signal_type=SignalTypeEnum.SELL,
                        confidence=confidence,
                        strength=strength,
                        price=price,
                        meta={
                            "kind": "momentum",
                            "indicator": "RSI_14",
                            "condition": "overbought",
                            "value": round(rsi, 2),
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )

        # ============================
        #             MACD
        # ============================
        if (
            "MACD_12_26_9" in df.columns
            and "MACDs_12_26_9" in df.columns
            and len(df) >= 2
        ):
            macd_curr = latest.get("MACD_12_26_9")
            macd_sig_curr = latest.get("MACDs_12_26_9")
            macd_prev = prev.get("MACD_12_26_9")
            macd_sig_prev = prev.get("MACDs_12_26_9")

            if not any(
                pd.isna(v) for v in [macd_curr, macd_sig_curr, macd_prev, macd_sig_prev]
            ):
                # Cruce alcista MACD sobre signal → BUY
                if macd_curr > macd_sig_curr and macd_prev <= macd_sig_prev:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.MOMENTUM,
                            signal_type=SignalTypeEnum.BUY,
                            confidence=0.75,
                            strength=SignalStrengthEnum.STRONG,
                            price=price,
                            meta={
                                "kind": "momentum",
                                "indicator": "MACD",
                                "event": "bullish_cross",
                                "macd": float(macd_curr),
                                "signal": float(macd_sig_curr),
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )
                # Cruce bajista MACD bajo signal → SELL
                elif macd_curr < macd_sig_curr and macd_prev >= macd_sig_prev:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.MOMENTUM,
                            signal_type=SignalTypeEnum.SELL,
                            confidence=0.75,
                            strength=SignalStrengthEnum.STRONG,
                            price=price,
                            meta={
                                "kind": "momentum",
                                "indicator": "MACD",
                                "event": "bearish_cross",
                                "macd": float(macd_curr),
                                "signal": float(macd_sig_curr),
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        # ============================
        #          Williams %R
        # ============================
        if "WILLR_14" in df.columns and not pd.isna(latest.get("WILLR_14")):
            willr = float(latest["WILLR_14"])

            if willr < -80:
                # Sobreventa → BUY débil / complemento
                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.MOMENTUM,
                        signal_type=SignalTypeEnum.BUY,
                        confidence=0.5,
                        strength=SignalStrengthEnum.WEAK,
                        price=price,
                        meta={
                            "kind": "momentum",
                            "indicator": "WILLR_14",
                            "condition": "oversold",
                            "value": round(willr, 2),
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )
            elif willr > -20:
                # Sobrecompra → SELL débil
                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.MOMENTUM,
                        signal_type=SignalTypeEnum.SELL,
                        confidence=0.5,
                        strength=SignalStrengthEnum.WEAK,
                        price=price,
                        meta={
                            "kind": "momentum",
                            "indicator": "WILLR_14",
                            "condition": "overbought",
                            "value": round(willr, 2),
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )

        # ============================
        #         Stochastic RSI
        # ============================
        if (
            "STOCHRSIk_14_14_3_3" in df.columns
            and not pd.isna(latest.get("STOCHRSIk_14_14_3_3"))
        ):
            stoch = float(latest["STOCHRSIk_14_14_3_3"])

            if stoch < 0.2:
                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.MOMENTUM,
                        signal_type=SignalTypeEnum.BUY,
                        confidence=0.55,
                        strength=SignalStrengthEnum.WEAK,
                        price=price,
                        meta={
                            "kind": "momentum",
                            "indicator": "STOCHRSIk_14_14_3_3",
                            "condition": "oversold",
                            "value": round(stoch, 3),
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )
            elif stoch > 0.8:
                signals.append(
                    SignalDTO(
                        symbol=symbol,
                        signal_source=SignalSourceEnum.MOMENTUM,
                        signal_type=SignalTypeEnum.SELL,
                        confidence=0.55,
                        strength=SignalStrengthEnum.WEAK,
                        price=price,
                        meta={
                            "kind": "momentum",
                            "indicator": "STOCHRSIk_14_14_3_3",
                            "condition": "overbought",
                            "value": round(stoch, 3),
                            "strategy_name": config.strategy_name,
                        },
                        created_at=now,
                        expires_at=expires_at,
                    )
                )

        logger.info(f"✅ Momentum analysis: {len(signals)} signals detectadas")
        return signals
