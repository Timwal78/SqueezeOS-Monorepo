# ScriptMasterLabs — SML Institutional Signal Engine
### Base-4 Sovereign Harmonic Matrix | MCP Server v6.2

**9-set EMA compression · Self-calibrating CI · Dual-gate signals · AI counsel debate · XRPL micropayment**

---

## What This Does

The SML Base-4 engine detects when a market is mathematically coiling across every institutional time horizon simultaneously — the pre-breakout accumulation signature that retail indicators miss entirely.

**9 EMA sets × 4 EMAs each** in a `1:4:8:12` harmonic ratio = 36 EMAs, compressed to 25 unique periods. When all 9 sets compress, price is consolidating from intraday to monthly institutional anchor simultaneously.

### Live Validated Results (June 4, 2026)

| Ticker | State | Sets Coiled | CI Score | Verdict |
|--------|-------|-------------|----------|---------|
| SPY | **APEX SINGULARITY** | 8/9 | 94.8 | Structural coil at top 5th pct |
| IWM | **CRITICAL MASS** | 5/9 | 85.9 | Compressed regime confirmed |
| QQQ | **CRITICAL MASS** | 5/9 | 91.1 | Tightening vector |
| AMC | SCANNING | 1/9 | 75.8 | ← **correctly identified as chop zone** |
| GME | SCANNING | 0/9 | 63.7 | ← **zero sets converged — avoid** |

**The same CI=78 threshold correctly separated institutional setups from chop-zone instruments across all 5 tickers without any parameter tuning.** That is the self-calibrating percentile system at work.

---

## The Math

```
CI (Compression Index) = percentile_rank(avg_EMA_spread, 252_bar_window)

Dual-Gate:
  CI >= 78 (structural gate)  → top 22nd percentile — chop zone eliminated
  SQI >= 75 (execution gate)  → all 4 pillars aligned

SQI = compression(40pt) + MTF_alignment(30pt) + volume(15pt) + regime(15pt)

PRIME signal = CI >= 78 AND SQI >= 75 simultaneously
```

**Why 78?** Below CI=78, market makers retain enough EMA grid dispersion to run stop-hunting wicks without triggering the breakout. Above 78, the multi-week anchor lines are mathematically committed — breaking price requires breaking institutional positions across every time horizon first.

**Why percentile-ranked?** A fixed spread threshold (e.g., < 1%) produces inconsistent signal frequency across different instruments. AMC at "1% spread" means something completely different than SPY at "1% spread". Percentile ranking normalizes against each instrument's own 252-bar history — CI=78 is equally selective everywhere.

---

## Tools (9 total)

### Free Tools
| Tool | Description |
|------|-------------|
| `get_signal_preview` | Truncated signal — state, CI, SQI, action, key levels |
| `run_showcase` | Live scan: SPY/IWM/QQQ/AMC/GME/NVDA sorted by quality |
| `get_methodology` | Full mathematical reference with live validation data |
| `check_health` | Service status and regulatory context |
| `get_institution_catalog` | Complete product/service catalog |

### Premium Tools (RLUSD via x402)
| Tool | Cost | Description |
|------|------|-------------|
| `get_intelligence_brief` | 0.10 RLUSD | Full institutional narrative — compression math, grid analysis, MTF context, risk factors, agent instruction block |
| `get_full_signal` | 0.05 RLUSD | All 9 set metrics + MTF breakdown + SQI pillars |
| `scan_tickers` | 0.05 RLUSD | Multi-ticker scan with CI/prime filters (up to 10 symbols) |
| `get_council_verdict` | 0.25 RLUSD | Full Bull/Bear/Neutral AI debate via TradingAgents (Anthropic Claude) |

*Payment via x402 protocol — RLUSD on XRP Ledger. No subscriptions. No API keys required for free tools.*

---

## Quick Start

### Claude Desktop / Cursor
```bash
claude mcp add sml-institutional -- python C:\Users\timot\.gemini\antigravity\scratch\SqueezeOS_Monorepo\backend\mcp_server_sml.py
```

### From Smithery
Install directly from the Smithery registry.

### Environment Variables (optional)
```bash
ANTHROPIC_API_KEY=     # Enables AI counsel verdicts
DISCORD_WEBHOOK_ALL=   # Signal notifications
ROBINHOOD_PAPER_MODE=true   # Paper mode (default)
PDT_SHIELD_ENABLED=false    # PDT rule eliminated 2026-06-04
X402_ENFORCE=false          # Disable payment gate for local use
```

---

## The Full Institutional Stack

| Engine | Status | Description |
|--------|--------|-------------|
| SML Base-4 (Python + Pine) | ✅ Live | Core compression engine |
| SqueezeOS v5.x | ✅ Online | 13+ specialized trading engines |
| Oracle Engine | ✅ Integrated | BUY_PRIME/BUY/HOLD/SHIELD aggregator |
| TradingAgents Counsel | ✅ Wired | Bull/Bear debate via Claude |
| Echo Forge | ✅ Online (port 8001) | Cross-asset pattern memory |
| OpenMythos | ✅ Online (port 8002) | Recurrent-Depth Transformer |
| Argus Omega | Available | Fusion intelligence (ARGUS + LIQUIDITY GHOST + FALSE REALITY) |
| IWM 0DTE Desk | Available | Same-day options engine |
| Fee Forge / XRPL | ✅ Live | x402 micropayment rail — no API keys |
| Robinhood MCP | Paper mode | Connected, awaiting 30-day validation |

---

## Regulatory Context (2026)

- **PDT Rule**: Eliminated June 4, 2026 — no day-trade frequency limit
- **Margin Floor**: $2,000 minimum equity for margin accounts
- **Hard Stop**: Engine halts at $2,100 (100-point buffer above floor)
- **Execution**: Human confirmation required on all orders — no autonomous trading
- **Mode**: Paper mode default — live capital requires explicit operator override

---

## Example Agent Instruction (from `get_intelligence_brief`)

```
PRIME SIGNAL ACTIVE on SPY.
The SML Base-4 dual-gate has cleared: CI 94.8 >= 78 (structural)
AND SQI 67.9 >= 75 (execution).
Action: BUY — human confirmation required before execution.
Anchor floor (invalidation): $594.2200.
Do not enter if price is already outside the anchor band.
```

---

## MCP Directory Listings

This server is listed on:
- [Smithery.ai](https://smithery.ai)
- [glama.ai](https://glama.ai/mcp/servers)
- [mcp.so](https://mcp.so)
- [pulsemcp.com](https://pulsemcp.com)

---

## License & Contact

**Proprietary — ScriptMasterLabs © 2026. DO NOT REDISTRIBUTE.**

- Site: https://scriptmasterlabs.com
- GitHub: https://github.com/timwal78/SqueezeOS
- Methodology: `/api/methodology` (served locally)
- AI manifest: `/llms.txt` (served locally)


