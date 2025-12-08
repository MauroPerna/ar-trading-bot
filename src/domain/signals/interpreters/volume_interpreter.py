import logging
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from src.domain.signals.interpreters.base_interpreter import BaseStrategyInterpreter
from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum

logger = logging.getLogger(__name__)

VOLUME_SIGNAL_TTL_DAYS = 60


class VolumeInterpreter(BaseStrategyInterpreter):
    """
    Interpreta señales relacionadas al volumen: spikes y divergencias con precio.
    Solo genera señales si la estrategia usa indicadores de volumen.
    """

    def interpret(
        self,
        df: pd.DataFrame,
        config: StrategyConfigDTO,
    ) -> List[SignalDTO]:
        logger.info("📦 Analizando volume signals...")
        signals: List[SignalDTO] = []

        if df.empty or "Volume" not in df.columns:
            return signals

        entry_rules = config.params.entry_rules
        exit_rules = config.params.exit_rules
        all_rules = entry_rules + exit_rules

        volume_indicators = {
            "Volume",
            "SMA_20_VOL",
            "avg_volume",
            "OBV",
            "volume_spike",
        }

        uses_volume = any(
            rule.indicator in volume_indicators for rule in all_rules)
        if not uses_volume:
            return signals

        latest = df.iloc[-1]
        symbol = config.symbol
        now = datetime.now()
        expires_at = now + timedelta(days=VOLUME_SIGNAL_TTL_DAYS)

        # ============================
        #        VOLUME SPIKE
        # ============================
        if "SMA_20_VOL" in df.columns and not pd.isna(latest.get("SMA_20_VOL")):
            current_vol = latest.get("Volume", 0.0)
            avg_vol = latest["SMA_20_VOL"]

            if avg_vol and avg_vol > 0 and not pd.isna(current_vol):
                multiplier = float(current_vol / avg_vol)

                if multiplier > 2.0:
                    confidence = max(
                        0.6, min(0.95, 0.5 + (multiplier - 2.0) * 0.15))
                    strength = (
                        SignalStrengthEnum.EXTREME
                        if multiplier >= 4
                        else SignalStrengthEnum.STRONG
                    )

                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.VOLUME,
                            signal_type=SignalTypeEnum.ALERT,
                            confidence=confidence,
                            strength=strength,
                            price=float(latest.get("Close")
                                        ) if "Close" in df.columns else None,
                            meta={
                                "kind": "volume_spike",
                                "multiplier": round(multiplier, 2),
                                "interpretation": "unusual_volume_high_interest",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        # ============================
        #        OBV DIVERGENCE
        # ============================
        if "OBV" in df.columns and len(df) >= 2 and "Close" in df.columns:
            obv_curr = latest.get("OBV")
            obv_prev = df.iloc[-2].get("OBV")
            price_curr = latest.get("Close")
            price_prev = df.iloc[-2].get("Close")

            if all(
                val is not None and not pd.isna(val)
                for val in [obv_curr, obv_prev, price_curr, price_prev]
            ):
                price_up = price_curr > price_prev
                obv_up = obv_curr > obv_prev

                # Precio sube pero OBV baja → debilidad
                if price_up and not obv_up:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.VOLUME,
                            signal_type=SignalTypeEnum.SELL,
                            confidence=0.65,
                            strength=SignalStrengthEnum.MODERATE,
                            price=float(price_curr),
                            meta={
                                "kind": "obv_divergence",
                                "price_direction": "up",
                                "volume_direction": "down",
                                "interpretation": "up_move_on_weak_volume",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

                # Precio baja pero OBV sube → fortaleza oculta
                elif (not price_up) and obv_up:
                    signals.append(
                        SignalDTO(
                            symbol=symbol,
                            signal_source=SignalSourceEnum.VOLUME,
                            signal_type=SignalTypeEnum.BUY,
                            confidence=0.65,
                            strength=SignalStrengthEnum.MODERATE,
                            price=float(price_curr),
                            meta={
                                "kind": "obv_divergence",
                                "price_direction": "down",
                                "volume_direction": "up",
                                "interpretation": "down_move_on_strong_volume",
                                "strategy_name": config.strategy_name,
                            },
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )

        logger.info(f"✅ Volume analysis: {len(signals)} signals detectados")
        return signals
