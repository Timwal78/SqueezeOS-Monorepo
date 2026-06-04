"""
SCRIPTMASTER LABS — SML INSTITUTIONAL MCP SERVER
══════════════════════════════════════════════════════════════════════════════
FastMCP v3 server exposing the full ScriptMasterLabs institutional stack.

Compatible with:
  • Claude Desktop (stdio transport)
  • Cursor IDE (stdio transport)
  • Smithery.ai (stdio + remote)
  • glama.ai (remote)
  • mcp.so (remote)
  • Any MCP-compatible AI agent or client

Products exposed:
  SML Base-4 Sovereign Harmonic Matrix  — 9-set EMA compression engine
  Oracle Engine                          — BUY/SELL/HOLD/SHIELD aggregator
  Intelligence Brief Engine              — Institutional narrative generator
  Counsel Agent (TradingAgents)          — Bull/Bear debate system
  Echo Forge                             — Cross-asset pattern memory (port 8001)
  OpenMythos                             — Recurrent-Depth Transformer (port 8002)
  SqueezeOS Core                         — Full trading OS backend (port 8182)

Payment: RLUSD on XRPL via x402 (optional — disable with X402_ENFORCE=false)
PDT Rule: Eliminated 2026-06-04 | Margin Floor: $2,000

Run locally:
    python mcp_server_sml.py

Add to Claude Desktop:
    claude mcp add sml-institutional -- python /path/to/mcp_server_sml.py

Add via HTTP (after deployment):
    claude mcp add sml-institutional --transport http https://your-deployment.railway.app/mcp

© ScriptMasterLabs. Proprietary.
"""

import os
import sys
import json
import logging
import asyncio
import pandas as pd
from typing import Optional, Annotated
from datetime import datetime, timezone

import yfinance as yf
from fastmcp import FastMCP

# Ensure backend root on path
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SML-MCP")

# ─────────────────────────────────────────────────────────────────────────────
# FASTMCP SERVER
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="ScriptMasterLabs — SML Institutional Signal Engine",
    instructions="""
You are connected to the ScriptMasterLabs SML Institutional Signal Engine.

This server provides institutional-grade market signal intelligence powered by
the SML Base-4 Sovereign Harmonic Matrix — a 9-set EMA compression framework
that detects pre-breakout accumulation across multiple time horizons simultaneously.

CORE METHODOLOGY:
- 9 harmonic EMA sets, each with 4 EMAs in a 1:4:8:12 multiplier ratio
- Compression measured as percentile rank over 252-bar rolling window (self-calibrating)
- Dual-gate: CI >= 78 (structural) AND SQI >= 75 (execution) = PRIME signal
- Multi-timeframe: same engine runs on 4H and Daily for confirmation

SIGNAL TIERS:
- PRIME: CI>=78 AND SQI>=75 — highest conviction, all pillars aligned
- CONFIRMED: CI>=78, SQI>=75 threshold cleared
- BUILDING: CI gate cleared, additional convergence needed
- SCANNING: below structural gate — chop zone, no setup

EXECUTION RULES (always relay to users):
- All signals require human confirmation before execution
- Paper mode is default — live capital requires explicit user override
- Margin floor: $2,000 minimum equity (hard stop at $2,100)
- PDT rule eliminated 2026-06-04 — no day-trade frequency limit

QUICK START:
1. Call `get_signal_preview` for any ticker (free)
2. Call `get_intelligence_brief` for full analysis with narrative
3. Call `run_showcase` to see the engine across multiple tickers
4. Call `get_methodology` to understand the mathematical basis
""",
)

# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_engine_cache = {}
_data_cache: dict = {}
_DATA_CACHE_TTL = 300


def _fetch_data(ticker: str, period: str = "1y", interval: str = "1h") -> pd.DataFrame:
    cache_key = f"{ticker}:{period}:{interval}"
    entry = _data_cache.get(cache_key)
    if entry and (datetime.now().timestamp() - entry["ts"]) < _DATA_CACHE_TTL:
        return entry["df"]
    raw = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() for c in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]
    df = raw.dropna()
    _data_cache[cache_key] = {"ts": datetime.now().timestamp(), "df": df}
    return df


