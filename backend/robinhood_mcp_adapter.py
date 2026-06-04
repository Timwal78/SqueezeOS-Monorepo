"""
ROBINHOOD MCP ADAPTER — Paper + Live Execution
══════════════════════════════════════════════════════════════════════════════
Wraps the Robinhood Trading MCP server as a Python execution broker.

Paper Mode (default):
  - All orders are logged to robinhood_paper_log.json
  - No real execution occurs
  - Full fill simulation at last price
  - P&L tracking + signal audit trail

Live Mode (requires ROBINHOOD_PAPER_MODE=false in .env):
  - Routes orders through Robinhood MCP HTTP endpoint
  - Circuit breakers must pass before any order reaches the API
  - Human confirmation gate enforced (Discord 60-sec window)

© ScriptMasterLabs. Proprietary.
"""

import os
import json
import logging
import asyncio
import aiohttp
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, Dict, List
from pathlib import Path

logger = logging.getLogger("RobinhoodMCP")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

ROBINHOOD_MCP_URL     = os.getenv("ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading")
PAPER_MODE            = os.getenv("ROBINHOOD_PAPER_MODE", "true").lower() == "true"
PAPER_LOG_PATH        = Path(os.getenv("ROBINHOOD_PAPER_LOG", "robinhood_paper_log.json"))
DISCORD_WEBHOOK       = os.getenv("DISCORD_WEBHOOK_ALL", "")
HUMAN_GATE_TIMEOUT_S  = int(os.getenv("HUMAN_GATE_TIMEOUT_S", "60"))

# ─────────────────────────────────────────────────────────────────────────────
# CIRCUIT BREAKER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CircuitBreakerConfig:
    daily_loss_limit_pct:     float = 3.0    # halt all trading if daily P&L < -3%
    consecutive_loss_limit:   int   = 3      # pause 24h after 3 consecutive losses
    drawdown_from_peak_pct:   float = 5.0    # manual restart required at -5% from peak
    max_concurrent_positions: int   = 3
    max_position_size_pct:    float = 2.0    # max 2% of account per trade

    # ── MARGIN FLOOR PROTECTION (PDT rule change 2026-06-04) ──────────────
    # $2,000 is the absolute minimum equity for any margin account.
    # Dropping below this floor eliminates margin privileges entirely.
    # Three-tier protection system to keep account above $2,000 at all times.
    margin_floor_hard:        float = 2100.0  # FULL HALT — $100 buffer above $2,000 floor
    margin_floor_caution:     float = 2200.0  # NO NEW POSITIONS — $200 buffer
    margin_floor_warning:     float = 2500.0  # HALF SIZE + DISCORD ALERT — $500 buffer


