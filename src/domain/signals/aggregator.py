import logging
from datetime import datetime
from typing import Iterable, List, Dict, Optional

from src.domain.signals.dtos.signal_dto import SignalDTO
from src.commons.enums.signal_enums import (
    SignalTypeEnum,
    SignalStrengthEnum,
    SignalSourceEnum,
)

logger = logging.getLogger(__name__)


class SignalAggregator:
    """
    Agrega múltiples SignalDTO (de distintos intérpretes/estrategias)
    y devuelve UNA única señal operable.

    Reglas de negocio:
    - La decisión final SIEMPRE es BUY, SELL o HOLD.
    - Nunca devolvemos ALERT.
    - Actualmente no operamos en corto: SELL se interpreta como "cerrar/vender",
      no como abrir short.
    - EXIT se considera semánticamente como SELL para el agregado (cerrar posición).
    """

    STRENGTH_WEIGHTS: Dict[SignalStrengthEnum, float] = {
        SignalStrengthEnum.WEAK: 0.5,
        SignalStrengthEnum.MODERATE: 0.75,
        SignalStrengthEnum.STRONG: 1.0,
        SignalStrengthEnum.EXTREME: 1.25,
    }

    MIN_SCORE: float = 0.4    # score mínimo para animarse a tomar acción
    MIN_MARGIN: float = 0.15  # diferencia mínima entre el mejor y el segundo

    def aggregate(self, signals: Iterable[SignalDTO]) -> Optional[SignalDTO]:
        signals = [s for s in signals if s is not None]

        if not signals:
            logger.info("🔇 SignalAggregator: no signals to aggregate")
            return None

        # ============================
        #   0) Procesar ALERTS por source
        # ============================
        alert_signals: List[SignalDTO] = [
            s for s in signals if s.signal_type == SignalTypeEnum.ALERT
        ]

        # Alertas que SÍ matizan riesgo (volumen, volatilidad, riesgo)
        risk_alerts: List[SignalDTO] = [
            s
            for s in alert_signals
            if s.signal_source in {
                SignalSourceEnum.VOLUME,
                SignalSourceEnum.VOLATILITY,
                SignalSourceEnum.RISK,
            }
        ]

        # Alertas informativas (estructura, tendencia, etc.) que no afectan ejecución
        ignored_alerts: List[SignalDTO] = [
            s for s in alert_signals if s not in risk_alerts
        ]

        if ignored_alerts:
            logger.info(
                f"ℹ️ Ignorando {len(ignored_alerts)} ALERT(s) no operativas "
                f"para la capa de riesgo."
            )

        risk_context = self._build_risk_context(risk_alerts)

        # ============================
        #  1) Ignorar ALERTs para el voto operable
        # ============================
        non_alert_signals: List[SignalDTO] = [
            s for s in signals if s.signal_type != SignalTypeEnum.ALERT
        ]

        # Si solo hay ALERTs → HOLD, pero con contexto de riesgo seteado
        if not non_alert_signals:
            best_alert = max(signals, key=self._score)
            logger.info(
                f"📌 Solo ALERTs presentes, decisión operativa → HOLD "
                f"(mejor ALERT conf={best_alert.confidence})"
            )
            return self._build_aggregated_signal(
                chosen_type=SignalTypeEnum.HOLD,
                base_signal=best_alert,
                signals=signals,
                final_score=self._score(best_alert),
                risk_context=risk_context,
            )

        # ============================
        #  2) Direccionales relevantes para la decisión
        # ============================
        directional_types = {
            SignalTypeEnum.BUY,
            SignalTypeEnum.SELL,
            SignalTypeEnum.EXIT,
            SignalTypeEnum.HOLD,
        }

        directional_signals: List[SignalDTO] = [
            s for s in non_alert_signals if s.signal_type in directional_types
        ]

        if not directional_signals:
            logger.info("🔇 SignalAggregator: no directional signals")
            return None

        # === 2.1) Sumamos score por tipo normalizado (EXIT cuenta como SELL) ===
        score_by_type: Dict[SignalTypeEnum, float] = {}

        for s in directional_signals:
            score = self._score(s)

            normalized_type = (
                SignalTypeEnum.SELL
                if s.signal_type == SignalTypeEnum.EXIT
                else s.signal_type
            )

            score_by_type[normalized_type] = (
                score_by_type.get(normalized_type, 0.0) + score
            )

        # Ordenamos por score total
        sorted_types = sorted(
            score_by_type.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )

        best_type, best_score = sorted_types[0]
        second_score = sorted_types[1][1] if len(sorted_types) > 1 else 0.0

        logger.info(
            "📊 Aggregation scores → "
            + ", ".join(
                f"{t.value}: {round(v, 3)}" for t, v in score_by_type.items()
            )
        )

        # === 2.2) Decisión: ¿hay ganador claro? ===
        if best_score < self.MIN_SCORE or (best_score - second_score) < self.MIN_MARGIN:
            logger.info(
                f"🤝 Sin consenso claro (best_score={best_score:.3f}, "
                f"second={second_score:.3f}) → HOLD"
            )
            chosen_type = SignalTypeEnum.HOLD
        else:
            chosen_type = best_type  # BUY / SELL / HOLD
            logger.info(
                f"✅ Consenso → {chosen_type.value.upper()} "
                f"(score={best_score:.3f})"
            )

        # === 2.3) Overlay de riesgo con ALERTS de volumen/volatilidad/riesgo ===
        # Regla conservadora: si hay condiciones EXTREME de riesgo, frenamos BUY.
        if (
            chosen_type == SignalTypeEnum.BUY
            and risk_context.get("extreme_conditions")
        ):
            logger.info(
                "⚠️ Contexto EXTREME (volatilidad/volumen/riesgo). "
                "Regla conservadora: degradamos BUY → HOLD."
            )
            chosen_type = SignalTypeEnum.HOLD

        # ============================
        #  3) Elegimos una señal base del tipo ganador
        # ============================
        def _normalized_type(s: SignalDTO) -> SignalTypeEnum:
            if s.signal_type == SignalTypeEnum.EXIT:
                return SignalTypeEnum.SELL
            return s.signal_type

        same_type_signals = [
            s for s in directional_signals if _normalized_type(s) == chosen_type
        ]

        if same_type_signals:
            base_signal = max(same_type_signals, key=lambda s: self._score(s))
        else:
            # fallback defensivo (no debería pasar)
            base_signal = max(directional_signals,
                              key=lambda s: self._score(s))

        return self._build_aggregated_signal(
            chosen_type=chosen_type,
            base_signal=base_signal,
            signals=signals,
            final_score=best_score,
            risk_context=risk_context,
        )

    # ======================================================
    # Helpers
    # ======================================================

    def _score(self, s: SignalDTO) -> float:
        strength_weight = self.STRENGTH_WEIGHTS.get(s.strength, 1.0)
        return float(s.confidence) * float(strength_weight)

    def _strength_from_score(self, score: float) -> SignalStrengthEnum:
        if score >= 1.8:
            return SignalStrengthEnum.EXTREME
        if score >= 1.2:
            return SignalStrengthEnum.STRONG
        if score >= 0.7:
            return SignalStrengthEnum.MODERATE
        return SignalStrengthEnum.WEAK

    def _build_risk_context(
        self,
        risk_alerts: List[SignalDTO],
    ) -> Dict[str, any]:
        """
        Resume el contexto de riesgo a partir de ALERTs de volumen/volatilidad/riesgo.
        No decide nada por sí mismo, solo etiqueta el régimen.
        """
        if not risk_alerts:
            return {
                "has_risk_alerts": False,
                "high_volatility": False,
                "volume_spike": False,
                "risk_events": False,
                "extreme_conditions": False,
                "risk_alerts_count": 0,
            }

        has_high_vol = any(
            (a.meta or {}).get("kind") == "atr_spike"
            for a in risk_alerts
        )
        has_vol_spike = any(
            (a.meta or {}).get("kind") == "volume_spike"
            for a in risk_alerts
        )
        has_risk = any(
            a.signal_source == SignalSourceEnum.RISK
            for a in risk_alerts
        )
        has_extreme = any(
            a.strength == SignalStrengthEnum.EXTREME
            for a in risk_alerts
        )

        return {
            "has_risk_alerts": True,
            "high_volatility": has_high_vol,
            "volume_spike": has_vol_spike,
            "risk_events": has_risk,
            "extreme_conditions": has_extreme,
            "risk_alerts_count": len(risk_alerts),
        }

    def _build_aggregated_signal(
        self,
        chosen_type: SignalTypeEnum,
        base_signal: SignalDTO,
        signals: List[SignalDTO],
        final_score: float,
        risk_context: Optional[Dict[str, any]] = None,
    ) -> SignalDTO:
        """
        Construye un SignalDTO "resumen" usando una señal base
        y agregando info al meta.
        """

        # Confidence agregada (no pasa de 1.0).
        # Para HOLD ponemos 1.0 → "estamos tranquilos de no hacer nada".
        aggregated_confidence = (
            1.0
            if chosen_type == SignalTypeEnum.HOLD
            else max(
                min(final_score, 1.0),
                float(base_signal.confidence),
            )
        )

        aggregated_strength = self._strength_from_score(final_score)

        # Elegimos la expiración más cercana (conservador)
        valid_expires = [
            s.expires_at for s in signals if s.expires_at is not None]
        expires_at = min(
            valid_expires) if valid_expires else base_signal.expires_at

        # Meta: trazabilidad de qué se usó
        meta = base_signal.meta.copy() if base_signal.meta else {}

        # Conteo por tipo de señal (BUY/SELL/etc.)
        type_counts: Dict[str, int] = {}
        for s in signals:
            t = s.signal_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        # Conteo por fuente (momentum/volatility/etc.)
        source_counts: Dict[str, int] = {}
        for s in signals:
            src = s.signal_source.value
            source_counts[src] = source_counts.get(src, 0) + 1

        meta["aggregated"] = True
        meta["source_signals_count"] = len(signals)
        meta["source_types"] = type_counts
        meta["source_sources"] = source_counts
        meta["aggregator_info"] = {
            "chosen_type": chosen_type.value,
            "final_score": final_score,
        }
        if risk_context is not None:
            meta["risk_context"] = risk_context

        return SignalDTO(
            id=None,
            symbol=base_signal.symbol,
            signal_source=base_signal.signal_source,
            signal_type=chosen_type,
            confidence=aggregated_confidence,
            strength=aggregated_strength,
            price=base_signal.price,
            target_price=base_signal.target_price,
            stop_loss=base_signal.stop_loss,
            meta=meta,
            created_at=datetime.now(),
            expires_at=expires_at,
        )
