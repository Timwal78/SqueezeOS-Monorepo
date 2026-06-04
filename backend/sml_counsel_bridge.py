"""
SML COUNSEL BRIDGE — Phase 4
══════════════════════════════════════════════════════════════════════════════
Connects the SML Base-4 signal engine to the TradingAgents counsel system.

Flow:
  SMLBase4Result + Oracle score
      ↓
  Structured context brief (injected as past_context for counsel agents)
      ↓
  TradingAgentsGraph.propagate(ticker, date)
      ↓
  Bull/Bear/Neutral debate → Trader decision
      ↓
  CounselVerdict (action, reasoning, confidence, risk_notes)
      ↓
  OrderRequest.counsel_verdict field

The counsel agents receive the full quantitative picture from SML B4 so their
debate is grounded in the compression state, MTF alignment, and price levels —
not just general market narrative.

Performance note: TradingAgentsGraph.propagate() makes multiple LLM calls.
Expect 20-60 seconds per verdict. Use asyncio.run_in_executor() in async contexts.
Results are cached per ticker+date to prevent redundant API calls.

© ScriptMasterLabs. Proprietary.
"""

from __future__ import annotations
import os
import sys
import json
import logging
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger("SMLCounsel")

# Ensure agents directory is on path
_AGENTS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agents"
)
if _AGENTS_ROOT not in sys.path:
    sys.path.insert(0, _AGENTS_ROOT)