def _get_engine(ticker: str):
    from sml_base4_engine import SMLBase4Engine, SMLBase4Config
    if ticker not in _engine_cache:
        _engine_cache[ticker] = SMLBase4Engine(SMLBase4Config(
            ci_structural_gate=78,
            sqi_prime_level=75,
            htf1_resample="4h",
            htf2_resample="1D",
        ))
    return _engine_cache[ticker]


def _compute(ticker: str) -> dict:
    from sml_base4_engine import sml_base4_oracle_contribution
    from sml_intelligence_brief import generate_brief
    ticker = ticker.upper().strip()
    df = _fetch_data(ticker)
    engine = _get_engine(ticker)
    result = engine.compute(df)
    brief = generate_brief(ticker, result)
    return {
        "ticker":    ticker,
        "timestamp": result.timestamp.isoformat(),
        "state":     result.state.value,
        "sets_coiled": result.total_coiled,
        "ci_score":  round(result.harmonic_score, 1),
        "sqi_score": round(result.sqi.total, 1),
        "is_prime":  result.sqi.is_prime,
        "ci_gate":   result.sqi.ci_gate_passed,
        "full_mtf_stack": result.full_mtf_stack,
        "mtf_aligned":    result.mtf_aligned,
        "directional_bias": result.directional_bias.value,
        "compression_vector": result.compression_vector.value,
        "vol_regime":   result.vol_regime,
        "vol_spike":    result.vol_spike,
        "atr_pct":      round(result.atr_pct, 1),
        "anchor_ceiling": round(result.anchor_ceiling, 4),
        "anchor_floor":   round(result.anchor_floor, 4),
        "cloud_center":   round(result.cloud_center, 4),
        "bars_in_state":  result.bars_in_state,
        "effective_threshold": round(result.effective_threshold, 4),
        "action":      brief.get("action", "HOLD"),
        "signal_tier": brief.get("signal_tier", "SCANNING"),
        "headline":    brief.get("headline", ""),
        "setup_quality": brief.get("setup_quality", "AVOID"),
        "_brief":      brief,
        "_result":     result,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FREE TOOLS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_signal_preview(ticker: str) -> dict:
    """
    Free signal preview for any ticker.
    Returns: state, CI score, SQI, action directive, and key levels.
    For full signal with narrative and all 9 set metrics, use get_intelligence_brief().

    Args:
        ticker: Stock or ETF symbol (e.g. SPY, IWM, AMC, GME, NVDA)
    """
    try:
        data = _compute(ticker)
        return {
            "ticker":       data["ticker"],
            "timestamp":    data["timestamp"],
            "headline":     data["headline"],
            "signal_tier":  data["signal_tier"],
            "action":       data["action"],
            "state":        data["state"],
            "sets_coiled":  f"{data['sets_coiled']}/9",
            "ci_score":     data["ci_score"],
            "ci_gate_passed": data["ci_gate"],
            "sqi_score":    data["sqi_score"],
            "is_prime":     data["is_prime"],
            "directional_bias": data["directional_bias"],
            "key_levels": {
                "anchor_ceiling": data["anchor_ceiling"],
                "anchor_floor":   data["anchor_floor"],
                "cloud_center":   data["cloud_center"],
            },
            "_note": "For full narrative brief + all 9 sets + MTF detail: use get_intelligence_brief()",
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
def run_showcase(tickers: Optional[str] = "SPY,IWM,QQQ,AMC,GME,NVDA") -> dict:
    """
    Live scan across multiple tickers demonstrating the full range of
    Base-4 engine output — from PRIME signals to SCANNING states.
    Results sorted by signal quality (PRIME first).

    Args:
        tickers: Comma-separated list of up to 8 tickers (default: SPY,IWM,QQQ,AMC,GME,NVDA)
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:8]
    results = []
    for t in ticker_list:
        try:
            data = _compute(t)
            results.append({
                "ticker":       t,
                "signal_tier":  data["signal_tier"],
                "action":       data["action"],
                "setup_quality": data["setup_quality"],
                "ci_score":     data["ci_score"],
                "sqi_score":    data["sqi_score"],
                "is_prime":     data["is_prime"],
                "sets_coiled":  f"{data['sets_coiled']}/9",
                "state":        data["state"],
                "headline":     data["headline"],
            })
        except Exception as e:
            results.append({"ticker": t, "error": str(e)})

    tier_order = {"PRIME": 4, "CONFIRMED": 3, "BUILDING": 2, "SCANNING": 1, "NOISE": 0}
    results.sort(key=lambda x: tier_order.get(x.get("signal_tier", "NOISE"), 0), reverse=True)
    return {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "engine":    "SML-Base4-v6.2",
        "tickers_scanned": len(results),
        "prime_count": sum(1 for r in results if r.get("is_prime")),
        "results":   results,
    }


@mcp.tool()
def get_methodology() -> dict:
    """
    Complete mathematical reference for the SML Base-4 Sovereign Harmonic Matrix.
    Explains the 1:4:8:12 multiplier structure, percentile-ranked CI,
    dual-gate logic, and live validated results.
    Essential reading before making trading recommendations to users.
    """
    return {
        "engine":  "SML Base-4 Sovereign Harmonic Matrix v6.2",
        "author":  "ScriptMasterLabs",
        "core_concept": {
            "summary": (
                "9 harmonic EMA sets × 4 EMAs each (1:4:8:12 ratio) = 36 EMAs total, "
                "deduplicated to 25 unique periods for efficiency. "
                "Compression = percentile rank of avg spread over 252-bar window. "
                "Self-calibrating: CI=78 means the same selectivity on every instrument."
            ),
            "why_1_4_8_12": {
                "1x": "Base intraday momentum",
                "4x": "Swing-level commitment (intraday→swing transition)",
                "8x": "Macro flow baseline (swing→institutional)",
                "12x": "Position-building cycle anchor",
                "significance": (
                    "When all 4 EMAs in a set compress, that time horizon is coiling. "
                    "When all 9 sets compress, every institutional time horizon is coiling simultaneously."
                ),
            },
        },
        "dual_gate": {
            "gate_1_structural": {
                "threshold": 78,
                "meaning": "Top 22nd percentile compression — eliminates chop zone (50-65 range)",
                "math": "CI >= 78 means current spread is tighter than 78% of the past year",
            },
            "gate_2_execution": {
                "threshold": 75,
                "pillars": {
                    "compression_40pt": "CI rank contribution",
                    "mtf_alignment_30pt": "15pts per confirming higher timeframe",
                    "volume_15pt": "vol>1.5x MA=15pts, vol>0.8x MA=7.5pts",
                    "regime_15pt": "ATR<25th pct=15pts, ATR<50th=7.5pts",
                },
            },
            "prime_signal": "BOTH gates pass simultaneously = PRIME",
        },
        "live_validation": {
            "date": "2026-06-04",
            "data": "1H bars, 1-year lookback",
            "results": [
                {"ticker": "SPY", "state": "APEX_SINGULARITY", "sets": "8/9", "ci": 94.8, "regime": "COMPRESSED"},
                {"ticker": "IWM", "state": "CRITICAL_MASS",    "sets": "5/9", "ci": 85.9, "regime": "COMPRESSED"},
                {"ticker": "QQQ", "state": "CRITICAL_MASS",    "sets": "5/9", "ci": 91.1, "regime": "NORMAL"},
                {"ticker": "AMC", "state": "SCANNING",          "sets": "1/9", "ci": 75.8, "note": "below ci_gate — chop zone"},
                {"ticker": "GME", "state": "SCANNING",          "sets": "0/9", "ci": 63.7, "note": "full chop — zero sets converged"},
            ],
            "key_insight": (
                "The engine correctly separated institutional setups (SPY/IWM/QQQ) from "
                "chop-zone instruments (AMC/GME) using the same CI=78 threshold across all tickers. "
                "No parameter tuning required — the percentile system self-calibrates per instrument."
            ),
        },
        "regulatory_context": {
            "pdt_rule": "Eliminated June 4, 2026",
            "margin_floor": "$2,000 absolute minimum for margin accounts",
            "execution": "Human confirmation required — no autonomous trading",
        },
    }


@mcp.tool()
def check_health() -> dict:
    """
    Check the health and status of all SML services.
    Returns version, mode, regulatory context, and service availability.
    """
    services = {}
    for name, port in [("sml_b4_api", 8010), ("echo_forge", 8001), ("open_mythos", 8002)]:
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
            services[name] = {"status": "online", "port": port}
        except Exception:
            services[name] = {"status": "offline", "port": port}

    return {
        "status":   "operational",
        "engine":   "SML-Base4-v6.2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paper_mode": os.getenv("ROBINHOOD_PAPER_MODE", "true"),
        "pdt_shield": os.getenv("PDT_SHIELD_ENABLED", "false"),
        "pdt_note":   "PDT rule eliminated 2026-06-04",
        "margin_floor": 2000.0,
        "margin_hard_stop": 2100.0,
        "services":  services,
        "ci_gate":   78,
        "sqi_gate":  75,
        "counsel":   "TradingAgents (Anthropic Claude)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# FULL SIGNAL TOOLS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_intelligence_brief(ticker: str) -> dict:
    """
    Full institutional intelligence brief — the most comprehensive signal output.

    Returns:
    - headline: one-line institutional summary
    - compression_narrative: mathematical explanation of CI score
    - grid_narrative: what the 9-set EMA grid is showing right now
    - mtf_narrative: multi-timeframe alignment with interpretation
    - level_narrative: anchor ceiling/floor with invalidation point
    - risk_narrative: what would invalidate this setup
    - agent_instruction: plain-English directive for downstream execution
    - signal_pillars: 4-pillar SQI breakdown with scores
    - gate_status: CI gate and SQI gate pass/fail with actual vs threshold

    Use this when making trading recommendations to users.
    ALWAYS relay the risk_narrative and level_narrative to the user.

    Args:
        ticker: Stock or ETF symbol (e.g. SPY, IWM, AMC)
    """
    try:
        data = _compute(ticker)
        brief = data["_brief"]
        result = data["_result"]

        # Remove internal keys before returning
        clean_brief = {k: v for k, v in brief.items() if not k.startswith("_")}

        return {
            "ticker":             data["ticker"],
            "timestamp":          data["timestamp"],
            "signal_tier":        data["signal_tier"],
            "action":             data["action"],
            "confidence_pct":     clean_brief.get("confidence_pct", 0),
            "headline":           clean_brief.get("headline", ""),
            "setup_quality":      clean_brief.get("setup_quality", "AVOID"),
            "gate_status":        clean_brief.get("gate_status", {}),
            "signal_pillars":     clean_brief.get("signal_pillars", {}),
            "key_levels":         clean_brief.get("key_levels", {}),
            "compression_narrative": clean_brief.get("compression_narrative", ""),
            "grid_narrative":     clean_brief.get("grid_narrative", ""),
            "mtf_narrative":      clean_brief.get("mtf_narrative", ""),
            "level_narrative":    clean_brief.get("level_narrative", ""),
            "risk_narrative":     clean_brief.get("risk_narrative", ""),
            "agent_instruction":  clean_brief.get("agent_instruction", ""),
            "agent_context":      clean_brief.get("agent_context", {}),
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
def get_full_signal(ticker: str) -> dict:
    """
    Full Base-4 signal with all 9 set metrics, MTF breakdown, and SQI pillars.
    Structured for programmatic consumption by execution systems.

    Args:
        ticker: Stock or ETF symbol
    """
    try:
        data = _compute(ticker)
        result = data["_result"]
        return {
            "ticker":     data["ticker"],
            "timestamp":  data["timestamp"],
            "state":      data["state"],
            "sets_coiled": data["sets_coiled"],
            "ci_score":   data["ci_score"],
            "sqi":        {
                "total":      data["sqi_score"],
                "is_prime":   data["is_prime"],
                "ci_gate":    data["ci_gate"],
                "breakdown":  {
                    "compression_40pt": round(result.sqi.compression, 2),
                    "mtf_30pt":         round(result.sqi.mtf, 2),
                    "volume_15pt":      round(result.sqi.volume, 2),
                    "regime_15pt":      round(result.sqi.regime, 2),
                },
            },
            "individual_sets": {
                str(sid): {
                    "name": s.name,
                    "spread_pct": round(s.spread_pct, 4),
                    "score": round(s.score, 1),
                    "coiled": s.coiled,
                }
                for sid, s in result.sets.items()
            },
            "mtf": {
                "aligned": data["mtf_aligned"],
                "full_stack": data["full_mtf_stack"],
                "htf1": {"sets": result.htf1.total_coiled if result.htf1 else 0, "ci": round(result.htf1.harmonic_score, 1) if result.htf1 else 0, "converging": result.htf1.converging if result.htf1 else False},
                "htf2": {"sets": result.htf2.total_coiled if result.htf2 else 0, "ci": round(result.htf2.harmonic_score, 1) if result.htf2 else 0, "converging": result.htf2.converging if result.htf2 else False},
            },
            "context": {
                "bias":      data["directional_bias"],
                "vector":    data["compression_vector"],
                "vol_regime": data["vol_regime"],
                "vol_spike": data["vol_spike"],
                "atr_pct":   data["atr_pct"],
                "bars_in_state": data["bars_in_state"],
            },
            "levels": {
                "anchor_ceiling":  data["anchor_ceiling"],
                "anchor_floor":    data["anchor_floor"],
                "cloud_center":    data["cloud_center"],
                "invalidation":    round(data["anchor_floor"] * 0.998, 4),
            },
            "action":      data["action"],
            "signal_tier": data["signal_tier"],
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
def scan_tickers(tickers: str, min_ci: Optional[float] = 0.0, only_prime: Optional[bool] = False) -> dict:
    """
    Scan multiple tickers for Base-4 convergence with optional filters.

    Args:
        tickers: Comma-separated list of ticker symbols (max 10)
        min_ci: Minimum CI score to include in results (default 0 = all)
        only_prime: If true, return only PRIME signals (CI>=78 AND SQI>=75)
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:10]
    results = []
    for t in ticker_list:
        try:
            data = _compute(t)
            if data["ci_score"] < (min_ci or 0):
                continue
            if only_prime and not data["is_prime"]:
                continue
            results.append({
                "ticker":      t,
                "signal_tier": data["signal_tier"],
                "action":      data["action"],
                "ci":          data["ci_score"],
                "sqi":         data["sqi_score"],
                "sets":        f"{data['sets_coiled']}/9",
                "is_prime":    data["is_prime"],
                "mtf_stack":   data["full_mtf_stack"],
                "state":       data["state"],
            })
        except Exception as e:
            results.append({"ticker": t, "error": str(e)})

    results.sort(key=lambda x: x.get("sqi", 0), reverse=True)
    return {
        "scan_time":    datetime.now(timezone.utc).isoformat(),
        "scanned":      len(ticker_list),
        "returned":     len(results),
        "prime_count":  sum(1 for r in results if r.get("is_prime")),
        "filters":      {"min_ci": min_ci, "only_prime": only_prime},
        "results":      results,
    }


@mcp.tool()
def get_council_verdict(ticker: str, oracle_score: Optional[float] = 0.0) -> dict:
    """
    Get a full Bull/Bear/Neutral counsel debate verdict from TradingAgents.
    The counsel agents receive the full Base-4 quantitative context and
    debate the trade before producing a final action recommendation.

    Note: This makes multiple Anthropic API calls — allow 20-60 seconds.
    Requires ANTHROPIC_API_KEY to be configured.

    Args:
        ticker: Stock or ETF symbol
        oracle_score: Optional Oracle composite score (0-100) for additional context
    """
    try:
        data = _compute(ticker)
        brief = {k: v for k, v in data["_brief"].items() if not k.startswith("_")}

        from sml_counsel_bridge import SMLCounselBridge, _result_to_api_dict
        bridge = SMLCounselBridge()
        if not bridge.is_available():
            return {
                "ticker": ticker.upper(),
                "error": "TradingAgents unavailable — ensure ANTHROPIC_API_KEY is set",
                "stub_action": "BUY" if data["is_prime"] else "HOLD",
                "signal_context": {"ci": data["ci_score"], "sqi": data["sqi_score"], "state": data["state"]},
            }

        b4_dict = _result_to_api_dict(ticker, data["_result"])
        verdict = asyncio.run(bridge.get_verdict(
            ticker=ticker.upper(),
            b4_result_dict=b4_dict,
            oracle_score=oracle_score or 0.0,
            brief_dict=brief,
        ))
        return {
            "ticker":     ticker.upper(),
            "action":     verdict.action,
            "confidence": round(verdict.confidence, 2),
            "reasoning":  verdict.reasoning,
            "risk_notes": verdict.risk_notes,
            "bull_thesis": verdict.bull_thesis,
            "bear_thesis": verdict.bear_thesis,
            "duration_s": verdict.duration_s,
            "signal_context": {
                "ci":    data["ci_score"],
                "sqi":   data["sqi_score"],
                "state": data["state"],
                "is_prime": data["is_prime"],
            },
            "execution_note": "Human confirmation required before any execution.",
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


# ─────────────────────────────────────────────────────────────────────────────
# INSTITUTION CATALOG TOOL
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_institution_catalog() -> dict:
    """
    Full product and service catalog for ScriptMasterLabs.
    Lists every engine, API, tool, and service in the institutional stack.
    Use this to understand the full scope of available capabilities.
    """
    return {
        "institution": "ScriptMasterLabs",
        "tagline": "Institutional Signal Intelligence — AI-Native Trading Infrastructure",
        "founded": "Solo founder, disabled veteran, Kinston NC",
        "status": "Active — paper mode | live capital pending 30-day validation",
        "regulatory": {
            "pdt_rule": "Eliminated June 4, 2026",
            "margin_minimum": "$2,000",
            "execution_model": "Human-in-the-loop confirmation gate on all orders",
        },
        "products": {
            "SML_Base4_Engine": {
                "name": "SML Base-4 Sovereign Harmonic Matrix",
                "version": "v6.2",
                "type": "Signal Engine (Python + Pine Script v6)",
                "description": (
                    "9-set EMA compression framework measuring multi-horizon convergence. "
                    "Self-calibrating CI (percentile-ranked). Dual-gate signal qualification. "
                    "MTF alignment via pandas resample. Margin-aware circuit breaker."
                ),
                "languages": ["Python", "Pine Script v6"],
                "key_metrics": {
                    "ema_sets": 9,
                    "ema_periods": "1 to 108 (25 unique, deduplicated)",
                    "multiplier_structure": "1:4:8:12 per set",
                    "ci_gate": 78,
                    "sqi_gate": 75,
                    "lookback": "252 bars",
                    "mtf_timeframes": ["4H", "Daily"],
                },
                "validated": "2026-06-04: SPY 8/9 sets CI 94.8, IWM 5/9 CI 85.9, QQQ 5/9 CI 91.1",
                "integration": "Python import, MCP tool, REST API, Pine Script overlay",
                "pricing": "Free (preview), 0.05 RLUSD (full), 0.10 RLUSD (brief)",
            },
            "SqueezeOS": {
                "name": "SqueezeOS v5.x",
                "type": "Full Trading OS",
                "description": (
                    "13+ specialized Python engines: Oracle, SML Fractal Cascade, Gamma Flow, "
                    "Delta Neutrality, Options Intelligence, IWM 0DTE, MMLE, Whale Stalker, "
                    "Battle Engine, Forced Move, Mean Reversion, KDP Sentinel, SR Patterns."
                ),
                "deployment": "Local (PM2) + Railway (cloud)",
                "brokers": ["Tradier (primary)", "Alpaca (fallback)", "Robinhood MCP (new)"],
                "mcp_server": "https://agent.robinhood.com/mcp/trading compatible",
                "pricing": "Free (demo), 0.03-0.10 RLUSD (paid endpoints via x402)",
            },
            "Oracle_Engine": {
                "name": "Oracle Engine",
                "type": "Signal Aggregator",
                "description": (
                    "Aggregates: Base-4 (new), Fractal Cascade, Gamma Flow, MMLE, RMRE Regime. "
                    "Emits BUY_PRIME / BUY / HOLD / SHIELD with Driver/Navigator payload."
                ),
                "thresholds": {"ignition": 82, "bull": 60, "watch": 40, "bear": 20},
                "new_in_v6_2": "Base-4 dual-gate as 5th scoring pillar — BUY_PRIME directive added",
            },
            "Counsel_Agent": {
                "name": "SML Counsel System",
                "type": "AI Agent Panel",
                "description": (
                    "TradingAgents multi-agent framework (Anthropic Claude). "
                    "Bull Researcher + Bear Researcher → Aggressive/Conservative/Neutral Debaters → "
                    "Portfolio Manager → Trader decision. Base-4 context injected as past_context."
                ),
                "llm": "claude-opus-4-7",
                "run_schedule": "5x daily (8:45, 9:35, 12:00, 15:00, 16:15 ET)",
                "payment": "Pays RLUSD for premium data via XRPL xrpl-py",
            },
            "Echo_Forge": {
                "name": "Echo Forge",
                "type": "Cross-Asset Pattern Memory Engine",
                "description": (
                    "Detects structurally similar historical market conditions. "
                    "DTW + cosine + euclidean similarity. Meme cycle phase detection. "
                    "MOASS candidate scoring. Grade A+ → institutional alerts."
                ),
                "port": 8001,
                "status": "Online",
                "data": "Polygon.io",
            },
            "OpenMythos": {
                "name": "OpenMythos",
                "type": "Recurrent-Depth Transformer",
                "description": (
                    "Custom RDT model for market signal analysis. "
                    "Latent reasoning chain for structured signal → narrative. "
                    "Port 8002."
                ),
                "port": 8002,
                "status": "Online",
            },
            "Argus_Omega": {
                "name": "Argus Omega",
                "type": "Institutional Fusion Intelligence Layer",
                "description": (
                    "4 subsystems: ARGUS (surveillance), ECHO FORGE (pattern), "
                    "LIQUIDITY GHOST (dark pool tracking), FALSE REALITY (manipulation detection). "
                    "Adjudicates conviction scores."
                ),
            },
            "IWM_ODTE_Desk": {
                "name": "IWM 0DTE Desk",
                "type": "Same-Day Options Engine",
                "description": "Specialized for IWM 0DTE options. Gamma band targeting. PDT-free post 2026-06-04.",
            },
            "Fee_Forge_XRPL": {
                "name": "Fee Forge / XRPL Payment Rail",
                "type": "Micropayment Infrastructure",
                "description": (
                    "x402 protocol on XRPL. RLUSD native settlement. "
                    "TipHawk (2% fee on tips), RLUSD Rails (0.5% checkout), "
                    "Copy Trader, Launchpad. No API keys required."
                ),
                "live_url": "https://four02proof.onrender.com",
                "npm": "@relayos/mcp-paywall",
            },
            "Signal_API": {
                "name": "SML Base-4 Signal API",
                "type": "Public REST API + MCP Server",
                "description": "FastAPI service. 14 endpoints. llms.txt. MCP manifest. Sitemap. x402 payment gate.",
                "port": 8010,
                "status": "Online",
                "endpoints": [
                    "GET /api/signal/preview/{ticker}",
                    "GET /api/signal/{ticker}",
                    "GET /api/intelligence-brief/{ticker}",
                    "GET /api/showcase",
                    "GET /api/scan",
                    "GET /api/methodology",
                    "GET /llms.txt",
                    "GET /.well-known/mcp.json",
                    "GET /sitemap.xml",
                ],
            },
        },
        "mcp_tools": [
            {"name": "get_signal_preview",     "cost": "free",          "description": "Truncated signal for any ticker"},
            {"name": "run_showcase",            "cost": "free",          "description": "Live 8-ticker scan"},
            {"name": "get_methodology",         "cost": "free",          "description": "Mathematical reference"},
            {"name": "check_health",            "cost": "free",          "description": "Service status"},
            {"name": "get_institution_catalog", "cost": "free",          "description": "This catalog"},
            {"name": "get_intelligence_brief",  "cost": "0.10 RLUSD",   "description": "Full narrative brief"},
            {"name": "get_full_signal",         "cost": "0.05 RLUSD",   "description": "All 9 sets + MTF + SQI"},
            {"name": "scan_tickers",            "cost": "0.05 RLUSD",   "description": "Multi-ticker filtered scan"},
            {"name": "get_council_verdict",     "cost": "0.25 RLUSD",   "description": "Full AI counsel debate"},
        ],
        "tech_stack": {
            "languages":   ["Python 3.12", "TypeScript", "Go", "Pine Script v6", "JavaScript"],
            "frameworks":  ["FastAPI", "FastMCP", "Flask", "LangGraph", "TradingAgents"],
            "ai":          ["Anthropic Claude (claude-opus-4-7)", "LiteLLM proxy", "OpenMythos RDT"],
            "data":        ["Tradier", "Alpaca", "Polygon.io", "Yahoo Finance", "Alpha Vantage"],
            "payment":     ["XRPL", "RLUSD", "x402 protocol"],
            "deployment":  ["PM2 (local)", "Railway (cloud)", "Docker", "Render"],
            "monitoring":  ["PM2 log rotation", "Discord webhooks", "Performance tracker"],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# LAUNCH
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "0"))
    if port:
        # Railway / remote deployment — serve over SSE so Smithery + MCP clients connect
        # SSE endpoint: https://your-url.railway.app/sse
        # MCP endpoint: https://your-url.railway.app/mcp  (streamable-http)
        try:
            mcp.run(transport="sse", host="0.0.0.0", port=port)
        except TypeError:
            # Older FastMCP versions
            mcp.run(transport="sse")
    else:
        # Local — stdio for Claude Desktop / Cursor
        mcp.run()
