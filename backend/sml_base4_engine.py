"""
SML BASE-4 SOVEREIGN HARMONIC MATRIX — Python Engine v6.2
══════════════════════════════════════════════════════════════════════════════
Institutional Python port of the SML Base-4 Pine Script v6.2.

Faithfully reproduces:
  • 9-set Base-4 EMA grid  (25 unique periods, zero redundant calculations)
  • Percentile-ranked Compression Index  (self-calibrating, instrument-agnostic)
  • ATR-Adaptive Threshold  (consistent signal frequency across all volatility regimes)
  • Signal Quality Index  (4-pillar composite: compression 40pt, MTF 30pt, volume 15pt, regime 15pt)
  • Multi-Timeframe Convergence  (pandas resample — no external data call needed)
  • Momentum Gradient  (cloud velocity + compression acceleration vector)
  • Full state-machine  (SCANNING → CONVERGENCE → CRITICAL MASS → APEX SINGULARITY → FULL SPECTRUM)

© ScriptMasterLabs. Proprietary.
"""

import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Tuple

logger = logging.getLogger("SMLBase4")


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class ConvergenceState(str, Enum):
    SCANNING        = "SCANNING"
    CONVERGENCE     = "CONVERGENCE"
    CRITICAL_MASS   = "CRITICAL_MASS"
    APEX_SINGULARITY = "APEX_SINGULARITY"
    FULL_SPECTRUM   = "FULL_SPECTRUM"


class CompressionVector(str, Enum):
    TIGHTENING = "TIGHTENING"
    STABLE     = "STABLE"
    EXPANDING  = "EXPANDING"


class CloudMomentum(str, Enum):
    ADVANCING      = "ADVANCING"
    CONSOLIDATING  = "CONSOLIDATING"
    RETREATING     = "RETREATING"


class DirectionalBias(str, Enum):
    NET_LONG_POSTURE   = "NET LONG POSTURE"
    MILD_BULLISH_SKEW  = "MILD BULLISH SKEW"
    MILD_BEARISH_SKEW  = "MILD BEARISH SKEW"
    NET_SHORT_POSTURE  = "NET SHORT POSTURE"


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SetMetrics:
    """Per-set compression metrics."""
    set_id:        int
    name:          str
    spread_pct:    float   # EMA spread as % of price
    score:         float   # 0-100 percentile-ranked compression score
    coiled:        bool    # True if spread < effective_threshold


@dataclass
class SQIBreakdown:
    """Signal Quality Index — 4-pillar breakdown."""
    total:       float   # 0-100 composite
    compression: float   # 0-40 from harmonic_score
    mtf:         float   # 0-30 from MTF alignment
    volume:      float   # 0-15 from volume confirmation
    regime:      float   # 0-15 from volatility regime
    is_prime:          bool    # True if CI >= ci_structural_gate AND total >= prime_threshold
    ci_gate_passed:    bool    # True if harmonic_score >= ci_structural_gate (78)


@dataclass
class MTFResult:
    """Higher-timeframe convergence snapshot."""
    timeframe:     str
    total_coiled:  int
    harmonic_score: float
    converging:    bool


