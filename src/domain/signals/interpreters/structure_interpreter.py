import logging
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from src.domain.signals.interpreters.base_interpreter import BaseStrategyInterpreter
from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum

logger = logging.getLogger(__name__)

STRUCTURE_SIGNAL_TTL_DAYS = 180


class StructureInterpreter(BaseStrategyInterpreter):
    """
    Interpreta estructura de mercado: Fair Value Gaps, zonas y breakouts
    """

    def interpret(
        self,
        df: pd.DataFrame,
        config: StrategyConfigDTO,
    ) -> List[SignalDTO]:
        logger.info("🏗️ Analyzing market structure...")
        signals: List[SignalDTO] = []

        if df.empty:
            return signals

        entry_rules = config.params.entry_rules
        exit_rules = config.params.exit_rules
        all_rules = entry_rules + exit_rules

        has_fvg_rules = any(
            rule.indicator.startswith("fvg_")
            for rule in all_rules
        )

        zone_indicators = {
            "main_support",
            "main_resistance",
            "zone_support_1",
            "zone_support_2",
            "zone_support_3",
            "zone_resistance_1",
            "zone_resistance_2",
            "zone_resistance_3",
        }
        has_zone_rules = any(
            rule.indicator in zone_indicators for rule in all_rules)

        if not has_fvg_rules and not has_zone_rules:
            return signals

        latest = df.iloc[-1]
        symbol = config.symbol
        now = datetime.now()
        expires_at = now + timedelta(days=STRUCTURE_SIGNAL_TTL_DAYS)

        # ============================
        #       FAIR VALUE GAPS
        # ============================
        if has_fvg_rules and "fvg_type" in df.columns:
            fvg_type = latest.get("fvg_type")
            if not pd.isna(fvg_type):
                fvg_size = latest.get("fvg_size")
                gap_start = latest.get("fvg_start")
                gap_end = latest.get("fvg_end")

                if fvg_type == 1:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.STRUCTURE,
                            signal_type=SignalTypeEnum.BUY,
                            confidence=0.7,
                            strength=SignalStrengthEnum.STRONG,
                            price=float(latest.get("Close")),
                            meta={
                                "kind": "fair_value_gap",
                                "direction": "bullish",
                                "gap_size": float(fvg_size) if fvg_size is not None else None,
                                "gap_start": gap_start,
                                "gap_end": gap_end,
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )
                elif fvg_type == -1:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.STRUCTURE,
                            signal_type=SignalTypeEnum.SELL,
                            confidence=0.7,
                            strength=SignalStrengthEnum.STRONG,
                            price=float(latest.get("Close")),
                            meta={
                                "kind": "fair_value_gap",
                                "direction": "bearish",
                                "gap_size": float(fvg_size) if fvg_size is not None else None,
                                "gap_start": gap_start,
                                "gap_end": gap_end,
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        # ============================
        #        ZONAS / BREAKOUTS
        # ============================
        if has_zone_rules and "Close" in df.columns:
            close = latest["Close"]

            # Breakout sobre resistencia principal
            if (
                "main_resistance" in df.columns
                and not pd.isna(latest.get("main_resistance"))
            ):
                main_resistance = latest["main_resistance"]

                # breakout “fuerte”
                if close > main_resistance * 1.002:  # +0.2%
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.STRUCTURE,
                            signal_type=SignalTypeEnum.BUY,
                            confidence=0.8,
                            strength=SignalStrengthEnum.STRONG,
                            price=float(close),
                            meta={
                                "kind": "breakout",
                                "direction": "up",
                                "zone_type": "main_resistance",
                                "zone_value": float(main_resistance),
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )
                else:
                    # proximidad a resistencia
                    dist = abs(close - main_resistance) / main_resistance
                    if dist <= 0.005:  # 0.5%
                        signals.append(
                            SignalDTO(
                                symbol=symbol,
                                signal_source=SignalSourceEnum.STRUCTURE,
                                signal_type=SignalTypeEnum.ALERT,
                                confidence=0.5,
                                strength=SignalStrengthEnum.MODERATE,
                                price=float(close),
                                meta={
                                    "kind": "zone_proximity",
                                    "direction": "resistance_approach",
                                    "zone_type": "main_resistance",
                                    "zone_value": float(main_resistance),
                                    "distance_pct": dist * 100,
                                    "strategy_name": config.strategy_name,
                                },
                                created_at=now,
                                expires_at=expires_at,
                            )
                        )

            # Breakdown sobre soporte principal
            if (
                "main_support" in df.columns
                and not pd.isna(latest.get("main_support"))
            ):
                main_support = latest["main_support"]

                if close < main_support * 0.998:  # -0.2%
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.STRUCTURE,
                            signal_type=SignalTypeEnum.SELL,
                            confidence=0.8,
                            strength=SignalStrengthEnum.STRONG,
                            price=float(close),
                            meta={
                                "kind": "breakout",
                                "direction": "down",
                                "zone_type": "main_support",
                                "zone_value": float(main_support),
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )
                else:
                    dist = abs(close - main_support) / main_support
                    if dist <= 0.005:
                        signals.append(
                            SignalDTO(
                                symbol=symbol,
                                signal_source=SignalSourceEnum.STRUCTURE,
                                signal_type=SignalTypeEnum.ALERT,
                                confidence=0.5,
                                strength=SignalStrengthEnum.MODERATE,
                                price=float(close),
                                meta={
                                    "kind": "zone_proximity",
                                    "direction": "support_approach",
                                    "zone_type": "main_support",
                                    "zone_value": float(main_support),
                                    "distance_pct": dist * 100,
                                    "strategy_name": config.strategy_name,
                                },
                                created_at=now,
                                expires_at=expires_at,
                            )
                        )

        logger.info(f"✅ Structure analysis: {len(signals)} signals detected")
        return signals