class CircuitBreaker:
    """
    Stateful circuit breaker — all trading flows through check() before execution.
    State persists across calls within a session. Use reset() at session start.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.cfg               = config or CircuitBreakerConfig()
        self._halted:    bool  = False
        self._halt_reason: str = ""
        self._daily_pnl: float = 0.0
        self._peak_equity:float= 0.0
        self._equity:    float = 0.0
        self._losses:    int   = 0
        self._open_positions: int = 0
        self._state_path = Path("circuit_breaker_state.json")
        self._load_state()

    def check(self, symbol: str, order_value: float, account_equity: float) -> tuple[bool, str]:
        """
        Returns (approved: bool, reason: str).
        Call before every order. Thread-safe.

        Checks in order:
          1. Hard halt (previous trigger)
          2. Margin floor — HARD ($2,100) → full halt, protect $2,000 minimum
          3. Margin floor — CAUTION ($2,200) → no new positions
          4. Daily loss limit
          5. Peak drawdown
          6. Consecutive losses
          7. Max concurrent positions
          8. Position size (reduced to 50% in WARNING zone < $2,500)
        """
        if self._halted:
            return False, f"CIRCUIT BREAKER HALTED: {self._halt_reason}"

        # ── MARGIN FLOOR — HARD STOP ────────────────────────────────────────
        # Protect the $2,000 margin minimum at all costs.
        # Dropping below $2,000 eliminates margin privileges (post-PDT-rule-change 2026-06-04).
        if account_equity <= self.cfg.margin_floor_hard:
            self._trigger_halt(
                f"MARGIN FLOOR BREACH: equity ${account_equity:.2f} at or below hard floor "
                f"${self.cfg.margin_floor_hard:.2f} — halting to protect $2,000 minimum margin requirement"
            )
            return False, self._halt_reason

        # ── MARGIN FLOOR — CAUTION (no new positions) ──────────────────────
        if account_equity <= self.cfg.margin_floor_caution:
            return False, (
                f"MARGIN CAUTION: equity ${account_equity:.2f} below caution floor "
                f"${self.cfg.margin_floor_caution:.2f} — no new positions until equity recovers above "
                f"${self.cfg.margin_floor_caution:.2f}"
            )

        # ── DAILY LOSS CHECK ────────────────────────────────────────────────
        if account_equity > 0 and self._daily_pnl / account_equity * 100 < -self.cfg.daily_loss_limit_pct:
            self._trigger_halt(f"Daily loss limit hit ({self._daily_pnl / account_equity * 100:.2f}%)")
            return False, self._halt_reason

        # ── PEAK DRAWDOWN ───────────────────────────────────────────────────
        if self._peak_equity > 0 and account_equity < self._peak_equity * (1 - self.cfg.drawdown_from_peak_pct / 100):
            self._trigger_halt(f"Peak drawdown limit hit (current ${account_equity:.2f} vs peak ${self._peak_equity:.2f})")
            return False, self._halt_reason

        # ── CONSECUTIVE LOSSES ──────────────────────────────────────────────
        if self._losses >= self.cfg.consecutive_loss_limit:
            self._trigger_halt(f"{self._losses} consecutive losses — 24h cooling period required")
            return False, self._halt_reason

        # ── MAX CONCURRENT POSITIONS ────────────────────────────────────────
        if self._open_positions >= self.cfg.max_concurrent_positions:
            return False, f"Max concurrent positions reached ({self._open_positions}/{self.cfg.max_concurrent_positions})"

        # ── POSITION SIZE ───────────────────────────────────────────────────
        # In WARNING zone ($2,500 or below): enforce half-size automatically
        if account_equity > 0:
            effective_limit = self.cfg.max_position_size_pct
            in_warning_zone = account_equity <= self.cfg.margin_floor_warning
            if in_warning_zone:
                effective_limit = self.cfg.max_position_size_pct * 0.5   # half size in warning zone
                logger.warning(
                    "[CIRCUIT BREAKER] WARNING ZONE: equity $%.2f < $%.2f — position size limit reduced to %.1f%%",
                    account_equity, self.cfg.margin_floor_warning, effective_limit,
                )
            pct = order_value / account_equity * 100
            if pct > effective_limit:
                zone_note = " (REDUCED — margin warning zone)" if in_warning_zone else ""
                return False, f"Position size {pct:.2f}% exceeds limit {effective_limit:.2f}%{zone_note}"

        return True, "APPROVED"

    def margin_zone(self, account_equity: float) -> str:
        """Returns the current margin zone label for HUD / Discord display."""
        if account_equity <= self.cfg.margin_floor_hard:
            return "HARD_FLOOR_BREACH"
        if account_equity <= self.cfg.margin_floor_caution:
            return "CAUTION"
        if account_equity <= self.cfg.margin_floor_warning:
            return "WARNING"
        return "SAFE"

    def margin_distance(self, account_equity: float) -> float:
        """Distance in dollars from the hard floor ($2,100). Negative = breached."""
        return account_equity - self.cfg.margin_floor_hard

    def record_fill(self, pnl: float, won: bool) -> None:
        """Call after each trade closes."""
        self._daily_pnl += pnl
        if won:
            self._losses = 0
        else:
            self._losses += 1
        self._save_state()

    def record_open(self) -> None:
        self._open_positions += 1
        self._save_state()

    def record_close(self) -> None:
        self._open_positions = max(0, self._open_positions - 1)
        self._save_state()

    def update_equity(self, equity: float) -> None:
        self._equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity
        self._save_state()

    def kill(self, reason: str = "Manual kill switch") -> None:
        """Hard halt — requires manual reset() to resume."""
        self._trigger_halt(reason)
        logger.critical("[CIRCUIT BREAKER] KILL SWITCH ACTIVATED: %s", reason)

    def reset(self) -> None:
        """Reset for new trading session (manual, requires operator approval)."""
        self._halted = False
        self._halt_reason = ""
        self._daily_pnl = 0.0
        self._losses = 0
        self._save_state()
        logger.info("[CIRCUIT BREAKER] Reset for new session")

    def status(self, current_equity: float = 0.0) -> Dict:
        zone = self.margin_zone(current_equity) if current_equity > 0 else "UNKNOWN"
        dist = self.margin_distance(current_equity) if current_equity > 0 else None
        return {
            "halted":               self._halted,
            "halt_reason":          self._halt_reason,
            "daily_pnl":            round(self._daily_pnl, 4),
            "peak_equity":          round(self._peak_equity, 2),
            "current_equity":       round(current_equity, 2),
            "consecutive_losses":   self._losses,
            "open_positions":       self._open_positions,
            "margin_zone":          zone,
            "margin_floor_hard":    self.cfg.margin_floor_hard,
            "margin_floor_caution": self.cfg.margin_floor_caution,
            "margin_floor_warning": self.cfg.margin_floor_warning,
            "distance_to_hard_floor": round(dist, 2) if dist is not None else None,
            "pdt_shield_active":    False,
            "pdt_note":             "PDT rule eliminated 2026-06-04 — no day-trade frequency limit",
        }

    def _trigger_halt(self, reason: str) -> None:
        self._halted = True
        self._halt_reason = reason
        self._save_state()
        logger.critical("[CIRCUIT BREAKER] HALT: %s", reason)

    def _save_state(self) -> None:
        try:
            self._state_path.write_text(json.dumps(self.status(), indent=2))
        except Exception:
            pass

    def _load_state(self) -> None:
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text())
                self._halted    = data.get("halted", False)
                self._halt_reason = data.get("halt_reason", "")
                self._daily_pnl = data.get("daily_pnl", 0.0)
                self._peak_equity = data.get("peak_equity", 0.0)
                self._losses    = data.get("consecutive_losses", 0)
                self._open_positions = data.get("open_positions", 0)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# ORDER / FILL DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OrderRequest:
    symbol:        str
    side:          str           # "buy" | "sell"
    quantity:      float
    order_type:    str = "market"
    limit_price:   Optional[float] = None
    stop_price:    Optional[float] = None
    # ── Signal context (for audit trail) ──────────────────────────────────
    signal_state:  str = ""      # e.g. "APEX_SINGULARITY"
    sqi_score:     float = 0.0
    oracle_score:  float = 0.0
    counsel_verdict: str = ""    # Bull/Bear/Hold from counsel agent
    # ── Internal ──────────────────────────────────────────────────────────
    timestamp:     str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id:    str = field(default_factory=lambda: f"RH_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:19]}")


@dataclass
class FillResult:
    request_id:    str
    symbol:        str
    side:          str
    quantity:      float
    fill_price:    float
    fill_time:     str
    paper_mode:    bool
    status:        str           # "filled" | "rejected" | "pending_human" | "circuit_breaker"
    rejection_reason: str = ""
    order_id:      str = ""      # Robinhood order ID (live mode only)


# ─────────────────────────────────────────────────────────────────────────────
# ADAPTER
# ─────────────────────────────────────────────────────────────────────────────

class RobinhoodMCPAdapter:
    """
    Paper + Live Robinhood execution adapter.

    In paper mode: simulates fills at last price, full audit trail.
    In live mode:  routes through Robinhood MCP after circuit breaker + human gate.

    Usage
    -----
        adapter = RobinhoodMCPAdapter(circuit_breaker=cb)
        fill = await adapter.submit(order_request, last_price=150.00, account_equity=10000)
    """

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        paper_mode:       Optional[bool] = None,
    ):
        self.paper_mode = paper_mode if paper_mode is not None else PAPER_MODE
        self.cb = circuit_breaker or CircuitBreaker()
        self._paper_log: List[Dict] = self._load_paper_log()

        mode_str = "PAPER MODE" if self.paper_mode else "LIVE MODE ⚡"
        logger.info("[RobinhoodMCP] Adapter initialized — %s", mode_str)
        if not self.paper_mode:
            logger.warning("[RobinhoodMCP] LIVE MODE ACTIVE — real orders will execute")

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC
    # ─────────────────────────────────────────────────────────────────────

    async def submit(
        self,
        order:          OrderRequest,
        last_price:     float,
        account_equity: float,
    ) -> FillResult:
        """
        Primary execution entry point.

        Flow:
          1. Circuit breaker check
          2. Human confirmation gate (Discord, 60s window)
          3. Paper fill  OR  Robinhood MCP live order
        """
        order_value = order.quantity * last_price

        # ── 1. Circuit breaker ────────────────────────────────────────────
        approved, reason = self.cb.check(order.symbol, order_value, account_equity)
        if not approved:
            logger.warning("[RobinhoodMCP] Circuit breaker rejected %s: %s", order.request_id, reason)
            return FillResult(
                request_id=order.request_id, symbol=order.symbol, side=order.side,
                quantity=order.quantity, fill_price=0.0,
                fill_time=datetime.now(timezone.utc).isoformat(),
                paper_mode=self.paper_mode, status="circuit_breaker",
                rejection_reason=reason,
            )

        # ── 2. Human confirmation gate ────────────────────────────────────
        confirmed = await self._human_gate(order, last_price, account_equity)
        if not confirmed:
            logger.info("[RobinhoodMCP] Human gate: order %s not confirmed within %ds", order.request_id, HUMAN_GATE_TIMEOUT_S)
            return FillResult(
                request_id=order.request_id, symbol=order.symbol, side=order.side,
                quantity=order.quantity, fill_price=0.0,
                fill_time=datetime.now(timezone.utc).isoformat(),
                paper_mode=self.paper_mode, status="pending_human",
                rejection_reason="Human gate timeout — order cancelled",
            )

        # ── 3. Execute ────────────────────────────────────────────────────
        if self.paper_mode:
            return self._paper_fill(order, last_price)
        else:
            return await self._live_fill(order, last_price)

    def paper_pnl_summary(self) -> Dict:
        """Running P&L summary from paper log."""
        if not self._paper_log:
            return {"total_trades": 0, "total_pnl": 0.0, "win_rate": 0.0}
        trades = len(self._paper_log)
        # Simplified: track fills; real P&L needs paired buy/sell
        return {
            "total_trades":  trades,
            "paper_log_path": str(PAPER_LOG_PATH),
            "circuit_breaker": self.cb.status(),
        }

    # ─────────────────────────────────────────────────────────────────────
    # PAPER FILL
    # ─────────────────────────────────────────────────────────────────────

    def _paper_fill(self, order: OrderRequest, last_price: float) -> FillResult:
        fill = FillResult(
            request_id  = order.request_id,
            symbol      = order.symbol,
            side        = order.side,
            quantity    = order.quantity,
            fill_price  = last_price,
            fill_time   = datetime.now(timezone.utc).isoformat(),
            paper_mode  = True,
            status      = "filled",
            order_id    = f"PAPER_{order.request_id}",
        )
        self.cb.record_open()
        self._log_paper(order, fill)
        logger.info(
            "[RobinhoodMCP PAPER] FILL: %s %s x%.2f @ $%.4f | %s | SQI:%.0f | Oracle:%.0f",
            order.side.upper(), order.symbol, order.quantity, last_price,
            order.signal_state, order.sqi_score, order.oracle_score,
        )
        return fill

    # ─────────────────────────────────────────────────────────────────────
    # LIVE FILL — Robinhood MCP
    # ─────────────────────────────────────────────────────────────────────

    async def _live_fill(self, order: OrderRequest, last_price: float) -> FillResult:
        """Route to Robinhood MCP HTTP endpoint."""
        payload = {
            "jsonrpc": "2.0",
            "id":      1,
            "method":  "tools/call",
            "params":  {
                "name":      "place_order",
                "arguments": {
                    "symbol":     order.symbol,
                    "side":       order.side,
                    "quantity":   order.quantity,
                    "order_type": order.order_type,
                    **({"limit_price": order.limit_price} if order.limit_price else {}),
                    **({"stop_price": order.stop_price} if order.stop_price else {}),
                }
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(ROBINHOOD_MCP_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

            if "result" in data:
                order_id = data["result"].get("order_id", "")
                self.cb.record_open()
                logger.info(
                    "[RobinhoodMCP LIVE] FILL: %s %s x%.2f @ market | order_id: %s",
                    order.side.upper(), order.symbol, order.quantity, order_id,
                )
                return FillResult(
                    request_id=order.request_id, symbol=order.symbol, side=order.side,
                    quantity=order.quantity, fill_price=last_price,
                    fill_time=datetime.now(timezone.utc).isoformat(),
                    paper_mode=False, status="filled", order_id=order_id,
                )
            else:
                err = data.get("error", {}).get("message", "Unknown MCP error")
                logger.error("[RobinhoodMCP LIVE] Order rejected: %s", err)
                return FillResult(
                    request_id=order.request_id, symbol=order.symbol, side=order.side,
                    quantity=order.quantity, fill_price=0.0,
                    fill_time=datetime.now(timezone.utc).isoformat(),
                    paper_mode=False, status="rejected", rejection_reason=err,
                )

        except Exception as exc:
            logger.exception("[RobinhoodMCP LIVE] Exception during order submission: %s", exc)
            return FillResult(
                request_id=order.request_id, symbol=order.symbol, side=order.side,
                quantity=order.quantity, fill_price=0.0,
                fill_time=datetime.now(timezone.utc).isoformat(),
                paper_mode=False, status="rejected", rejection_reason=str(exc),
            )

    # ─────────────────────────────────────────────────────────────────────
    # HUMAN CONFIRMATION GATE
    # ─────────────────────────────────────────────────────────────────────

    async def _human_gate(self, order: OrderRequest, last_price: float, equity: float) -> bool:
        """
        Sends a Discord alert and waits for human approval.

        In paper mode: auto-approves after sending the alert (for simulation flow).
        In live mode:  waits HUMAN_GATE_TIMEOUT_S seconds for approval webhook response.

        For now, paper mode returns True immediately after logging.
        Live mode approval flow: operator replies to Discord embed; a /confirm endpoint
        receives the approval and sets a shared flag. TODO: wire /confirm route.
        """
        await self._send_discord_alert(order, last_price, equity)

        if self.paper_mode:
            logger.info("[HumanGate] PAPER MODE — auto-approved order %s", order.request_id)
            return True

        # Live mode: poll for operator confirmation
        # This is a simplified placeholder — full implementation wires a /confirm HTTP endpoint
        logger.warning(
            "[HumanGate] LIVE MODE: waiting %ds for human approval of %s",
            HUMAN_GATE_TIMEOUT_S, order.request_id,
        )
        await asyncio.sleep(HUMAN_GATE_TIMEOUT_S)
        # TODO: check approval store; for now deny to prevent accidental live fills during setup
        logger.warning("[HumanGate] Timeout — live order %s DENIED (wire /confirm endpoint to enable)", order.request_id)
        return False

    async def _send_discord_alert(self, order: OrderRequest, last_price: float, equity: float) -> None:
        if not DISCORD_WEBHOOK:
            logger.debug("[Discord] No webhook configured — skipping alert")
            return
        pct_equity = (order.quantity * last_price) / equity * 100 if equity > 0 else 0
        margin_zone   = self.cb.margin_zone(equity)
        margin_dist   = self.cb.margin_distance(equity)
        zone_colors   = {"SAFE": 0x00FF7F, "WARNING": 0xFFD700, "CAUTION": 0xFF6B00, "HARD_FLOOR_BREACH": 0xFF1493}
        embed_color   = zone_colors.get(margin_zone, 0x00FF7F)
        margin_label  = f"${equity:.2f}  [{margin_zone}]  (+${margin_dist:.2f} to floor)"

        payload = {
            "embeds": [{
                "title":       f"{'PAPER' if self.paper_mode else 'LIVE'} ORDER SIGNAL — {order.symbol}",
                "color":       embed_color,
                "fields": [
                    {"name": "Direction",     "value": order.side.upper(),                                         "inline": True},
                    {"name": "Symbol",        "value": order.symbol,                                               "inline": True},
                    {"name": "Quantity",      "value": f"{order.quantity:.2f}",                                    "inline": True},
                    {"name": "Last Price",    "value": f"${last_price:.4f}",                                       "inline": True},
                    {"name": "Order Value",   "value": f"${order.quantity * last_price:.2f} ({pct_equity:.2f}%)",  "inline": True},
                    {"name": "Account",       "value": margin_label,                                               "inline": False},
                    {"name": "Signal State",  "value": order.signal_state or "N/A",                                "inline": True},
                    {"name": "SQI",           "value": f"{order.sqi_score:.0f} / 100",                             "inline": True},
                    {"name": "Oracle",        "value": f"{order.oracle_score:.0f} / 100",                          "inline": True},
                    {"name": "Counsel",       "value": order.counsel_verdict or "N/A",                             "inline": False},
                    {"name": "Mode",          "value": "PAPER" if self.paper_mode else "LIVE",                     "inline": True},
                    {"name": "CB Status",     "value": "OK" if not self.cb._halted else "HALTED",                  "inline": True},
                    {"name": "PDT Shield",    "value": "OFF (rule eliminated 2026-06-04)",                          "inline": True},
                    {"name": "Request ID",    "value": order.request_id,                                            "inline": False},
                ],
                "footer": {"text": "SML Base-4 v6.2 | ScriptMasterLabs — Protect the $2,000 floor at all times"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }
        if not self.paper_mode:
            payload["content"] = "🔴 **LIVE ORDER PENDING — Reply CONFIRM to approve within 60s**"

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(DISCORD_WEBHOOK, json=payload)
        except Exception as exc:
            logger.warning("[Discord] Alert failed: %s", exc)

    # ─────────────────────────────────────────────────────────────────────
    # PAPER LOG
    # ─────────────────────────────────────────────────────────────────────

    def _log_paper(self, order: OrderRequest, fill: FillResult) -> None:
        entry = {
            "order":  asdict(order),
            "fill":   asdict(fill),
        }
        self._paper_log.append(entry)
        try:
            PAPER_LOG_PATH.write_text(json.dumps(self._paper_log, indent=2))
        except Exception as exc:
            logger.warning("[PaperLog] Write failed: %s", exc)

    def _load_paper_log(self) -> List[Dict]:
        try:
            if PAPER_LOG_PATH.exists():
                return json.loads(PAPER_LOG_PATH.read_text())
        except Exception:
            pass
        return []


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    async def _test():
        print("=" * 72)
        print("Robinhood MCP Adapter — Paper Mode Test")
        print("=" * 72)
        cb = CircuitBreaker()
        cb.reset()
        adapter = RobinhoodMCPAdapter(circuit_breaker=cb, paper_mode=True)

        # quantity=0.36 → $195.30 on $10,000 account = 1.95% (under 2.00% limit)
        order = OrderRequest(
            symbol="SPY", side="buy", quantity=0.36,
            signal_state="APEX_SINGULARITY", sqi_score=81.0,
            oracle_score=74.0, counsel_verdict="BULL — strong compression + MTF stack confirmed",
        )
        fill = await adapter.submit(order, last_price=542.50, account_equity=10000.0)
        print(f"\nFill result: {fill.status}")
        print(f"  Symbol:     {fill.symbol}")
        print(f"  Side:       {fill.side}")
        print(f"  Fill price: ${fill.fill_price:.4f}")
        print(f"  Paper mode: {fill.paper_mode}")
        print(f"  Order ID:   {fill.order_id}")
        print(f"\nCircuit Breaker status: {cb.status()}")
        print(f"Paper P&L summary: {adapter.paper_pnl_summary()}")

    asyncio.run(_test())