@dataclass
class SMLBase4Result:
    """Complete output from one SMLBase4Engine.compute() call."""
    # ── Timestamp ──────────────────────────────────────────────────────────
    timestamp:         pd.Timestamp

    # ── Per-set metrics ────────────────────────────────────────────────────
    sets:              Dict[int, SetMetrics]

    # ── Aggregate compression ──────────────────────────────────────────────
    total_coiled:      int         # 0-9 sets currently compressed
    avg_spread:        float       # avg spread % across all 9 sets
    harmonic_score:    float       # 0-100 percentile-ranked CI
    anchor_spread_idx: float       # 0-100 percentile of 9-anchor EMA spread
    effective_threshold: float     # current threshold (manual or ATR-adaptive)

    # ── State machine ──────────────────────────────────────────────────────
    state:             ConvergenceState
    bars_in_state:     int         # consecutive bars in current convergence tier
    fired_entry:       bool        # True on the bar the state ENTERED (transition)
    fired_exit:        bool        # True on the bar convergence was released

    # ── Directional context ────────────────────────────────────────────────
    directional_bias:  DirectionalBias
    compression_vector: CompressionVector
    cloud_momentum:    CloudMomentum
    cloud_velocity_5:  float       # 5-bar % change of cloud center
    comp_acceleration: float       # 5-bar change in harmonic_score

    # ── Volatility / volume ────────────────────────────────────────────────
    atr_pct:           float       # ATR percentile 0-100
    vol_regime:        str         # "COMPRESSED" | "NORMAL" | "EXPANDED"
    regime_compressed: bool
    vol_spike:         bool        # volume > vol_ma * vol_mult
    vol_near:          bool        # volume > vol_ma * 0.8

    # ── Key price levels ───────────────────────────────────────────────────
    anchor_ceiling:    float       # highest of all 9 anchor EMAs
    anchor_floor:      float       # lowest of all 9 anchor EMAs
    cloud_center:      float       # avg of fast + anchor EMAs for sets 1, 5, 9

    # ── MTF alignment ──────────────────────────────────────────────────────
    htf1:              Optional[MTFResult]
    htf2:              Optional[MTFResult]
    mtf_aligned:       int         # 0, 1, or 2 higher TFs confirming
    full_mtf_stack:    bool

    # ── SQI ────────────────────────────────────────────────────────────────
    sqi:               SQIBreakdown


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SMLBase4Config:
    # Convergence thresholds
    threshold_pct:     float = 1.0
    use_auto_thresh:   bool  = False
    auto_thresh_mult:  float = 0.5

    # State-machine tier minimums
    min_sets_conv:     int   = 3
    min_sets_crit:     int   = 5
    min_sets_apex:     int   = 7
    min_sets_full:     int   = 9

    # Lookback for percentile calibration
    ci_lookback:       int   = 252

    # ATR
    atr_len:           int   = 14
    atr_lookback:      int   = 100

    # Volume
    vol_ma_len:        int   = 20
    vol_mult:          float = 1.5

    # MTF
    htf1_resample:     str   = "60min"   # pandas resample rule
    htf2_resample:     str   = "240min"
    mtf_min_conv:      int   = 3

    # SQI prime threshold
    sqi_prime_level:   int   = 75

    # Structural coil gate — CI must exceed this before SQI is evaluated.
    # 78 = top-22nd-percentile compression within the instrument's own 252-bar history.
    # Filters the 50-65 chop zone where MM stop hunts are viable.
    # Do NOT conflate with "78% of threshold consumed" — this is a percentile rank.
    ci_structural_gate: int  = 78


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class SMLBase4Engine:
    """
    SML Base-4 Sovereign Harmonic Matrix — Python Engine v6.2.

    Usage
    -----
        engine = SMLBase4Engine(config)
        result = engine.compute(ohlcv_df)

    Parameters
    ----------
    ohlcv_df : pd.DataFrame
        Must have columns: open, high, low, close, volume (lowercase).
        Index must be a DatetimeIndex, timezone-aware preferred.
        At least config.ci_lookback + 108 rows required for full calibration.
    """

    # 25 unique EMA periods across all 9 sets (deduplicated from original 36)
    _EMA_PERIODS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 16, 20, 24, 28, 32, 36, 40, 48, 56, 60, 64, 72, 84, 96, 108]

    # Set definitions: set_id → (e_a, e_b, e_c, e_d) periods
    _SETS: Dict[int, Tuple[int, int, int, int]] = {
        1: (1,  4,   8,  12),
        2: (2,  8,  16,  24),
        3: (3, 12,  24,  36),
        4: (4, 16,  32,  48),
        5: (5, 20,  40,  60),
        6: (6, 24,  48,  72),
        7: (7, 28,  56,  84),
        8: (8, 32,  64,  96),
        9: (9, 36,  72, 108),
    }

    _SET_NAMES = {
        1: "MICRO", 2: "ULTRA-FAST", 3: "FAST-SWING", 4: "SWING",
        5: "CORE",  6: "MACRO",      7: "STRUCTURAL",  8: "DEEP-WAVE",
        9: "SOVEREIGN",
    }

    def __init__(self, config: Optional[SMLBase4Config] = None):
        self.cfg = config or SMLBase4Config()
        self._prev_coiled:      int   = 0
        self._bars_in_conv:     int   = 0
        self._prev_state:       ConvergenceState = ConvergenceState.SCANNING

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────

    def compute(self, df: pd.DataFrame) -> SMLBase4Result:
        """
        Run the full SML Base-4 computation on the provided OHLCV dataframe.

        Returns the result for the LAST bar in the dataframe (most recent).
        Pass at least ci_lookback + 200 rows for accurate percentile calibration.
        """
        self._validate_df(df)

        ema_cache   = self._compute_ema_cache(df)
        spreads     = self._compute_spreads(df, ema_cache)
        atr_data    = self._compute_atr(df)
        vol_data    = self._compute_volume(df)
        threshold   = self._effective_threshold(atr_data, df)
        ci_scores   = self._compute_ci_scores(spreads, threshold)
        coil_flags  = self._compute_coil_flags(spreads, threshold)
        total_coiled = int(coil_flags.iloc[-1].sum())
        avg_spread  = float(spreads.mean(axis=1).iloc[-1])
        harmonic_score = float(ci_scores["harmonic_score"].iloc[-1])
        anchor_idx  = self._compute_anchor_spread_index(df, ema_cache)
        cloud_center_series = self._compute_cloud_center(ema_cache)
        momentum    = self._compute_momentum(harmonic_score, ci_scores, cloud_center_series)
        bias        = self._compute_bias(df, ema_cache)
        state_data  = self._compute_state(total_coiled, atr_data, vol_data)
        htf1, htf2  = self._compute_mtf(df)
        sqi         = self._compute_sqi(harmonic_score, atr_data, vol_data, state_data["atr_pct"], htf1, htf2)

        # Per-set metrics
        sets = {}
        for sid in range(1, 10):
            sp = float(spreads[f"sp{sid}"].iloc[-1])
            sc = float(ci_scores[f"sc{sid}"].iloc[-1])
            sets[sid] = SetMetrics(
                set_id=sid, name=self._SET_NAMES[sid],
                spread_pct=sp, score=sc,
                coiled=bool(coil_flags[f"coil{sid}"].iloc[-1]),
            )

        anchor_ceiling = float(max(
            ema_cache[f"e{p}"].iloc[-1]
            for p in [12, 24, 36, 48, 60, 72, 84, 96, 108]
        ))
        anchor_floor = float(min(
            ema_cache[f"e{p}"].iloc[-1]
            for p in [12, 24, 36, 48, 60, 72, 84, 96, 108]
        ))

        return SMLBase4Result(
            timestamp          = df.index[-1],
            sets               = sets,
            total_coiled       = total_coiled,
            avg_spread         = avg_spread,
            harmonic_score     = harmonic_score,
            anchor_spread_idx  = float(anchor_idx.iloc[-1]),
            effective_threshold = float(threshold.iloc[-1]),
            state              = state_data["state"],
            bars_in_state      = state_data["bars_in_state"],
            fired_entry        = state_data["fired_entry"],
            fired_exit         = state_data["fired_exit"],
            directional_bias   = bias,
            compression_vector = momentum["vector"],
            cloud_momentum     = momentum["cloud_momentum"],
            cloud_velocity_5   = momentum["cloud_vel_5"],
            comp_acceleration  = momentum["comp_accel"],
            atr_pct            = float(state_data["atr_pct"]),
            vol_regime         = state_data["vol_regime"],
            regime_compressed  = state_data["regime_compressed"],
            vol_spike          = bool(vol_data["spike"].iloc[-1]),
            vol_near           = bool(vol_data["near"].iloc[-1]),
            anchor_ceiling     = anchor_ceiling,
            anchor_floor       = anchor_floor,
            cloud_center       = float(cloud_center_series.iloc[-1]),
            htf1               = htf1,
            htf2               = htf2,
            mtf_aligned        = (1 if (htf1 and htf1.converging) else 0) + (1 if (htf2 and htf2.converging) else 0),
            full_mtf_stack     = (htf1 is not None and htf1.converging) and (htf2 is not None and htf2.converging),
            sqi                = sqi,
        )

    def summary(self, result: SMLBase4Result) -> str:
        """One-line institutional summary for logging / Discord."""
        state_label = result.state.value.replace("_", " ")
        mtf_tag = " | MTF STACK" if result.full_mtf_stack else (f" | MTF {result.mtf_aligned}/2" if result.mtf_aligned else "")
        prime_tag = " ★ PRIME" if result.sqi.is_prime else ""
        return (
            f"[SML B4] {state_label} | "
            f"SETS: {result.total_coiled}/9 | "
            f"CI: {result.harmonic_score:.0f} | "
            f"SQI: {result.sqi.total:.0f}{prime_tag} | "
            f"THR: {result.effective_threshold:.2f}% | "
            f"REGIME: {result.vol_regime}"
            f"{mtf_tag}"
        )

    # ─────────────────────────────────────────────────────────────────────
    # INTERNAL COMPUTATIONS
    # ─────────────────────────────────────────────────────────────────────

    def _validate_df(self, df: pd.DataFrame) -> None:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"SMLBase4Engine: missing columns: {missing}")
        if len(df) < self.cfg.ci_lookback + 108:
            logger.warning(
                "SMLBase4Engine: only %d rows — CI percentile calibration requires %d+. "
                "Results may be inaccurate.",
                len(df), self.cfg.ci_lookback + 108,
            )

    def _ema(self, series: pd.Series, period: int) -> pd.Series:
        """Standard EMA using pandas ewm (matches Pine Script ta.ema)."""
        return series.ewm(span=period, adjust=False).mean()

    def _compute_ema_cache(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Compute all 25 unique EMA periods once — zero redundant calls."""
        close = df["close"]
        return {f"e{p}": self._ema(close, p) for p in self._EMA_PERIODS}

    def _set_spread(self, df: pd.DataFrame, ema_cache: Dict[str, pd.Series], sid: int) -> pd.Series:
        """
        Spread = (max(ea,eb,ec,ed) - min(ea,eb,ec,ed)) / close * 100.
        Exact Python port of Pine Script get_spread().
        """
        pa, pb, pc, pd_ = self._SETS[sid]
        ea = ema_cache[f"e{pa}"]
        eb = ema_cache[f"e{pb}"]
        ec = ema_cache[f"e{pc}"]
        ed = ema_cache[f"e{pd_}"]
        hi = pd.concat([ea, eb, ec, ed], axis=1).max(axis=1)
        lo = pd.concat([ea, eb, ec, ed], axis=1).min(axis=1)
        return ((hi - lo) / df["close"]) * 100.0

    def _compute_spreads(self, df: pd.DataFrame, ema_cache: Dict[str, pd.Series]) -> pd.DataFrame:
        return pd.DataFrame({f"sp{sid}": self._set_spread(df, ema_cache, sid) for sid in range(1, 10)})

    def _compute_atr(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        high, low, close_prev = df["high"], df["low"], df["close"].shift(1)
        tr = pd.concat([
            high - low,
            (high - close_prev).abs(),
            (low  - close_prev).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(span=self.cfg.atr_len, adjust=False).mean()
        atr_hi = atr.rolling(self.cfg.atr_lookback, min_periods=1).max()
        atr_lo = atr.rolling(self.cfg.atr_lookback, min_periods=1).min()
        atr_pct = ((atr - atr_lo) / (atr_hi - atr_lo).replace(0, np.nan)).fillna(0.5) * 100.0
        return {"atr": atr, "atr_hi": atr_hi, "atr_lo": atr_lo, "atr_pct": atr_pct}

    def _compute_volume(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        vol_ma = df["volume"].rolling(self.cfg.vol_ma_len, min_periods=1).mean()
        spike = df["volume"] > vol_ma * self.cfg.vol_mult
        near  = df["volume"] > vol_ma * 0.8
        return {"vol_ma": vol_ma, "spike": spike, "near": near}

    def _effective_threshold(self, atr_data: Dict[str, pd.Series], df: pd.DataFrame) -> pd.Series:
        """
        Manual mode: constant threshold_pct series.
        Auto mode:   ATR as % of price * sensitivity — matches Pine Script adaptive threshold.
        """
        if self.cfg.use_auto_thresh:
            raw = (atr_data["atr"] / df["close"]) * 100.0 * self.cfg.auto_thresh_mult
            return raw.clip(lower=0.1)
        return pd.Series(self.cfg.threshold_pct, index=df.index)

    def _percentile_rank(self, series: pd.Series, lookback: int) -> pd.Series:
        """
        Rolling inverse-percentile rank: high rank = more compressed.
        score = 1 - (value - rolling_min) / (rolling_max - rolling_min)
        Matches the Pine Script v6.2 self-calibrating CI formula exactly.
        """
        rolling_hi = series.rolling(lookback, min_periods=1).max()
        rolling_lo = series.rolling(lookback, min_periods=1).min()
        span = (rolling_hi - rolling_lo).replace(0, np.nan)
        score = (1.0 - (series - rolling_lo) / span).fillna(0.5) * 100.0
        return score.clip(0.0, 100.0)

    def _compute_ci_scores(self, spreads: pd.DataFrame, threshold: pd.Series) -> pd.DataFrame:
        """
        Compute per-set scores and the overall harmonic_score.
        All percentile-ranked over cfg.ci_lookback bars — instrument-agnostic.
        """
        lb = self.cfg.ci_lookback
        avg = spreads.mean(axis=1)
        result = {f"sc{sid}": self._percentile_rank(spreads[f"sp{sid}"], lb) for sid in range(1, 10)}
        result["harmonic_score"] = self._percentile_rank(avg, lb)
        return pd.DataFrame(result)

    def _compute_coil_flags(self, spreads: pd.DataFrame, threshold: pd.Series) -> pd.DataFrame:
        return pd.DataFrame({
            f"coil{sid}": spreads[f"sp{sid}"] < threshold
            for sid in range(1, 10)
        })

    def _compute_anchor_spread_index(self, df: pd.DataFrame, ema_cache: Dict[str, pd.Series]) -> pd.Series:
        """All 9 anchor EMAs (12,24,36,48,60,72,84,96,108) spread — percentile ranked."""
        anchors = pd.concat([ema_cache[f"e{p}"] for p in [12,24,36,48,60,72,84,96,108]], axis=1)
        hi = anchors.max(axis=1)
        lo = anchors.min(axis=1)
        raw = ((hi - lo) / df["close"]) * 100.0
        return self._percentile_rank(raw, self.cfg.ci_lookback)

    def _compute_cloud_center(self, ema_cache: Dict[str, pd.Series]) -> pd.Series:
        """Avg of fast + anchor EMAs for sets 1, 5, 9 — matches Pine Script cloud_center."""
        return (ema_cache["e1"] + ema_cache["e12"] + ema_cache["e5"] + ema_cache["e60"] + ema_cache["e9"] + ema_cache["e108"]) / 6.0

    def _compute_momentum(self, harmonic_score_now: float, ci_scores: pd.DataFrame, cloud_center: pd.Series) -> Dict:
        """Cloud velocity and compression acceleration vector."""
        if len(cloud_center) > 5 and cloud_center.iloc[-6] > 0:
            cloud_vel_5 = (cloud_center.iloc[-1] - cloud_center.iloc[-6]) / cloud_center.iloc[-6] * 100.0
        else:
            cloud_vel_5 = 0.0

        if len(ci_scores) > 5:
            comp_accel = ci_scores["harmonic_score"].iloc[-1] - ci_scores["harmonic_score"].iloc[-6]
        else:
            comp_accel = 0.0

        if abs(cloud_vel_5) < 0.05:
            cloud_mom = CloudMomentum.CONSOLIDATING
        elif cloud_vel_5 > 0:
            cloud_mom = CloudMomentum.ADVANCING
        else:
            cloud_mom = CloudMomentum.RETREATING

        if comp_accel > 3.0:
            vector = CompressionVector.TIGHTENING
        elif comp_accel < -3.0:
            vector = CompressionVector.EXPANDING
        else:
            vector = CompressionVector.STABLE

        return {"cloud_vel_5": cloud_vel_5, "comp_accel": comp_accel, "cloud_momentum": cloud_mom, "vector": vector}

    def _compute_bias(self, df: pd.DataFrame, ema_cache: Dict[str, pd.Series]) -> DirectionalBias:
        """Directional posture: price vs anchor EMAs of sets 1, 5, 9."""
        last_close = df["close"].iloc[-1]
        above = sum([
            last_close > ema_cache["e12"].iloc[-1],   # set 1 anchor
            last_close > ema_cache["e60"].iloc[-1],   # set 5 anchor
            last_close > ema_cache["e108"].iloc[-1],  # set 9 anchor
        ])
        if above == 3:
            return DirectionalBias.NET_LONG_POSTURE
        if above == 2:
            return DirectionalBias.MILD_BULLISH_SKEW
        if above == 1:
            return DirectionalBias.MILD_BEARISH_SKEW
        return DirectionalBias.NET_SHORT_POSTURE

    def _compute_state(self, total_coiled: int, atr_data: Dict, vol_data: Dict) -> Dict:
        """State machine — mirrors Pine Script state_convergence/critical/apex/full logic."""
        cfg = self.cfg
        atr_pct_now = float(atr_data["atr_pct"].iloc[-1])
        vol_regime = "COMPRESSED" if atr_pct_now < 25.0 else ("EXPANDED" if atr_pct_now > 75.0 else "NORMAL")
        regime_compressed = atr_pct_now < 25.0

        # Determine current state tier
        if total_coiled >= cfg.min_sets_full:
            state = ConvergenceState.FULL_SPECTRUM
        elif total_coiled >= cfg.min_sets_apex:
            state = ConvergenceState.APEX_SINGULARITY
        elif total_coiled >= cfg.min_sets_crit:
            state = ConvergenceState.CRITICAL_MASS
        elif total_coiled >= cfg.min_sets_conv:
            state = ConvergenceState.CONVERGENCE
        else:
            state = ConvergenceState.SCANNING

        # State transition detection
        prev_in_conv = self._prev_coiled >= cfg.min_sets_conv
        now_in_conv  = total_coiled      >= cfg.min_sets_conv
        fired_entry  = now_in_conv  and not prev_in_conv
        fired_exit   = not now_in_conv and prev_in_conv

        # Bars-in-state counter
        if now_in_conv:
            self._bars_in_conv += 1
        else:
            self._bars_in_conv = 0

        self._prev_coiled = total_coiled
        self._prev_state  = state

        return {
            "state":             state,
            "bars_in_state":     self._bars_in_conv,
            "fired_entry":       fired_entry,
            "fired_exit":        fired_exit,
            "atr_pct":           atr_pct_now,
            "vol_regime":        vol_regime,
            "regime_compressed": regime_compressed,
        }

    def _compute_mtf(self, df: pd.DataFrame) -> Tuple[Optional[MTFResult], Optional[MTFResult]]:
        """
        Multi-timeframe convergence via pandas resample.

        Resamples the base OHLCV data to HTF1 and HTF2, then runs the same
        compression engine on each resampled series. This is the Python
        equivalent of Pine Script's request.security() calls.

        The resampled engine uses the SAME config (threshold, ci_lookback)
        as the base-TF engine, which means the adaptive threshold also
        scales to each TF's own ATR — matching Pine Script behavior exactly.
        """
        htf1 = self._run_htf(df, self.cfg.htf1_resample)
        htf2 = self._run_htf(df, self.cfg.htf2_resample)
        return htf1, htf2

    def _run_htf(self, df: pd.DataFrame, rule: str) -> Optional[MTFResult]:
        """Resample + compute Base-4 metrics for one higher timeframe."""
        try:
            htf_df = df.resample(rule).agg({
                "open":   "first",
                "high":   "max",
                "low":    "min",
                "close":  "last",
                "volume": "sum",
            }).dropna()

            if len(htf_df) < 60:
                logger.debug("SMLBase4 HTF %s: only %d bars — skipping", rule, len(htf_df))
                return None

            ema_cache = self._compute_ema_cache(htf_df)
            spreads   = self._compute_spreads(htf_df, ema_cache)
            atr_data  = self._compute_atr(htf_df)
            threshold = self._effective_threshold(atr_data, htf_df)
            ci_scores = self._compute_ci_scores(spreads, threshold)
            coil_flags = self._compute_coil_flags(spreads, threshold)

            total_coiled    = int(coil_flags.iloc[-1].sum())
            harmonic_score  = float(ci_scores["harmonic_score"].iloc[-1])
            converging      = total_coiled >= self.cfg.mtf_min_conv

            return MTFResult(
                timeframe=rule,
                total_coiled=total_coiled,
                harmonic_score=harmonic_score,
                converging=converging,
            )
        except Exception as exc:
            logger.warning("SMLBase4 HTF %s: compute failed — %s", rule, exc)
            return None

    def _compute_sqi(
        self,
        harmonic_score: float,
        atr_data:       Dict,
        vol_data:       Dict,
        atr_pct:        float,
        htf1:           Optional[MTFResult],
        htf2:           Optional[MTFResult],
    ) -> SQIBreakdown:
        """
        Signal Quality Index — four-pillar composite 0-100.

        Pillar 1 — Compression  (40 pts): harmonic_score * 0.40
        Pillar 2 — MTF Align    (30 pts): 15 pts per confirming higher TF
        Pillar 3 — Volume Conf  (15 pts): spike=15, near=7.5, else=0
        Pillar 4 — Regime Grade (15 pts): compressed=15, normal_low=7.5, else=0
        """
        p1 = harmonic_score * 0.40
        p2 = (15.0 if (htf1 and htf1.converging) else 0.0) + (15.0 if (htf2 and htf2.converging) else 0.0)
        p3 = 15.0 if bool(vol_data["spike"].iloc[-1]) else (7.5 if bool(vol_data["near"].iloc[-1]) else 0.0)
        p4 = 15.0 if atr_pct < 25.0 else (7.5 if atr_pct < 50.0 else 0.0)
        total = p1 + p2 + p3 + p4

        # Dual-gate: CI structural gate must pass before SQI prime is declared.
        # CI >= 78 (top-22nd-pct compression) AND SQI >= 75 (4-pillar confirmation).
        ci_gate_passed = harmonic_score >= self.cfg.ci_structural_gate
        return SQIBreakdown(
            total=round(total, 2),
            compression=round(p1, 2),
            mtf=round(p2, 2),
            volume=round(p3, 2),
            regime=round(p4, 2),
            is_prime=ci_gate_passed and total >= self.cfg.sqi_prime_level,
            ci_gate_passed=ci_gate_passed,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ORACLE BRIDGE — integrates SML B4 into OracleEngine score
# ─────────────────────────────────────────────────────────────────────────────

def sml_base4_oracle_contribution(result: SMLBase4Result, weight: float = 25.0) -> float:
    """
    Map SML Base-4 SQI onto a score contribution for OracleEngine.

    weight=25.0 means SML B4 contributes up to 25 points to the Oracle total.
    Oracle uses 0-100 scale; this function returns a partial score component.

    Logic mirrors oracle_engine.py IGNITION_THRESHOLD=82 / BULL_THRESHOLD=60.
    """
    sqi = result.sqi.total
    if result.state == ConvergenceState.FULL_SPECTRUM and result.full_mtf_stack:
        return weight                        # maximum contribution
    if result.state == ConvergenceState.APEX_SINGULARITY:
        return weight * (sqi / 100.0) * 0.9
    if result.state == ConvergenceState.CRITICAL_MASS:
        return weight * (sqi / 100.0) * 0.7
    if result.state == ConvergenceState.CONVERGENCE:
        return weight * (sqi / 100.0) * 0.5
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST (run as: python sml_base4_engine.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import yfinance as yf

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("=" * 72)
    print("SML Base-4 Sovereign Harmonic Matrix — Engine v6.2 Validation")
    print("=" * 72)

    for ticker in ["SPY", "IWM", "QQQ"]:
        print(f"\n[{ticker}] Fetching 2-year 1H data...")
        raw = yf.download(ticker, period="2y", interval="1h", auto_adjust=True, progress=False)
        # yfinance >= 0.2 returns MultiIndex columns — flatten to (open, high, low, close, volume)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0].lower() for c in raw.columns]
        else:
            raw.columns = [c.lower() for c in raw.columns]
        raw.index = pd.to_datetime(raw.index)

        engine = SMLBase4Engine(SMLBase4Config(
            threshold_pct=1.0,
            use_auto_thresh=False,
            htf1_resample="4h",
            htf2_resample="1D",
        ))
        result = engine.compute(raw)
        print(engine.summary(result))
        print(f"  State:       {result.state.value}")
        print(f"  Sets coiled: {result.total_coiled}/9")
        print(f"  CI score:    {result.harmonic_score:.1f}")
        print(f"  SQI:         {result.sqi.total:.1f} {'★ PRIME' if result.sqi.is_prime else ''}")
        print(f"  Bias:        {result.directional_bias.value}")
        print(f"  Vector:      {result.compression_vector.value}")
        print(f"  Cloud Vel:   {result.cloud_velocity_5:+.3f}%")
        print(f"  ATR%:        {result.atr_pct:.1f}% ({result.vol_regime})")
        print(f"  MTF Stack:   {'FULL' if result.full_mtf_stack else f'{result.mtf_aligned}/2'}")
        if result.htf1:
            print(f"    HTF1 ({result.htf1.timeframe}): {result.htf1.total_coiled}/9 sets | CI {result.htf1.harmonic_score:.1f}")
        if result.htf2:
            print(f"    HTF2 ({result.htf2.timeframe}): {result.htf2.total_coiled}/9 sets | CI {result.htf2.harmonic_score:.1f}")
        print(f"  Oracle contribution: {sml_base4_oracle_contribution(result):.1f} / 25.0 pts")
