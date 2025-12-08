from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Dict, Iterable, Tuple
import numpy as np
import pandas as pd
import pandas_ta as ta
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


_ALLOWED_TF = {"1s", "1m", "5m", "15m", "1h", "4h", "1d", "1w", "1mn"}


@dataclass(frozen=True)
class Zone:
    """Immutable container for a S/R zone.

    Attributes:
        type: -1 support, +1 resistance.
        value: central price of the zone.
        x0: candle index where it becomes active.
        x1: candle index where it stops being active (inclusive).
        count: number of pivots that originated it (strength).
        is_reversal: True if this zone is from polarity (broken S→R or R→S).
    """
    type: int
    value: float
    x0: int
    x1: int
    count: int
    is_reversal: bool = False


class BreakoutAnalyzer:
    """Detects Support/Resistance zones and assigns them "sticky" (anti-jump).

    Pipeline:
        1) Pivot detection.
        2) Value clustering → zone centers.
        3) Active segments (x0..x1) until breakout.
        4) (Optional) Polarity: after a break, S↔R role-reversal until opposite break.
        5) Sticky assignment with hysteresis and up to `max_zones` per side.

    Output columns:
        zone_support_1..N / zone_resistance_1..N / main_support / main_resistance / isPivot
    """

    # Momentum thresholds for breakout confirmation
    RSI_BULLISH_THRESHOLD = 60
    RSI_BEARISH_THRESHOLD = 40

    # ----------------------------- init -----------------------------

    def __init__(
        self,
        df: pd.DataFrame,
        timeframe: str = "5m",
        high_col: str = "High",
        low_col: str = "Low",
        close_col: str = "Close",
        pivot_window: int = 10,
        max_zones: int = 3,
        # Breakouts / robustness
        use_close_only: bool = False,
        confirmation_candles: int = 3,
        band_mode: str = "atr",     # "pct" | "atr"
        band_pct: float = 0.20,
        band_atr_mult: float = 1.0,
        merge_breaks_min_sep: int = 5,
        min_band_abs: float = 1e-12,
        # Anti-jumps
        level_tol_pct: float = 0.05,
        hysteresis_ratio: float = 0.25,
        # Polarity (simple role-reversal)
        enable_polarity: bool = True,
        polarity_cooldown: int = 0,  # Candles to wait after break before checking reversal
        eternal_polarity: bool = False,  # If True, polarity zones extend to end of data
    ):
        # Original index to restore timestamps
        self.original_index = df.index
        self.df = df.copy()
        self.df.reset_index(drop=True, inplace=True)

        # OHLC columns
        self.high_col = high_col
        self.low_col = low_col
        self.close_col = close_col

        # Main parameters
        self.pivot_window = int(pivot_window)
        self.max_zones = int(max_zones)

        tf = (timeframe or "").strip().lower()
        if tf not in _ALLOWED_TF:
            logger.warning(
                f"[BreakoutAnalyzer] timeframe '{timeframe}' not recognized. Using 'unknown'.")
            tf = "unknown"
        self.analysis_timeframe = tf

        self.use_close_only = bool(use_close_only)
        self.confirmation_candles = max(1, int(confirmation_candles))
        self.band_mode = (band_mode or "pct").lower().strip()
        self.band_pct = float(band_pct)
        self.band_atr_mult = float(band_atr_mult)
        self.merge_breaks_min_sep = max(0, int(merge_breaks_min_sep))
        self.min_band_abs = float(min_band_abs)

        self.level_tol_pct = max(0.0, float(level_tol_pct))
        self.hysteresis_ratio = max(0.0, float(hysteresis_ratio))

        self.enable_polarity = bool(enable_polarity)
        self.polarity_cooldown = max(0, int(polarity_cooldown))
        self.eternal_polarity = bool(eternal_polarity)

        # Output columns
        self.df["isPivot"] = 0
        for i in range(1, self.max_zones + 1):
            self.df[f"zone_support_{i}"] = np.nan
            self.df[f"zone_resistance_{i}"] = np.nan
        self.df["main_support"] = np.nan
        self.df["main_resistance"] = np.nan

        # Caches
        self._zones_df: Optional[pd.DataFrame] = None
        self._atr14: Optional[pd.Series] = None

    # ---------------------- adaptive configuration ----------------------

    def _token_config(self, price_level: float) -> Dict[str, float]:
        """Returns configuration by price range (cluster % and edge %)."""
        if price_level < 0.001:
            return {"cluster_zone_pct": 3.0, "break_zone_pct": 2.0, "min_pivots": 2}
        if price_level < 1.0:
            return {"cluster_zone_pct": 2.0, "break_zone_pct": 1.0, "min_pivots": 2}
        if price_level < 100:
            return {"cluster_zone_pct": 1.5, "break_zone_pct": 1.0, "min_pivots": 3}
        return {"cluster_zone_pct": 1.0, "break_zone_pct": 0.8, "min_pivots": 3}

    def _tf_tuning(self) -> Dict[str, float]:
        """Adjustments by timeframe (confirmation and band)."""
        tf = self.analysis_timeframe
        if tf in {"1s", "1m", "5m"}:
            return {"confirm": max(self.confirmation_candles, 3),
                    "band_pct": max(self.band_pct, 0.25),
                    "band_atr_mult": max(self.band_atr_mult, 1.2)}
        if tf in {"15m", "1h"}:
            return {"confirm": max(self.confirmation_candles, 2),
                    "band_pct": max(self.band_pct, 0.20),
                    "band_atr_mult": max(self.band_atr_mult, 1.0)}
        if tf in {"4h", "1d"}:
            return {"confirm": max(self.confirmation_candles, 2),
                    "band_pct": max(self.band_pct, 0.15),
                    "band_atr_mult": max(self.band_atr_mult, 0.9)}
        if tf in {"1w", "1mn"}:
            return {"confirm": max(self.confirmation_candles, 1),
                    "band_pct": max(self.band_pct, 0.10),
                    "band_atr_mult": max(self.band_atr_mult, 0.8)}
        return {"confirm": self.confirmation_candles,
                "band_pct": self.band_pct,
                "band_atr_mult": self.band_atr_mult}

    # --------------------------- lazy indicators ---------------------------

    def _ensure_rsi_macd(self) -> None:
        """Calculates RSI/MACD if missing."""
        if ("rsi" not in self.df.columns) or self.df["rsi"].isna().all():
            try:
                rsi = ta.rsi(self.df[self.close_col], length=14)
                if rsi is not None:
                    self.df["rsi"] = rsi
                elif "RSI_14" in self.df.columns:
                    self.df["rsi"] = self.df["RSI_14"]
            except Exception as e:
                logger.warning(f"RSI calc failed: {e}")

        need_macd = not ({"macd", "macd_signal"} <= set(self.df.columns)) \
            or self.df.get("macd", pd.Series(dtype=float)).isna().all() \
            or self.df.get("macd_signal", pd.Series(dtype=float)).isna().all()
        if need_macd:
            try:
                macd = ta.macd(self.df[self.close_col])
                if macd is not None:
                    self.df["macd"] = macd["MACD_12_26_9"]
                    self.df["macd_signal"] = macd["MACDs_12_26_9"]
            except Exception as e:
                logger.warning(f"MACD calc failed: {e}")

    def _ensure_atr(self) -> None:
        """Calculates ATR(14) if not cached."""
        if self._atr14 is None:
            h, l, c = self.df[self.high_col], self.df[self.low_col], self.df[self.close_col]
            try:
                atr = ta.atr(h, l, c, length=14)
                if atr is not None:
                    self._atr14 = atr
                else:
                    tr = pd.concat([
                        h - l,
                        (h - c.shift()).abs(),
                        (l - c.shift()).abs()
                    ], axis=1).max(axis=1)
                    self._atr14 = tr.rolling(14, min_periods=1).mean()
            except Exception as e:
                logger.warning(f"ATR calc failed: {e}")
                self._atr14 = (h - l).rolling(14, min_periods=1).mean()

    # --------------------------- pivot detection ---------------------------

    def _detect_pivots(self) -> None:
        """Detects pivot points and marks isPivot (ternary: -1/0/+1)."""
        high, low = self.df[self.high_col], self.df[self.low_col]
        w = self.pivot_window

        pivot_highs = high.rolling(2 * w + 1, center=True).max() == high
        pivot_lows = low.rolling(2 * w + 1, center=True).min() == low

        self.df.loc[pivot_highs, "isPivot"] = 1
        self.df.loc[pivot_lows, "isPivot"] = -1
        self.df.loc[pivot_highs & pivot_lows,
                    "isPivot"] = 0  # Conflict → neutral

    # ----------------------------- zone creation -----------------------------

    def _cluster_pivots(
        self,
        values: np.ndarray,
        cluster_pct: float
    ) -> List[Tuple[float, int]]:
        """Groups pivot values by proximity and returns (center, count)."""
        if len(values) == 0:
            return []

        sorted_vals = np.sort(values)
        threshold = cluster_pct / 100.0

        clusters: List[List[float]] = []
        current: List[float] = [sorted_vals[0]]

        for v in sorted_vals[1:]:
            ref = np.mean(current)
            if abs(v - ref) / max(ref, 1e-9) <= threshold:
                current.append(v)
            else:
                clusters.append(current)
                current = [v]
        if current:
            clusters.append(current)

        return [(np.mean(c), len(c)) for c in clusters]

    def _find_break_index(
        self,
        level: float,
        direction: str,
        start: int,
        edge_pct: float,
        confirmation_candles: int = 1
    ) -> int:
        """Finds where the price breaks level+band in direction.

        Args:
            level: zone value (S or R).
            direction: "up" (for R) or "down" (for S).
            start: candle index to start search.
            edge_pct: % band around the level.
            confirmation_candles: consecutive candles for confirmation.

        Returns:
            Last candle index where zone is still active, or len(df)-1.
        """
        n = len(self.df)
        if start >= n:
            return n - 1

        # Dynamic band by mode
        if self.band_mode == "atr":
            self._ensure_atr()
            band_vals = self._atr14 * self.band_atr_mult
        else:  # "pct"
            band_vals = pd.Series([level * edge_pct] * n, index=self.df.index)

        band_vals = band_vals.fillna(
            self.min_band_abs).clip(lower=self.min_band_abs)

        # Prices to check
        prices = self.df[self.close_col] if self.use_close_only else (
            self.df[self.high_col] if direction == "up" else self.df[self.low_col]
        )

        count = 0
        for i in range(start, n):
            band_at_i = float(band_vals.iloc[i])
            price_at_i = float(prices.iloc[i])

            if direction == "up":
                broken = price_at_i > level + band_at_i
            else:
                broken = price_at_i < level - band_at_i

            if broken:
                count += 1
                if count >= confirmation_candles:
                    return max(start, i - confirmation_candles)
            else:
                count = 0

        return n - 1

    def _merge_close_breaks(self, zdf: pd.DataFrame) -> pd.DataFrame:
        """Merges zones that break very close together (clutter reduction)."""
        if zdf.empty or self.merge_breaks_min_sep <= 0:
            return zdf

        # Sort by (x1, type, value)
        zdf = zdf.sort_values(["x1", "type", "value"]).reset_index(drop=True)

        keep: List[bool] = [True]
        for i in range(1, len(zdf)):
            curr, prev = zdf.iloc[i], zdf.iloc[i - 1]
            if (curr["type"] == prev["type"]) and (curr["x1"] - prev["x1"] <= self.merge_breaks_min_sep):
                same_lv = abs(curr["value"] - prev["value"]
                              ) / max(curr["value"], 1e-9) < 0.01
                if same_lv:
                    # Merge: keep previous, extend its x1
                    zdf.at[i - 1, "x1"] = max(prev["x1"], curr["x1"])
                    keep.append(False)
                else:
                    keep.append(True)
            else:
                keep.append(True)

        return zdf[keep].reset_index(drop=True)

    def _build_zones(self) -> List[Zone]:
        """Creates Zone objects from pivots and polarity logic."""
        high, low = self.df[self.high_col], self.df[self.low_col]
        pivot_mask = self.df["isPivot"] != 0
        if not pivot_mask.any():
            logger.info("[BreakoutAnalyzer] No pivots detected.")
            return []

        # Adaptive config
        median_price = self.df[self.close_col].median()
        cfg = self._token_config(median_price)
        tf_cfg = self._tf_tuning()
        cluster_pct = cfg["cluster_zone_pct"]
        edge_pct = (tf_cfg["band_pct"] if self.band_mode ==
                    "pct" else cfg["break_zone_pct"]) / 100.0
        min_pivots = int(cfg["min_pivots"])
        confirmation_candles = int(tf_cfg["confirm"])

        # Separate S/R pivots
        pivot_indices = self.df.index[pivot_mask].to_numpy()
        pivot_types = self.df.loc[pivot_mask, "isPivot"].to_numpy()
        pivot_values = np.where(pivot_types == -1, low.iloc[pivot_indices],
                                high.iloc[pivot_indices]).astype(float)

        support_vals = pivot_values[pivot_types == -1]
        resist_vals = pivot_values[pivot_types == 1]

        # Cluster
        sup_clusters = self._cluster_pivots(support_vals, cluster_pct)
        res_clusters = self._cluster_pivots(resist_vals, cluster_pct)

        # Filter by min_pivots
        sup_clusters = [(v, c) for v, c in sup_clusters if c >= min_pivots]
        res_clusters = [(v, c) for v, c in res_clusters if c >= min_pivots]

        zones: List[Zone] = []

        # Supports
        for center, count in sup_clusters:
            x0 = 0  # Active from start
            x1 = self._find_break_index(
                center, "down", x0, edge_pct, confirmation_candles)
            zones.append(Zone(-1, center, x0, x1, count, False))

        # Resistances
        for center, count in res_clusters:
            x0 = 0
            x1 = self._find_break_index(
                center, "up", x0, edge_pct, confirmation_candles)
            zones.append(Zone(+1, center, x0, x1, count, False))

        # Polarity: role-reversal after breakout (with eternal option!)
        if self.enable_polarity:
            extra: List[Zone] = []
            for z in zones:
                # Start polarity after cooldown
                start_rev = z.x1 + 1 + self.polarity_cooldown

                if start_rev < len(self.df):
                    if self.eternal_polarity:
                        # Extend polarity zones to the end of data (what your boss wants!)
                        y1 = len(self.df) - 1
                    else:
                        # Original behavior: find next breakout
                        if z.type == -1:  # Support broken → becomes Resistance
                            y1 = self._find_break_index(
                                z.value, "up", start_rev, edge_pct, confirmation_candles=1)
                        else:  # Resistance broken → becomes Support
                            y1 = self._find_break_index(
                                z.value, "down", start_rev, edge_pct, confirmation_candles=1)

                        # If no breakout found, extend to end anyway
                        if y1 == -1:
                            y1 = len(self.df) - 1

                    # Create the reversed zone
                    new_type = +1 if z.type == -1 else -1
                    extra.append(Zone(new_type, z.value, start_rev,
                                 y1, z.count, is_reversal=True))

                    if logger.isEnabledFor(logging.DEBUG):
                        end_str = "END" if self.eternal_polarity else str(y1)
                        zone_str = "R" if new_type == 1 else "S"
                        old_str = "S" if z.type == -1 else "R"
                        logger.debug(
                            f"Polarity: {old_str}@{z.value:.6f} broken → now {zone_str} [{start_rev}:{end_str}]")

            zones.extend(extra)

        # Merge and store DF for API
        zdf = pd.DataFrame(
            [z.__dict__ for z in zones],
            columns=["type", "value", "x0", "x1", "count", "is_reversal"]
        )
        zdf = self._merge_close_breaks(zdf)
        self._zones_df = zdf
        return [Zone(**rec) for rec in zdf.to_dict("records")]

    # --------------------------- sticky assignment ---------------------------

    def _same_level(self, a: float, b: float) -> bool:
        """True if `a` and `b` differ < level_tol_pct (same level)."""
        if pd.isna(a) or pd.isna(b):
            return False
        thr = max(a, b) * (self.level_tol_pct / 100.0)
        return abs(float(a) - float(b)) <= thr

    @staticmethod
    def _bucket_zones(zones: List[Zone]) -> Tuple[Dict[int, List[Zone]], Dict[int, List[Zone]]]:
        """Creates buckets by start index (x0) and end (x1) for linear sweep."""
        by_start: Dict[int, List[Zone]] = {}
        by_end: Dict[int, List[Zone]] = {}
        for z in zones:
            by_start.setdefault(z.x0, []).append(z)
            by_end.setdefault(z.x1, []).append(z)
        return by_start, by_end

    @staticmethod
    def _nearest_level(values: np.ndarray, prices: np.ndarray) -> np.ndarray:
        """Nearest non-NaN per row to corresponding price (vectorized)."""
        out = np.full(len(prices), np.nan, dtype=float)
        mask = ~np.isnan(values)
        if mask.any():
            dist = np.where(mask, np.abs(values - prices[:, None]), np.inf)
            idx = dist.argmin(axis=1)
            out = values[np.arange(len(prices)), idx]
        return out

    def _assign_sticky(self, zones: List[Zone]) -> None:
        """Assigns zones with hysteresis using a linear sweep (efficient).

        Logic:
            - Maintains active zones per candle (support/resistance)
            - Sorts candidates by (-count, distance, value)
            - Uses hysteresis to prevent oscillation between similar levels
        """
        n = len(self.df)
        price = self.df[self.close_col].to_numpy()

        by_start, by_end = self._bucket_zones(zones)
        active_sup: List[Zone] = []
        active_res: List[Zone] = []
        prev_sup = [np.nan] * self.max_zones
        prev_res = [np.nan] * self.max_zones

        def rank_candidates(active: List[Zone], i: int) -> List[Dict]:
            """Returns candidates sorted for candle i."""
            if not active:
                return []
            res = [{"value": z.value, "count": z.count,
                    "distance": abs(z.value - price[i])} for z in active]
            res.sort(key=lambda x: (-x["count"], x["distance"], x["value"]))
            return res

        def choose_sticky(prev_level: float, cands: List[Dict], i: int) -> float:
            """Decides whether to keep/change level in current column.

            Logic:
                1. If prev_level is in candidates with same value → KEEP (sticky)
                2. If best candidate doesn't improve distance by hysteresis_ratio → KEEP
                3. Otherwise → SWITCH to best candidate

            This prevents oscillations between similar levels.
            """
            if not cands:
                return np.nan

            # Step 1: Same level? Keep it (strongest stickiness)
            for c in cands:
                if self._same_level(prev_level, c["value"]):
                    return float(c["value"])

            # Step 2: Check if improvement justifies change
            if not pd.isna(prev_level):
                prev_dist = abs(prev_level - price[i])
                best = cands[0]
                if best["distance"] >= (1.0 - self.hysteresis_ratio) * prev_dist:
                    # Not enough improvement, try to keep prev if still active
                    for c in cands:
                        if self._same_level(prev_level, c["value"]):
                            return float(c["value"])

            # Step 3: Switch to best candidate
            return float(cands[0]["value"])

        for i in range(n):
            # Activate zones starting at i
            for z in by_start.get(i, []):
                (active_sup if z.type == -1 else active_res).append(z)
            # Deactivate those that ended at i-1
            for z in by_end.get(i - 1, []):
                try:
                    (active_sup if z.type == -1 else active_res).remove(z)
                except ValueError:
                    pass  # Already removed

            # Rank active candidates at i
            sup_cands = rank_candidates(active_sup, i)
            res_cands = rank_candidates(active_res, i)

            # SUPPORTS
            used: List[float] = []
            for k in range(self.max_zones):
                val = np.nan
                if sup_cands:
                    prev = prev_sup[k]
                    val = choose_sticky(prev, sup_cands, i) if not pd.isna(
                        prev) else float(sup_cands[0]["value"])
                    # Mark as used (avoid duplicates in S1..SN)
                    for c in sup_cands:
                        if self._same_level(val, c["value"]):
                            used.append(c["value"])
                            break
                    sup_cands = [c for c in sup_cands if not any(
                        self._same_level(c["value"], u) for u in used)]
                self.df.at[i, f"zone_support_{k+1}"] = val
                prev_sup[k] = val

            # RESISTANCES
            used = []
            for k in range(self.max_zones):
                val = np.nan
                if res_cands:
                    prev = prev_res[k]
                    val = choose_sticky(prev, res_cands, i) if not pd.isna(
                        prev) else float(res_cands[0]["value"])
                    for c in res_cands:
                        if self._same_level(val, c["value"]):
                            used.append(c["value"])
                            break
                    res_cands = [c for c in res_cands if not any(
                        self._same_level(c["value"], u) for u in used)]
                self.df.at[i, f"zone_resistance_{k+1}"] = val
                prev_res[k] = val

        # Main by proximity (vectorized)
        sup_vals = self.df[[f"zone_support_{k}" for k in range(
            1, self.max_zones + 1)]].to_numpy()
        res_vals = self.df[[f"zone_resistance_{k}" for k in range(
            1, self.max_zones + 1)]].to_numpy()
        self.df["main_support"] = self._nearest_level(sup_vals, price)
        self.df["main_resistance"] = self._nearest_level(res_vals, price)

    # ------------------------------ public API ------------------------------

    def analyze(self) -> pd.DataFrame:
        """Complete pipeline: pivots → zones (+polarity) → sticky assignment → dataframe."""
        self._detect_pivots()
        zones = self._build_zones()
        if zones:
            self._assign_sticky(zones)
        self.df.index = self.original_index
        return self.df
