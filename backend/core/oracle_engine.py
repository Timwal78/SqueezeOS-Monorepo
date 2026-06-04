"""
SML COMMAND CENTER — ORACLE ENGINE
Codename: ORACLE

Aggregates live signals from all SqueezeOS engines into a single
BUY / SELL / HOLD / SHIELD directive with full Driver/Navigator payload.

GitNexus-verified engine chain:
  sml_base4_engine.py   → SMLBase4Engine (dual-gate CI>=78 + SQI>=75) [NEW v6.2]
  gamma_flow_engine.py  → _signal_gamma_flip, analyze_fusion
  sml_engine.py         → compute_fractal_cascade, f_classify
  rmre_bridge.py        → compute_regime, _run_pipeline
  options_intelligence  → compute_flow_summary
  execution_engine.py   → get_gamma_walls
  data_providers.py     → TradierProvider (live quotes)
"""
import sys
import os
import logging
import time
from datetime import datetime

# Ensure backend root is on path so sml_base4_engine is importable
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
from typing import Optional

logger = logging.getLogger("Oracle")

# Sweet spot for 0DTE focus ($1–$60 range)
SWEET_SPOT_MIN = 1.0
SWEET_SPOT_MAX = 60.0

# Directive thresholds
IGNITION_THRESHOLD   = 82  # BUY — full send
BULL_THRESHOLD       = 60  # BUY — starter
WATCH_THRESHOLD      = 40  # HOLD — structure reclaim
BEAR_THRESHOLD       = 20  # SELL — distribution detected

# Historical fractal anchors for echo detection (Sep2020 GME baseline)
FRACTAL_ANCHORS = {
    "GME": [
        {"name": "Sep2020-Echo",  "multiplier": 1.0,  "target_pct": 0.68},
        {"name": "Jan2021-Echo",  "multiplier": 1.32, "target_pct": 1.20},
        {"name": "May2024-Echo",  "multiplier": 0.72, "target_pct": 0.45},
    ],
    "AMC": [
        {"name": "May2021-Echo",  "multiplier": 1.0,  "target_pct": 0.80},
        {"name": "May2024-Echo",  "multiplier": 0.78, "target_pct": 0.38},
    ],
    "IWM": [
        {"name": "0DTE-Gamma-Band", "multiplier": 1.0, "target_pct": 0.025},
    ],
}

# TP/Stop multipliers per regime
REGIME_MULTIPLIERS = {
    "ALPHA_EXPANSION": {"tp1": 1.15, "tp2": 1.30, "stop": 0.94},
    "MACRO_COLLAPSE":  {"tp1": 0.88, "tp2": 0.80, "stop": 1.04},
    "NEUTRAL":         {"tp1": 1.07, "tp2": 1.14, "stop": 0.96},
    "SHIELD":          {"tp1": None, "tp2": None,  "stop": None},
}


