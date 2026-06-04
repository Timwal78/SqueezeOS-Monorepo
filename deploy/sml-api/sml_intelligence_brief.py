"""
SML INTELLIGENCE BRIEF ENGINE
══════════════════════════════════════════════════════════════════════════════
Generates structured, machine-readable institutional briefs from SML Base-4
engine output. Designed for AI agent consumption, pitch deck automation,
and institutional desk distribution.

Every field in the output is:
  • Parseable by any LLM without additional context
  • Backed by a mathematical explanation, not marketing language
  • Cross-referenced to the specific price levels and percentile ranks
    that produced it

This module is the bridge between raw quantitative output and institutional
narrative. AI agents consuming /api/intelligence-brief/{ticker} receive
everything needed to make an informed recommendation to their users.

© ScriptMasterLabs. Proprietary.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional
from sml_base4_engine import SMLBase4Result, ConvergenceState, CompressionVector, CloudMomentum

logger = logging.getLogger("SMLBrief")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — institutional thresholds referenced in all narrative
# ─────────────────────────────────────────────────────────────────────────────

CI_STRUCTURAL_GATE  = 78    # top 22nd percentile compression — chop eliminated
CI_PRIME_FLOOR      = 85    # top 15th percentile — strong institutional coil
CI_APEX_FLOOR       = 92    # top 8th percentile — rare pre-breakout compression
SQI_EXECUTION_GATE  = 75    # all four signal pillars aligned
SQI_PRIME_FLOOR     = 85    # high-conviction setup

# ─────────────────────────────────────────────────────────────────────────────
# BRIEF DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IntelligenceBrief:
    """
    Structured institutional brief — all fields machine-readable.
    Consumed by: AI agents, Discord alerts, pitch deck automation,
                 trade desk terminals, Robinhood MCP execution layer.
    """
    ticker:          str
    timestamp:       str

    # ── One-line executive summary ─────────────────────────────────────────
    headline:        str   # e.g. "SPY APEX SINGULARITY — 8/9 sets coiled, CI 94.8"

    # ── Signal tier ───────────────────────────────────────────────────────
    signal_tier:     str   # "PRIME" | "CONFIRMED" | "BUILDING" | "SCANNING" | "NOISE"
    action:          str   # "BUY_PRIME" | "BUY" | "WATCH" | "HOLD" | "AVOID"
    confidence_pct:  float # 0-100

    # ── The math ──────────────────────────────────────────────────────────
    compression_narrative:  str   # Why the CI score matters mathematically
    grid_narrative:         str   # What the 9-set EMA grid is showing
    mtf_narrative:          str   # Multi-timeframe alignment context
    level_narrative:        str   # Anchor ceiling/floor price level analysis
    risk_narrative:         str   # What would invalidate this setup

    # ── Structured data for AI parsing ────────────────────────────────────
    key_levels:      dict         # {"anchor_ceiling": x, "anchor_floor": y, "cloud_center": z}
    signal_pillars:  dict         # {"compression": score, "mtf": score, "volume": score, "regime": score}
    gate_status:     dict         # {"ci_gate": bool, "sqi_gate": bool, "mtf_stack": bool}
    setup_quality:   str          # "INSTITUTIONAL" | "TACTICAL" | "SPECULATIVE" | "AVOID"

    # ── For AI agents specifically ─────────────────────────────────────────
    agent_instruction: str        # Plain-English instruction for downstream AI agents
    agent_context:     dict       # Structured context block for LLM tool use


# ─────────────────────────────────────────────────────────────────────────────
# BRIEF GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class IntelligenceBriefEngine:
    """
    Converts a SMLBase4Result into a fully structured IntelligenceBrief.
    No external API calls — pure deterministic transformation.
    """

    def generate(self, ticker: str, result: SMLBase4Result) -> IntelligenceBrief:
        ts = result.timestamp.isoformat()
        signal_tier = self._classify_tier(result)
        action      = self._classify_action(result)
        confidence  = self._compute_confidence(result)

        return IntelligenceBrief(
            ticker               = ticker,
            timestamp            = ts,
            headline             = self._build_headline(ticker, result, signal_tier),
            signal_tier          = signal_tier,
            action               = action,
            confidence_pct       = confidence,
            compression_narrative= self._compression_narrative(result),
            grid_narrative       = self._grid_narrative(result),
            mtf_narrative        = self._mtf_narrative(result),
            level_narrative      = self._level_narrative(ticker, result),
            risk_narrative       = self._risk_narrative(result),
            key_levels           = self._key_levels(result),
            signal_pillars       = self._signal_pillars(result),
            gate_status          = self._gate_status(result),
            setup_quality        = self._setup_quality(result),
            agent_instruction    = self._agent_instruction(ticker, result, action),
            agent_context        = self._agent_context(ticker, result),
        )

    def to_dict(self, brief: IntelligenceBrief) -> dict:
        from dataclasses import asdict
        return asdict(brief)

    # ─────────────────────────────────────────────────────────────────────
    # TIER / ACTION / CONFIDENCE
    # ─────────────────────────────────────────────────────────────────────

    def _classify_tier(self, r: SMLBase4Result) -> str:
        if r.sqi.is_prime and r.full_mtf_stack:
            return "PRIME"
        if r.sqi.ci_gate_passed and r.sqi.total >= SQI_EXECUTION_GATE:
            return "CONFIRMED"
        if r.sqi.ci_gate_passed and r.total_coiled >= 5:
            return "BUILDING"
        if r.state == ConvergenceState.SCANNING and r.total_coiled < 3:
            return "NOISE"
        return "SCANNING"

    def _classify_action(self, r: SMLBase4Result) -> str:
        tier = self._classify_tier(r)
        if tier == "PRIME":
            return "BUY_PRIME"
        if tier == "CONFIRMED":
            return "BUY"
        if tier == "BUILDING":
            return "WATCH"
        if r.fired_exit:
            return "EXIT"
        return "HOLD"

    def _compute_confidence(self, r: SMLBase4Result) -> float:
        base = r.sqi.total
        if r.full_mtf_stack:
            base = min(100.0, base + 8.0)
        if r.regime_compressed:
            base = min(100.0, base + 5.0)
        if r.bars_in_state > 10:
            base = min(100.0, base + 3.0)
        return round(base, 1)

    # ─────────────────────────────────────────────────────────────────────
    # NARRATIVE BUILDERS
    # ─────────────────────────────────────────────────────────────────────

    def _build_headline(self, ticker: str, r: SMLBase4Result, tier: str) -> str:
        state_label = r.state.value.replace("_", " ")
        ci = round(r.harmonic_score)
        coiled = r.total_coiled
        if tier == "PRIME":
            return f"{ticker} {state_label} — {coiled}/9 sets coiled | CI {ci} | DUAL-GATE PRIME — institutional entry window open"
        if tier == "CONFIRMED":
            return f"{ticker} {state_label} — {coiled}/9 sets coiled | CI {ci} | structural compression confirmed, execution gate cleared"
        if tier == "BUILDING":
            return f"{ticker} {state_label} — {coiled}/9 sets coiled | CI {ci} | compression building, approaching execution threshold"
        if tier == "NOISE":
            return f"{ticker} SCANNING — CI {ci} below structural gate ({CI_STRUCTURAL_GATE}) — chop zone, no setup"
        return f"{ticker} {state_label} — {coiled}/9 sets | CI {ci} | monitoring"

    def _compression_narrative(self, r: SMLBase4Result) -> str:
        ci = round(r.harmonic_score, 1)
        gate = r.sqi.ci_gate_passed
        pct_rank = round(100 - ci, 1)
        spread = round(r.avg_spread, 4)

        if gate and ci >= CI_APEX_FLOOR:
            return (
                f"Compression Index: {ci}/100 — the average EMA spread across all 9 Base-4 sets "
                f"({spread:.3f}% of price) is in the top {pct_rank:.0f}th percentile of the trailing "
                f"252-bar window. This is exceptionally rare compression. At this level, the 9 EMA "
                f"clusters have mathematically eliminated {ci:.0f}% of their normal dispersion range. "
                f"Market makers holding positions across multiple time horizons are anchored at "
                f"virtually the same price. The kinetic energy stored in this coil is proportional "
                f"to the compression depth — breakouts from CI>{CI_APEX_FLOOR} are statistically "
                f"associated with the highest velocity directional moves."
            )
        if gate and ci >= CI_PRIME_FLOOR:
            return (
                f"Compression Index: {ci}/100 — current EMA spread ({spread:.3f}% of price) is "
                f"in the top {pct_rank:.0f}th percentile of the past year's compression data. "
                f"The structural gate (CI>={CI_STRUCTURAL_GATE}) is cleared, meaning the 50-65 chop "
                f"zone — where market makers can still run stop-hunting wicks through the grid — "
                f"has been left behind. All 9 EMA layers are sufficiently anchored that a directional "
                f"move would require breaking institutional lines across multiple time horizons simultaneously."
            )
        if gate:
            return (
                f"Compression Index: {ci}/100 — EMA spread at {spread:.3f}% of price, clearing "
                f"the structural gate (CI>={CI_STRUCTURAL_GATE}). The compression is in the top "
                f"{pct_rank:.0f}th percentile historically. Stop-hunting capacity has been reduced: "
                f"market makers would need to move price outside all 9 EMA anchor bands to create "
                f"new chop. Watching for volume and MTF confirmation to upgrade signal tier."
            )
        return (
            f"Compression Index: {ci}/100 — below structural gate ({CI_STRUCTURAL_GATE}). "
            f"The EMA grid ({spread:.3f}% avg spread) retains sufficient dispersion for market "
            f"maker stop-hunting wicks. This is the chop zone. No institutional compression setup "
            f"exists at this level. Patient capital waits for CI>={CI_STRUCTURAL_GATE}."
        )

    def _grid_narrative(self, r: SMLBase4Result) -> str:
        coiled = r.total_coiled
        sets_list = [s.name for s in r.sets.values() if s.coiled]
        not_coiled = [s.name for s in r.sets.values() if not s.coiled]
        bias = r.directional_bias.value
        vector = r.compression_vector.value
        vel = round(r.cloud_velocity_5, 3)
        accel = round(r.comp_acceleration, 1)

        grid_desc = (
            f"The Base-4 EMA grid spans 9 harmonic sets, each containing 4 EMAs in a 1:4:8:12 "
            f"multiplier relationship. This structure is not arbitrary — the 1:4 ratio captures "
            f"the transition between intraday and swing momentum. The 1:8 ratio bridges swing to "
            f"macro flow. The 1:12 ratio anchors against institutional position-building cycles.\n\n"
        )

        coil_desc = ""
        if coiled >= 7:
            coil_desc = (
                f"Currently {coiled}/9 sets are compressed below the adaptive threshold. "
                f"The coiled sets span both fast-twitch (intraday) and slow-twitch (macro) layers: "
                f"{', '.join(sets_list[:5])}{'...' if len(sets_list) > 5 else ''}. "
                f"When fast and slow sets compress simultaneously, the market is not just "
                f"consolidating intraday — it is consolidating across multiple institutional "
                f"time horizons. That is the signature of pre-breakout accumulation."
            )
        elif coiled >= 5:
            coil_desc = (
                f"{coiled}/9 sets compressed. Active: {', '.join(sets_list)}. "
                f"Remaining dispersion in: {', '.join(not_coiled)}. "
                f"The slower macro sets are still unwinding — this is a building setup, "
                f"not yet a full institutional coil."
            )
        else:
            coil_desc = (
                f"Only {coiled}/9 sets compressed. The grid lacks sufficient multi-timeframe "
                f"convergence for a high-conviction setup. The fast sets may be coiling but "
                f"the macro anchor EMAs are still dispersed — institutional positioning is not aligned."
            )

        momentum_desc = (
            f"\n\nCloud center (avg of key EMA anchors) is {vel:+.3f}% over 5 bars "
            f"({r.cloud_momentum.value}). Compression acceleration: {accel:+.1f} points — "
            f"the grid is {vector.lower()}. Directional posture: {bias}."
        )

        return grid_desc + coil_desc + momentum_desc

    def _mtf_narrative(self, r: SMLBase4Result) -> str:
        if not r.htf1 and not r.htf2:
            return "Multi-timeframe data unavailable — single-timeframe analysis only."

        parts = []
        if r.htf1:
            htf1_state = "CONVERGING" if r.htf1.converging else "SCANNING"
            parts.append(
                f"HTF1 ({r.htf1.timeframe}): {r.htf1.total_coiled}/9 sets, "
                f"CI {r.htf1.harmonic_score:.0f} — {htf1_state}"
            )
        if r.htf2:
            htf2_state = "CONVERGING" if r.htf2.converging else "SCANNING"
            parts.append(
                f"HTF2 ({r.htf2.timeframe}): {r.htf2.total_coiled}/9 sets, "
                f"CI {r.htf2.harmonic_score:.0f} — {htf2_state}"
            )

        alignment_desc = ""
        if r.full_mtf_stack:
            alignment_desc = (
                "FULL MTF STACK CONFIRMED — all three timeframes showing simultaneous compression. "
                "This is the highest-value configuration: the current-bar setup is not an isolated "
                "intraday coil but a reflection of compression that exists at the 4H and daily level. "
                "Institutional algorithms operating on higher timeframes are already anchored to "
                "the same price zone. The probability of a sustained directional move (versus a "
                "mean-reverting spike) is significantly elevated when the stack is complete."
            )
        elif r.mtf_aligned == 1:
            alignment_desc = (
                "Partial MTF alignment — one higher timeframe confirming. The base-TF setup "
                "has macro support from one tier but not full stack confirmation. Viable "
                "for tactical entries; full stack would increase conviction substantially."
            )
        else:
            alignment_desc = (
                "No higher-timeframe alignment — current compression is isolated to the base "
                "timeframe. Institutional algorithms on 4H and daily are NOT in convergence. "
                "This reduces the probability of a sustained move. Intraday scalp potential "
                "only — not an institutional positioning setup."
            )

        return ". ".join(parts) + ". " + alignment_desc

    def _level_narrative(self, ticker: str, r: SMLBase4Result) -> str:
        ceiling = round(r.anchor_ceiling, 4)
        floor   = round(r.anchor_floor, 4)
        center  = round(r.cloud_center, 4)
        spread_pct = round((ceiling - floor) / center * 100, 3) if center > 0 else 0

        return (
            f"Key levels derived from the 9-anchor EMA band:\n"
            f"  Anchor Ceiling: ${ceiling:.4f} — the highest of all 9 anchor EMAs (12, 24, 36, "
            f"48, 60, 72, 84, 96, 108-bar). This is where the slowest institutional money is "
            f"positioned. A close above this level confirms the breakout has cleared ALL anchor "
            f"EMA resistance simultaneously.\n"
            f"  Anchor Floor: ${floor:.4f} — the lowest anchor EMA. A close below this level "
            f"invalidates the compression setup — the coil has unwound to the downside.\n"
            f"  Cloud Center: ${center:.4f} — the average of fast + anchor EMAs for sets 1, 5, 9. "
            f"This is the gravitational center of the entire grid. Price oscillating around "
            f"this level during compression is healthy consolidation.\n"
            f"  Band Width: {spread_pct:.3f}% of price — "
            f"{'extremely tight — pre-breakout tension is high' if spread_pct < 0.5 else 'moderate compression — watching for further tightening' if spread_pct < 1.5 else 'wide band — not yet in compression zone'}."
        )

    def _risk_narrative(self, r: SMLBase4Result) -> str:
        risks = []

        if not r.sqi.ci_gate_passed:
            risks.append(
                "PRIMARY RISK: CI below structural gate — market makers retain stop-hunt capacity. "
                "Any entry here is in the chop zone."
            )

        if not r.full_mtf_stack:
            risks.append(
                "MTF RISK: Higher timeframes are not aligned. A base-TF breakout without HTF "
                "confirmation is more likely to be a trap than a sustained move."
            )

        if not r.vol_spike and not r.regime_compressed:
            risks.append(
                "VOLUME RISK: No volume spike detected and volatility regime is not compressed. "
                "Breakouts require volume expansion for confirmation. Without it, price may "
                "re-enter the compression range."
            )

        if r.compression_vector == CompressionVector.EXPANDING:
            risks.append(
                "VECTOR RISK: Compression is EXPANDING — the coil is unwinding. "
                "If CI drops below the structural gate (78), the setup is invalidated."
            )

        if r.bars_in_state > 20:
            risks.append(
                f"DURATION RISK: {r.bars_in_state} bars in convergence state. "
                "Extended compression increases the probability of a volatility event but "
                "reduces the ability to predict direction. Consider this when sizing."
            )

        if not risks:
            risks.append(
                "No primary risk flags. Monitor for CI drop below 78 (structural gate breach) "
                "or MTF stack breakdown (HTF compression dissolving before base-TF fires)."
            )

        return " | ".join(risks)

    # ─────────────────────────────────────────────────────────────────────
    # STRUCTURED DATA
    # ─────────────────────────────────────────────────────────────────────

    def _key_levels(self, r: SMLBase4Result) -> dict:
        return {
            "anchor_ceiling":   round(r.anchor_ceiling, 4),
            "anchor_floor":     round(r.anchor_floor, 4),
            "cloud_center":     round(r.cloud_center, 4),
            "band_width_pct":   round((r.anchor_ceiling - r.anchor_floor) / r.cloud_center * 100, 4) if r.cloud_center > 0 else 0,
            "invalidation_level": round(r.anchor_floor * 0.998, 4),  # 0.2% below anchor floor
        }

    def _signal_pillars(self, r: SMLBase4Result) -> dict:
        return {
            "compression_40pt": round(r.sqi.compression, 2),
            "mtf_alignment_30pt": round(r.sqi.mtf, 2),
            "volume_confirm_15pt": round(r.sqi.volume, 2),
            "regime_grade_15pt": round(r.sqi.regime, 2),
            "sqi_total_100pt": round(r.sqi.total, 2),
            "ci_structural_gate_78": r.sqi.ci_gate_passed,
            "sqi_execution_gate_75": r.sqi.total >= SQI_EXECUTION_GATE,
            "prime_status": r.sqi.is_prime,
        }

    def _gate_status(self, r: SMLBase4Result) -> dict:
        return {
            "ci_gate":     {"passed": r.sqi.ci_gate_passed, "threshold": CI_STRUCTURAL_GATE, "actual": round(r.harmonic_score, 1)},
            "sqi_gate":    {"passed": r.sqi.total >= SQI_EXECUTION_GATE, "threshold": SQI_EXECUTION_GATE, "actual": round(r.sqi.total, 1)},
            "mtf_stack":   {"passed": r.full_mtf_stack, "aligned": r.mtf_aligned, "required": 2},
            "volume_gate": {"passed": r.vol_spike, "near": r.vol_near},
            "regime_gate": {"passed": r.regime_compressed, "atr_pct": round(r.atr_pct, 1)},
        }

    def _setup_quality(self, r: SMLBase4Result) -> str:
        if r.sqi.is_prime and r.full_mtf_stack and r.regime_compressed:
            return "INSTITUTIONAL"
        if r.sqi.is_prime or (r.sqi.ci_gate_passed and r.sqi.total >= SQI_EXECUTION_GATE):
            return "TACTICAL"
        if r.sqi.ci_gate_passed and r.total_coiled >= 4:
            return "SPECULATIVE"
        return "AVOID"

    # ─────────────────────────────────────────────────────────────────────
    # AI AGENT SPECIFIC
    # ─────────────────────────────────────────────────────────────────────

    def _agent_instruction(self, ticker: str, r: SMLBase4Result, action: str) -> str:
        if action == "BUY_PRIME":
            return (
                f"PRIME SIGNAL ACTIVE on {ticker}. "
                f"The SML Base-4 dual-gate has cleared: CI {r.harmonic_score:.0f} >= 78 (structural) "
                f"AND SQI {r.sqi.total:.0f} >= 75 (execution). "
                f"{'Full MTF stack confirmed — higher timeframes aligned.' if r.full_mtf_stack else ''} "
                f"Action: BUY — human confirmation required before execution. "
                f"Anchor floor (invalidation): ${r.anchor_floor:.4f}. "
                f"Do not enter if price is already outside the anchor band."
            )
        if action == "BUY":
            return (
                f"CONFIRMED SIGNAL on {ticker}. CI gate cleared ({r.harmonic_score:.0f} >= 78). "
                f"SQI {r.sqi.total:.0f}/100. MTF: {r.mtf_aligned}/2 timeframes aligned. "
                f"Tactically viable — institutional-grade confirmation requires full MTF stack. "
                f"Human confirmation required before execution."
            )
        if action == "WATCH":
            return (
                f"BUILDING SETUP on {ticker}. {r.total_coiled}/9 sets compressed. "
                f"CI {r.harmonic_score:.0f} — structural gate {'cleared' if r.sqi.ci_gate_passed else 'NOT YET cleared (needs 78)'}. "
                f"SQI {r.sqi.total:.0f}/100 — execution gate {'cleared' if r.sqi.total >= 75 else 'NOT YET cleared (needs 75)'}. "
                f"Monitor for additional set convergence. No execution yet."
            )
        if action == "EXIT":
            return (
                f"CONVERGENCE RELEASED on {ticker}. "
                f"The EMA grid has begun unwinding — sets dropping below threshold. "
                f"If holding positions from a prior PRIME or BUY signal, review exits."
            )
        return (
            f"{ticker} in SCANNING state. CI {r.harmonic_score:.0f} — "
            f"{'below structural gate — chop zone active' if not r.sqi.ci_gate_passed else 'monitoring for additional convergence'}. "
            f"No actionable setup. Check back when CI approaches 78."
        )

    def _agent_context(self, ticker: str, r: SMLBase4Result) -> dict:
        """
        Structured context block for LLM tool use.
        Format designed for direct injection into AI agent prompts.
        """
        return {
            "engine":        "SML-Base4-v6.2",
            "ticker":        ticker,
            "timestamp":     r.timestamp.isoformat(),
            "methodology": {
                "description": (
                    "9 sets of 4 EMAs each in a 1:4:8:12 harmonic ratio. "
                    "Compression measured as percentile rank of avg EMA spread "
                    "over a 252-bar rolling window. Instrument-agnostic and self-calibrating. "
                    "CI >= 78 = structural gate (top 22nd pct). "
                    "SQI >= 75 = execution gate (all 4 pillars: compression 40pt, MTF 30pt, volume 15pt, regime 15pt). "
                    "Both gates must clear simultaneously for a PRIME signal."
                ),
                "ci_structural_gate":  CI_STRUCTURAL_GATE,
                "sqi_execution_gate":  SQI_EXECUTION_GATE,
                "pdt_rule":            "eliminated 2026-06-04",
                "margin_floor":        2000.0,
                "human_confirmation":  "required for all execution",
            },
            "current_reading": {
                "state":            r.state.value,
                "sets_coiled":      f"{r.total_coiled}/9",
                "ci_score":         round(r.harmonic_score, 1),
                "sqi_score":        round(r.sqi.total, 1),
                "is_prime":         r.sqi.is_prime,
                "ci_gate_passed":   r.sqi.ci_gate_passed,
                "full_mtf_stack":   r.full_mtf_stack,
                "directional_bias": r.directional_bias.value,
                "vol_regime":       r.vol_regime,
            },
            "price_levels": {
                "anchor_ceiling":    round(r.anchor_ceiling, 4),
                "anchor_floor":      round(r.anchor_floor, 4),
                "cloud_center":      round(r.cloud_center, 4),
                "invalidation":      round(r.anchor_floor * 0.998, 4),
            },
            "what_to_watch": (
                "Signal upgrades to PRIME when: CI >= 78 AND SQI >= 75 AND "
                f"{'additional MTF alignment' if r.mtf_aligned < 2 else 'maintaining current MTF stack'}. "
                f"Signal invalidated if: CI drops below 78 OR price closes below ${r.anchor_floor:.4f}."
            ),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_brief_engine = IntelligenceBriefEngine()

def generate_brief(ticker: str, result: SMLBase4Result) -> dict:
    """Convenience function — returns serializable dict."""
    brief = _brief_engine.generate(ticker, result)
    return _brief_engine.to_dict(brief)