# ─────────────────────────────────────────────────────────────────────────────
# VERDICT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CounselVerdict:
    """Output from the TradingAgents counsel panel."""
    ticker:          str
    date:            str
    action:          str          # "BUY" | "SELL" | "HOLD"
    confidence:      float        # 0-1
    reasoning:       str          # Summarized counsel debate conclusion
    risk_notes:      str          # Risk factors identified by conservative debater
    bull_thesis:     str          # Bull researcher thesis (condensed)
    bear_thesis:     str          # Bear researcher thesis (condensed)
    sml_b4_context:  dict         # The SML B4 data injected as context
    raw_decision:    Optional[dict] = None  # Full TradingAgents decision dict
    duration_s:      float = 0.0
    error:           Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_sml_context_for_counsel(
    ticker:        str,
    b4_result_dict: dict,
    oracle_score:  float = 0.0,
    brief_dict:    Optional[dict] = None,
) -> str:
    """
    Builds a rich structured context string from SML B4 data for injection
    into TradingAgentsGraph as past_context.

    The counsel agents (bull/bear researchers, debaters, trader) will read
    this context and ground their analysis in the quantitative signal state.
    """
    r = b4_result_dict
    state       = r.get("state", {})
    compression = r.get("compression", {})
    sqi         = r.get("sqi", {})
    mtf         = r.get("mtf", {})
    levels      = r.get("levels", {})
    context     = r.get("context", {})

    headline = brief_dict.get("headline", "") if brief_dict else ""
    agent_instruction = brief_dict.get("agent_instruction", "") if brief_dict else ""
    compression_narrative = brief_dict.get("compression_narrative", "") if brief_dict else ""

    return f"""
=== SML BASE-4 SOVEREIGN HARMONIC MATRIX — QUANTITATIVE SIGNAL CONTEXT ===
Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
Ticker: {ticker}
Engine: SML Base-4 v6.2 | ScriptMasterLabs

HEADLINE: {headline or f"{ticker} — {state.get('current', 'UNKNOWN')}"}

SIGNAL STATE:
  - Convergence State: {state.get("current", "UNKNOWN")}
  - Sets Coiled: {state.get("total_sets_coiled", 0)}/9 EMA sets compressed
  - Bars in State: {state.get("bars_in_state", 0)} bars
  - Oracle Composite Score: {oracle_score:.0f}/100

COMPRESSION ANALYSIS:
  - Harmonic Score (CI): {compression.get("harmonic_score", 0):.1f}/100
  - CI Structural Gate (>=78): {"PASSED" if compression.get("ci_gate_passed") else "NOT CLEARED"}
  - Avg EMA Spread: {compression.get("avg_spread_pct", 0):.4f}% of price
  - Adaptive Threshold: {compression.get("threshold_pct", 0):.4f}%

  MEANING: {compression_narrative[:300] if compression_narrative else "See SML Base-4 methodology."}

SIGNAL QUALITY INDEX (SQI): {sqi.get("total", 0):.1f}/100
  - Compression pillar (40pt): {sqi.get("breakdown", {}).get("compression_40pt", 0):.1f}
  - MTF Alignment pillar (30pt): {sqi.get("breakdown", {}).get("mtf_30pt", 0):.1f}
  - Volume Confirmation (15pt): {sqi.get("breakdown", {}).get("volume_15pt", 0):.1f}
  - Regime Grade (15pt): {sqi.get("breakdown", {}).get("regime_15pt", 0):.1f}
  - PRIME SIGNAL STATUS: {"YES — dual-gate cleared" if sqi.get("is_prime") else "NO — gates not fully cleared"}

MULTI-TIMEFRAME ALIGNMENT:
  - MTF Aligned: {mtf.get("aligned_count", 0)}/2 higher timeframes converging
  - Full MTF Stack: {"YES — all timeframes aligned" if mtf.get("full_stack") else "NO"}
  - HTF1: {mtf.get("htf1", {}).get("total_coiled", "N/A")}/9 sets, CI {mtf.get("htf1", {}).get("harmonic_score", "N/A")} — {"CONVERGING" if mtf.get("htf1", {}).get("converging") else "SCANNING"}
  - HTF2: {mtf.get("htf2", {}).get("total_coiled", "N/A")}/9 sets, CI {mtf.get("htf2", {}).get("harmonic_score", "N/A")} — {"CONVERGING" if mtf.get("htf2", {}).get("converging") else "SCANNING"}

KEY PRICE LEVELS:
  - Anchor Ceiling: ${levels.get("anchor_ceiling", 0):.4f} (highest of 9 anchor EMAs — breakout confirmation above this)
  - Anchor Floor:   ${levels.get("anchor_floor", 0):.4f} (lowest of 9 anchor EMAs — invalidation below this)
  - Cloud Center:   ${levels.get("cloud_center", 0):.4f} (gravitational center of EMA grid)

MARKET CONTEXT:
  - Directional Bias: {context.get("directional_bias", "UNKNOWN")}
  - Compression Vector: {context.get("compression_vector", "UNKNOWN")} (is compression increasing or decreasing?)
  - Cloud Momentum: {context.get("cloud_momentum", "UNKNOWN")}
  - Volatility Regime: {context.get("vol_regime", "UNKNOWN")} (ATR at {context.get("atr_percentile", 0):.1f}th percentile)
  - Volume: {"SPIKE — elevated buying/selling pressure" if context.get("vol_spike") else "BASELINE"}

AGENT INSTRUCTION FROM SML ENGINE:
{agent_instruction or "See signal state above for guidance."}

NOTES FOR COUNSEL DEBATE:
- This quantitative signal does NOT replace fundamental or news analysis.
- The Base-4 matrix provides: (1) compression state, (2) price levels, (3) regime context.
- Bull researchers should consider: does the fundamental thesis support this compression setup?
- Bear researchers should consider: what catalysts could break the anchor floor and unwind the coil?
- Risk managers: the $2,000 account floor must be protected. PDT rule eliminated 2026-06-04.
==========================================================================
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# COUNSEL BRIDGE
# ─────────────────────────────────────────────────────────────────────────────

class SMLCounselBridge:
    """
    Bridges SML Base-4 signals to the TradingAgents counsel system.

    Usage (async context):
        bridge = SMLCounselBridge()
        verdict = await bridge.get_verdict(
            ticker="SPY",
            b4_result_dict=signal_data,
            oracle_score=74.0,
            brief_dict=brief_data,
        )
        order = OrderRequest(
            symbol=ticker,
            side="buy" if verdict.action == "BUY" else "sell",
            quantity=...,
            counsel_verdict=f"{verdict.action} — {verdict.reasoning[:100]}",
            sqi_score=signal_data["sqi"]["total"],
            oracle_score=oracle_score,
            signal_state=signal_data["state"]["current"],
        )
    """

    def __init__(self):
        self._cache: Dict[str, CounselVerdict] = {}
        self._cache_ttl = 300   # 5-minute cache per ticker
        self._ta_available = False
        self._try_import()

    def _try_import(self) -> None:
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            from tradingagents.default_config import DEFAULT_CONFIG
            self._TradingAgentsGraph = TradingAgentsGraph
            self._DEFAULT_CONFIG = DEFAULT_CONFIG
            self._ta_available = True
            logger.info("[CounselBridge] TradingAgents graph loaded successfully")
        except ImportError as exc:
            logger.warning("[CounselBridge] TradingAgents unavailable — %s. Using stub mode.", exc)
            self._ta_available = False

    def is_available(self) -> bool:
        return self._ta_available

    async def get_verdict(
        self,
        ticker:          str,
        b4_result_dict:  dict,
        oracle_score:    float = 0.0,
        brief_dict:      Optional[dict] = None,
        trade_date:      Optional[str] = None,
        analysts:        Optional[list] = None,
    ) -> CounselVerdict:
        """
        Asynchronous entry point. Runs TradingAgentsGraph in a thread executor
        to avoid blocking the event loop during multi-LLM-call propagation.
        """
        cache_key = f"{ticker}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.time() - float(cached.duration_s or 0) < self._cache_ttl:
                logger.debug("[CounselBridge] Cache hit for %s", ticker)
                return cached

        loop = asyncio.get_event_loop()
        verdict = await loop.run_in_executor(
            None,
            self._run_blocking,
            ticker, b4_result_dict, oracle_score, brief_dict, trade_date, analysts,
        )
        self._cache[cache_key] = verdict
        return verdict

    def _run_blocking(
        self,
        ticker:         str,
        b4_result_dict: dict,
        oracle_score:   float,
        brief_dict:     Optional[dict],
        trade_date:     Optional[str],
        analysts:       Optional[list],
    ) -> CounselVerdict:
        """Synchronous execution — called from run_in_executor."""
        t0 = time.time()
        date_str = trade_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sml_context = build_sml_context_for_counsel(ticker, b4_result_dict, oracle_score, brief_dict)

        if not self._ta_available:
            return self._stub_verdict(ticker, date_str, b4_result_dict, sml_context, t0)

        try:
            config = self._DEFAULT_CONFIG.copy()
            config["max_debate_rounds"] = 1   # Keep it fast — 1 round for paper mode

            selected_analysts = analysts or ["market", "news"]   # Minimal for speed

            ta = self._TradingAgentsGraph(
                selected_analysts=selected_analysts,
                debug=False,
                config=config,
            )

            _, decision = ta.propagate(
                company_name=ticker,
                trade_date=date_str,
                past_context=sml_context,
            )

            return self._parse_decision(ticker, date_str, decision, b4_result_dict, sml_context, t0)

        except Exception as exc:
            logger.exception("[CounselBridge] Propagation error for %s: %s", ticker, exc)
            return CounselVerdict(
                ticker=ticker, date=date_str,
                action="HOLD", confidence=0.3,
                reasoning=f"Counsel error — defaulting to HOLD. Error: {str(exc)[:100]}",
                risk_notes="Counsel system unavailable. Human review required.",
                bull_thesis="N/A", bear_thesis="N/A",
                sml_b4_context=b4_result_dict,
                duration_s=round(time.time() - t0, 2),
                error=str(exc),
            )

    def _parse_decision(
        self,
        ticker:   str,
        date_str: str,
        decision: Any,
        b4_dict:  dict,
        context:  str,
        t0:       float,
    ) -> CounselVerdict:
        """Parse TradingAgents decision into CounselVerdict."""
        if isinstance(decision, dict):
            action   = str(decision.get("action", decision.get("decision", "HOLD"))).upper().strip()
            reasoning = str(decision.get("reasoning", decision.get("explanation", "")))[:500]
            risk_notes = str(decision.get("risk", decision.get("risks", "")))[:300]
            bull_thesis = str(decision.get("bull_thesis", decision.get("bull", "")))[:300]
            bear_thesis = str(decision.get("bear_thesis", decision.get("bear", "")))[:300]
            confidence  = float(decision.get("confidence", 0.6))
        elif isinstance(decision, str):
            action     = "BUY" if "buy" in decision.lower() else "SELL" if "sell" in decision.lower() else "HOLD"
            reasoning  = decision[:500]
            risk_notes = ""
            bull_thesis = ""
            bear_thesis = ""
            confidence  = 0.5
        else:
            action = "HOLD"; reasoning = str(decision)[:200]
            risk_notes = ""; bull_thesis = ""; bear_thesis = ""
            confidence = 0.4

        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"

        return CounselVerdict(
            ticker=ticker, date=date_str,
            action=action,
            confidence=min(1.0, max(0.0, confidence)),
            reasoning=reasoning,
            risk_notes=risk_notes,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            sml_b4_context=b4_dict,
            raw_decision=decision if isinstance(decision, dict) else {"raw": str(decision)},
            duration_s=round(time.time() - t0, 2),
        )

    def _stub_verdict(
        self,
        ticker:   str,
        date_str: str,
        b4_dict:  dict,
        context:  str,
        t0:       float,
    ) -> CounselVerdict:
        """
        Stub verdict when TradingAgents is unavailable.
        Uses SML B4 signal quality to generate a deterministic fallback.
        Suitable for paper mode when Anthropic API key is not configured.
        """
        sqi   = b4_dict.get("sqi", {})
        state = b4_dict.get("state", {})
        is_prime = sqi.get("is_prime", False)
        ci_gate  = b4_dict.get("compression", {}).get("ci_gate_passed", False)
        total_coiled = state.get("total_sets_coiled", 0)

        if is_prime:
            action     = "BUY"
            confidence = 0.82
            reasoning  = (
                f"[STUB] SML B4 dual-gate confirmed — CI gate passed and SQI {sqi.get('total', 0):.0f}/100. "
                f"{total_coiled}/9 sets coiled. Counsel agent unavailable; signal quality warrants BUY consideration."
            )
        elif ci_gate and total_coiled >= 5:
            action     = "BUY"
            confidence = 0.62
            reasoning  = f"[STUB] Structural compression confirmed ({total_coiled}/9 sets). Counsel agent unavailable."
        elif state.get("current") == "SCANNING":
            action     = "HOLD"
            confidence = 0.30
            reasoning  = "[STUB] Market in scanning state — no setup. Counsel agent unavailable."
        else:
            action     = "HOLD"
            confidence = 0.45
            reasoning  = "[STUB] Building setup — watch for full convergence. Counsel agent unavailable."

        return CounselVerdict(
            ticker=ticker, date=date_str,
            action=action, confidence=confidence, reasoning=reasoning,
            risk_notes=f"Stub mode — TradingAgents not available. Review SML B4 context: {context[:150]}",
            bull_thesis="N/A (stub mode)", bear_thesis="N/A (stub mode)",
            sml_b4_context=b4_dict,
            duration_s=round(time.time() - t0, 3),
            error="TradingAgents unavailable — stub mode active",
        )


# ─────────────────────────────────────────────────────────────────────────────
# FULL PIPELINE HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def run_full_pipeline(
    ticker:         str,
    account_equity: float = 5000.0,
    paper_mode:     bool  = True,
) -> dict:
    """
    Full signal → counsel → circuit breaker → paper fill pipeline.
    Returns a complete audit record.

    This is the end-to-end demonstration of the SML institutional stack.
    """
    import yfinance as yf, pandas as pd
    from sml_base4_engine import SMLBase4Engine, SMLBase4Config
    from sml_intelligence_brief import generate_brief
    from robinhood_mcp_adapter import RobinhoodMCPAdapter, CircuitBreaker, OrderRequest

    logger.info("[Pipeline] Starting full pipeline for %s", ticker)

    # 1. Fetch data and compute Base-4 signal
    raw = yf.download(ticker, period="1y", interval="1h", auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() for c in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]

    engine = SMLBase4Engine(SMLBase4Config(ci_structural_gate=78, sqi_prime_level=75))
    result = engine.compute(raw)

    # 2. Get last price
    last_price = float(raw["close"].iloc[-1])

    # 3. Intelligence brief
    brief = generate_brief(ticker, result)

    # 4. Counsel verdict
    from dataclasses import asdict
    b4_dict = _result_to_api_dict(ticker, result)
    bridge = SMLCounselBridge()
    verdict = await bridge.get_verdict(ticker, b4_dict, brief_dict=brief)

    # 5. Circuit breaker + paper execution
    cb = CircuitBreaker()
    adapter = RobinhoodMCPAdapter(circuit_breaker=cb, paper_mode=paper_mode)

    # Position sizing: 1.5% of equity, capped by circuit breaker rules
    position_value = account_equity * 0.015
    quantity = round(position_value / last_price, 4) if last_price > 0 else 0

    if verdict.action in ("BUY",) and result.sqi.ci_gate_passed:
        order = OrderRequest(
            symbol=ticker,
            side="buy",
            quantity=quantity,
            signal_state=result.state.value,
            sqi_score=round(result.sqi.total, 1),
            oracle_score=0.0,
            counsel_verdict=f"{verdict.action} ({verdict.confidence:.0%}) — {verdict.reasoning[:80]}",
        )
        fill = await adapter.submit(order, last_price=last_price, account_equity=account_equity)
        fill_dict = {"status": fill.status, "fill_price": fill.fill_price, "order_id": fill.order_id, "rejection_reason": fill.rejection_reason}
    else:
        fill_dict = {"status": "NO_ORDER", "reason": f"Counsel: {verdict.action} | CI gate: {result.sqi.ci_gate_passed}"}

    return {
        "ticker":        ticker,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "signal":        {"state": result.state.value, "ci": round(result.harmonic_score, 1), "sqi": round(result.sqi.total, 1), "is_prime": result.sqi.is_prime},
        "counsel":       {"action": verdict.action, "confidence": verdict.confidence, "reasoning": verdict.reasoning[:150], "error": verdict.error},
        "execution":     fill_dict,
        "paper_mode":    paper_mode,
        "account_equity": account_equity,
    }


def _result_to_api_dict(ticker: str, result) -> dict:
    """Minimal serialization for pipeline use."""
    return {
        "state":       {"current": result.state.value, "total_sets_coiled": result.total_coiled, "bars_in_state": result.bars_in_state},
        "compression": {"harmonic_score": round(result.harmonic_score, 2), "ci_gate_passed": result.sqi.ci_gate_passed, "avg_spread_pct": round(result.avg_spread, 4), "threshold_pct": round(result.effective_threshold, 4)},
        "sqi":         {"total": round(result.sqi.total, 2), "is_prime": result.sqi.is_prime, "breakdown": {"compression_40pt": round(result.sqi.compression, 2), "mtf_30pt": round(result.sqi.mtf, 2), "volume_15pt": round(result.sqi.volume, 2), "regime_15pt": round(result.sqi.regime, 2)}},
        "mtf":         {"aligned_count": result.mtf_aligned, "full_stack": result.full_mtf_stack, "htf1": {"total_coiled": result.htf1.total_coiled if result.htf1 else 0, "harmonic_score": round(result.htf1.harmonic_score, 1) if result.htf1 else 0, "converging": result.htf1.converging if result.htf1 else False}, "htf2": {"total_coiled": result.htf2.total_coiled if result.htf2 else 0, "harmonic_score": round(result.htf2.harmonic_score, 1) if result.htf2 else 0, "converging": result.htf2.converging if result.htf2 else False}},
        "context":     {"directional_bias": result.directional_bias.value, "compression_vector": result.compression_vector.value, "cloud_momentum": result.cloud_momentum.value, "vol_regime": result.vol_regime, "atr_percentile": round(result.atr_pct, 1), "vol_spike": result.vol_spike},
        "levels":      {"anchor_ceiling": round(result.anchor_ceiling, 4), "anchor_floor": round(result.anchor_floor, 4), "cloud_center": round(result.cloud_center, 4)},
    }


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio, logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    result = asyncio.run(run_full_pipeline("SPY", account_equity=3500.0, paper_mode=True))
    print("\n" + "=" * 70)
    print("FULL PIPELINE RESULT")
    print("=" * 70)
    for k, v in result.items():
        if isinstance(v, dict):
            print(f"{k}:")
            for kk, vv in v.items():
                print(f"  {kk}: {vv}")
        else:
            print(f"{k}: {v}")