class OracleEngine:
    """
    Aggregates all SqueezeOS engine signals for a given symbol
    and emits a single structured Oracle directive.
    """

    def __init__(self, services: dict):
        """
        services: dict provided by core/legacy.py _services registry
          Expected keys: 'dm', 'whale_stalker'
          Optional keys: 'sml', 'mmle', 'gamma_flow', 'rmre', 'options_intel'
        """
        self.services = services or {}
        self._cache = {}
        self._cache_ttl = 60  # seconds

    def _get_service(self, name):
        return self.services.get(name)

    def _cached(self, key, fn, ttl=None):
        ttl = ttl or self._cache_ttl
        entry = self._cache.get(key)
        if entry and (time.time() - entry["ts"]) < ttl:
            return entry["data"]
        result = fn()
        self._cache[key] = {"ts": time.time(), "data": result}
        return result

    def _get_quote(self, symbol: str) -> dict:
        """Pull live quote from Tradier via DataManager."""
        dm = self._get_service("dm")
        if not dm:
            return {}
        try:
            quotes = dm.get_quotes([symbol])
            return quotes.get(symbol, {})
        except Exception as e:
            logger.error(f"[Oracle] Quote fetch failed for {symbol}: {e}")
            return {}

    def _get_gamma_walls(self, symbol: str, price: float) -> dict:
        """Pull gamma wall levels from ExecutionEngine."""
        try:
            from execution_engine import ExecutionEngine
            from rmre_bridge import RMREBridge
            dm = self._get_service("dm")
            if not dm:
                return {}
            rmre = RMREBridge()
            ee = ExecutionEngine(schwab_api=dm, rmre_bridge=rmre)
            walls = ee.get_gamma_walls(symbol)
            if not walls:
                return {}
            # Find nearest wall above and below current price
            above = [w for w in walls if w.get("strike", 0) > price]
            below = [w for w in walls if w.get("strike", 0) <= price]
            nearest_above = min(above, key=lambda w: w["strike"] - price, default=None)
            nearest_below = max(below, key=lambda w: w["strike"], default=None)
            return {
                "wall_above": nearest_above.get("strike") if nearest_above else None,
                "wall_below": nearest_below.get("strike") if nearest_below else None,
                "wall_strength_above": nearest_above.get("gex", 0) if nearest_above else 0,
                "wall_strength_below": nearest_below.get("gex", 0) if nearest_below else 0,
            }
        except Exception as e:
            logger.warning(f"[Oracle] Gamma walls unavailable for {symbol}: {e}")
            return {}

    def _get_regime(self, symbol: str) -> str:
        """Pull beast regime from RMREBridge."""
        try:
            from rmre_bridge import RMREBridge
            bridge = RMREBridge()
            result = bridge.compute_regime(symbol)
            if isinstance(result, dict):
                return result.get("regime", "NEUTRAL")
            return str(result) if result else "NEUTRAL"
        except Exception as e:
            logger.warning(f"[Oracle] Regime unavailable for {symbol}: {e}")
            return "NEUTRAL"

    def _get_fractal_signal(self, symbol: str, price: float) -> dict:
        """
        Pull fractal cascade from SMLEngine and match against known echoes.
        Returns the best matching fractal anchor and confidence.
        """
        try:
            sml = self._get_service("sml")
            if not sml:
                return {}
            result = sml.compute_all(symbol)
            score = result.get("fractal_score", 0) if isinstance(result, dict) else 0
            anchors = FRACTAL_ANCHORS.get(symbol, [])
            best = max(anchors, key=lambda a: a["multiplier"] * score, default=None)
            return {
                "fractal_score": score,
                "fractal_match": best["name"] if best else "None",
                "target_pct": best["target_pct"] if best else 0,
            }
        except Exception as e:
            logger.warning(f"[Oracle] Fractal signal unavailable for {symbol}: {e}")
            return {}

    def _get_mmle_signal(self, symbol: str) -> dict:
        """Pull VPIN and Greeks from MMLE engine."""
        try:
            from mmle_engine import MMLeEngine
            mmle_engines = {}
            if symbol not in mmle_engines:
                mmle_engines[symbol] = MMLeEngine()
            dm = self._get_service("dm")
            if not dm:
                return {}
            bars = dm.get_historical_bars(symbol, timeframe="1Min", limit=200)
            if not bars:
                return {}
            result = mmle_engines[symbol].analyze(symbol, bars)
            return {
                "vpin": result.get("vpin", 0),
                "charm": result.get("charm", 0),
                "vanna": result.get("vanna", 0),
                "axis_collapse": result.get("axis_collapse", False),
                "mmle_signal": result.get("signal", "NEUTRAL"),
            }
        except Exception as e:
            logger.warning(f"[Oracle] MMLE unavailable for {symbol}: {e}")
            return {}

    def _get_gamma_flow(self, symbol: str) -> dict:
        """Pull gamma flip signal from GammaFlowEngine."""
        try:
            from gamma_flow_engine import GammaFlowEngine
            dm = self._get_service("dm")
            if not dm:
                return {}
            polygon = getattr(dm, 'polygon', None) or dm
            watchlist = [symbol]
            gfe = GammaFlowEngine(polygon=polygon, watchlist=watchlist)
            result = gfe.process_ticker(symbol)
            if not result:
                return {}
            return {
                "gamma_flip": result.get("gamma_flip", False),
                "gamma_regime": result.get("regime", "NEUTRAL"),
                "gamma_score": result.get("score", 0),
            }
        except Exception as e:
            logger.warning(f"[Oracle] Gamma flow unavailable for {symbol}: {e}")
            return {}

    def _get_sml_base4_signal(self, symbol: str) -> dict:
        """
        Compute SML Base-4 Sovereign Harmonic Matrix for the symbol.
        Uses DataManager historical bars (Tradier/Alpaca) if available;
        falls back to yfinance for paper/dev mode.

        Dual-gate logic:
          CI >= 78 (structural gate)  AND  SQI >= 75 (execution gate) = PRIME
          CI >= 78 only               = structural confirmation (+12 pts)
          CI < 78                     = chop zone warning (-5 pts)
        """
        try:
            from sml_base4_engine import SMLBase4Engine, SMLBase4Config, sml_base4_oracle_contribution
            import pandas as pd

            df = None
            dm = self._get_service("dm")

            # DataManager path (Tradier / Alpaca live bars)
            if dm:
                try:
                    bars = dm.get_historical_bars(symbol, timeframe="1H", limit=500)
                    if bars and len(bars) >= 100:
                        df = pd.DataFrame([{
                            "open":   b.get("open",   b.get("o", 0)),
                            "high":   b.get("high",   b.get("h", 0)),
                            "low":    b.get("low",    b.get("l", 0)),
                            "close":  b.get("close",  b.get("c", 0)),
                            "volume": b.get("volume", b.get("v", 0)),
                        } for b in bars])
                        timestamps = [b.get("timestamp", b.get("t", "")) for b in bars]
                        df.index = pd.to_datetime(timestamps, utc=True, errors="coerce")
                        df = df.dropna()
                except Exception as dm_err:
                    logger.debug("[Oracle/B4] DataManager bars failed for %s: %s", symbol, dm_err)

            # yfinance fallback (paper mode / development)
            if df is None or len(df) < 100:
                import yfinance as yf
                raw = yf.download(symbol, period="1y", interval="1h", auto_adjust=True, progress=False)
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [c[0].lower() for c in raw.columns]
                else:
                    raw.columns = [c.lower() for c in raw.columns]
                df = raw.dropna()

            if len(df) < 50:
                return {"available": False, "reason": "insufficient data"}

            # Engine cache — one instance per symbol, stateful for bars_in_state tracking
            if not hasattr(self, "_sml_b4_engines"):
                self._sml_b4_engines = {}
            if symbol not in self._sml_b4_engines:
                self._sml_b4_engines[symbol] = SMLBase4Engine(SMLBase4Config(
                    ci_structural_gate=78,
                    sqi_prime_level=75,
                    htf1_resample="4h",
                    htf2_resample="1D",
                ))

            result = self._sml_b4_engines[symbol].compute(df)
            contribution = sml_base4_oracle_contribution(result, weight=25.0)

            return {
                "available":          True,
                "state":              result.state.value,
                "total_coiled":       result.total_coiled,
                "harmonic_score":     round(result.harmonic_score, 2),
                "ci_gate_passed":     result.sqi.ci_gate_passed,
                "sqi_total":          round(result.sqi.total, 2),
                "is_prime":           result.sqi.is_prime,
                "full_mtf_stack":     result.full_mtf_stack,
                "mtf_aligned":        result.mtf_aligned,
                "directional_bias":   result.directional_bias.value,
                "compression_vector": result.compression_vector.value,
                "anchor_ceiling":     round(result.anchor_ceiling, 4),
                "anchor_floor":       round(result.anchor_floor, 4),
                "bars_in_state":      result.bars_in_state,
                "vol_regime":         result.vol_regime,
                "oracle_contribution": round(contribution, 2),
            }

        except Exception as exc:
            logger.warning("[Oracle/B4] SML Base-4 unavailable for %s: %s", symbol, exc)
            return {"available": False, "reason": str(exc)}

    def _score_to_directive(self, score: float, regime: str, gamma_flip: bool, vpin: float) -> str:
        """Convert composite score to BUY/SELL/HOLD/SHIELD directive."""
        if regime == "SHIELD" or score < 5:
            return "SHIELD"
        if regime == "MACRO_COLLAPSE" and vpin > 0.75:
            return "SELL"
        if score >= IGNITION_THRESHOLD and gamma_flip:
            return "BUY"
        if score >= BULL_THRESHOLD:
            return "BUY"
        if score >= WATCH_THRESHOLD:
            return "HOLD"
        if regime == "MACRO_COLLAPSE" and score < WATCH_THRESHOLD:
            return "SELL"
        return "HOLD"

    def _build_reason(self, directive: str, fractal_match: str, gamma_flip: bool,
                      vpin: float, regime: str, score: float, b4: dict = None) -> str:
        """One-sentence Driver/Navigator reason string."""
        parts = []

        # SML Base-4 state — highest priority descriptor
        if b4 and b4.get("available"):
            b4_state = b4.get("state", "")
            if b4.get("is_prime"):
                parts.append(
                    f"Base-4 PRIME SIGNAL ({b4.get('total_coiled', 0)}/9 sets coiled, "
                    f"CI {b4.get('harmonic_score', 0):.0f}, SQI {b4.get('sqi_total', 0):.0f})"
                )
            elif b4.get("ci_gate_passed"):
                parts.append(
                    f"Base-4 structural compression confirmed ({b4.get('total_coiled', 0)}/9 sets, "
                    f"CI {b4.get('harmonic_score', 0):.0f})"
                )
            elif b4_state == "SCANNING":
                parts.append("Base-4 matrix in chop zone — EMA grid not compressed")

        if gamma_flip:
            parts.append("gamma flip confirmed above VWAP")
        if fractal_match and fractal_match != "None":
            parts.append(f"{fractal_match} fractal echo active")
        if vpin > 0.65:
            parts.append(f"order toxicity elevated ({round(vpin * 100)}% VPIN)")
        if regime == "ALPHA_EXPANSION":
            parts.append("regime in Alpha Expansion")
        elif regime == "MACRO_COLLAPSE":
            parts.append("macro collapse pressure detected")
        if not parts:
            parts.append(f"composite score {round(score)}")
        return ". ".join(parts).capitalize() + "."

    def analyze(self, symbol: str) -> dict:
        """
        Main Oracle entry point. Returns full Driver/Navigator payload.
        All data is live from SqueezeOS engines — no mock data.
        """
        ts = datetime.now().isoformat()
        logger.info(f"[Oracle] Analyzing {symbol}...")

        # 1. Live quote
        quote = self._cached(f"quote_{symbol}", lambda: self._get_quote(symbol), ttl=30)
        price = quote.get("price", 0)
        volume = quote.get("volume", 0)

        if price == 0:
            logger.warning(f"[Oracle] No price data for {symbol} — SHIELD")
            return {
                "symbol": symbol, "timestamp": ts,
                "directive": "SHIELD", "confidence": 0, "price": 0,
                "reason": "No live price data. Market may be closed or Tradier unavailable.",
                "sweet_spot": False, "regime": "SHIELD",
            }

        sweet_spot = SWEET_SPOT_MIN <= price <= SWEET_SPOT_MAX

        # 2. Parallel engine calls (SML B4 cached 90s — heavier computation)
        gamma_walls = self._cached(f"walls_{symbol}", lambda: self._get_gamma_walls(symbol, price))
        regime      = self._cached(f"regime_{symbol}", lambda: self._get_regime(symbol))
        fractal     = self._cached(f"fractal_{symbol}", lambda: self._get_fractal_signal(symbol, price))
        mmle        = self._cached(f"mmle_{symbol}", lambda: self._get_mmle_signal(symbol))
        gflow       = self._cached(f"gflow_{symbol}", lambda: self._get_gamma_flow(symbol))
        b4          = self._cached(f"b4_{symbol}", lambda: self._get_sml_base4_signal(symbol), ttl=90)

        # 3. Composite scoring
        score = 0
        score += fractal.get("fractal_score", 0) * 0.30
        score += mmle.get("vpin", 0) * 40          # VPIN 0-1 → 0-40 pts
        score += gflow.get("gamma_score", 0) * 0.30
        if gflow.get("gamma_flip"):
            score += 15
        if regime == "ALPHA_EXPANSION":
            score += 10
        elif regime == "MACRO_COLLAPSE":
            score -= 15
        if mmle.get("axis_collapse"):
            score -= 20

        # ── SML Base-4 dual-gate contribution (up to +25 pts) ────────────
        # Prime (CI>=78 AND SQI>=75 AND MTF aligned): full weight
        # Structural only (CI>=78, SQI not yet at threshold): half weight
        # Chop zone (CI<78): noise penalty — EMAs lack structural commitment
        if b4.get("available"):
            b4_contrib = b4.get("oracle_contribution", 0.0)
            if b4.get("is_prime"):
                score += b4_contrib
            elif b4.get("ci_gate_passed"):
                score += b4_contrib * 0.5
            else:
                score -= 5   # CI below structural gate — market is in chop zone

        score = max(0, min(100, score))

        # 4. Base directive from existing logic
        vpin       = mmle.get("vpin", 0)
        gamma_flip = gflow.get("gamma_flip", False)
        directive  = self._score_to_directive(score, regime, gamma_flip, vpin)

        # ── SML B4 prime upgrade ──────────────────────────────────────────
        # BUY → BUY_PRIME when Base-4 dual-gate passes and score clears BULL_THRESHOLD
        if directive == "BUY" and b4.get("is_prime"):
            directive = "BUY_PRIME"

        # 5. Price targets
        mults = REGIME_MULTIPLIERS.get(regime, REGIME_MULTIPLIERS["NEUTRAL"])
        tp1 = round(price * mults["tp1"], 2) if mults["tp1"] else None
        tp2 = round(price * mults["tp2"], 2) if mults["tp2"] else None
        stop = round(price * mults["stop"], 2) if mults["stop"] else None

        # Override for SELL: flip TP/stop
        if directive == "SELL":
            tp1 = round(price * REGIME_MULTIPLIERS["MACRO_COLLAPSE"]["tp1"], 2)
            tp2 = round(price * REGIME_MULTIPLIERS["MACRO_COLLAPSE"]["tp2"], 2)
            stop = round(price * REGIME_MULTIPLIERS["MACRO_COLLAPSE"]["stop"], 2)

        # 6. Fractal target
        target_pct = fractal.get("target_pct", 0)
        fractal_target = round(price * (1 + target_pct), 2) if target_pct else None

        # 7. Build reason (now includes Base-4 narrative)
        reason = self._build_reason(
            directive,
            fractal.get("fractal_match", "None"),
            gamma_flip, vpin, regime, score, b4=b4
        )

        # 8. Base-4 summary for payload (strip internal fields)
        b4_payload = {k: v for k, v in b4.items() if not k.startswith("_")} if b4.get("available") else {"available": False}

        payload = {
            "symbol":           symbol,
            "timestamp":        ts,
            "directive":        directive,
            "confidence":       round(score),
            "price":            price,
            "volume":           volume,
            "tp1":              tp1,
            "tp2":              tp2,
            "stop":             stop,
            "fractal_target":   fractal_target,
            "reason":           reason,
            "sweet_spot":       sweet_spot,
            "regime":           regime,
            "gamma_flip":       gamma_flip,
            "gamma_wall_above": gamma_walls.get("wall_above"),
            "gamma_wall_below": gamma_walls.get("wall_below"),
            "vpin":             round(vpin, 3),
            "charm":            round(mmle.get("charm", 0), 4),
            "vanna":            round(mmle.get("vanna", 0), 4),
            "axis_collapse":    mmle.get("axis_collapse", False),
            "fractal_match":    fractal.get("fractal_match", "None"),
            "fractal_score":    round(fractal.get("fractal_score", 0)),
            "sml_base4":        b4_payload,
        }

        logger.info(f"[Oracle] {symbol} → {directive} | Score: {round(score)} | {reason}")
        return payload


# ── Multi-symbol batch ──
def run_oracle_batch(symbols: list, services: dict) -> dict:
    engine = OracleEngine(services)
    results = {}
    for sym in symbols:
        try:
            results[sym] = engine.analyze(sym)
        except Exception as e:
            logger.error(f"[Oracle] Batch error for {sym}: {e}")
            results[sym] = {
                "symbol": sym, "directive": "SHIELD", "confidence": 0,
                "reason": f"Engine error: {e}", "timestamp": datetime.now().isoformat()
            }
    return results


ORACLE_SYMBOLS = ["GME", "AMC", "IWM"]
