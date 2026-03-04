# Interchange Squeeze — EU Debit Pricing Strategy Tool

Interactive Python CLI + Rich TUI for modeling Yuno's European debit pricing strategy scenarios.

## Overview

European debit interchange is being squeezed. This tool models four pricing strategies across merchant segments, quantifying the trade-off between volume retention and margin preservation.

**Key scenarios modeled:**
- **S1 Hold 18bp** — Defend current rates, risk GMV loss
- **S2 Flat 10bp** — Match market floor, maximize retention
- **S3 Tiered 12-18bp** — Segment by merchant size ★ Recommended
- **S4 Tiered + Growth** — Tiered pricing with 8% GMV growth ⚠ Growth is a commercial execution target, not a pricing input

## Quick Start

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run the TUI dashboard
uv run interchange-squeeze

# Or with custom inputs
uv run interchange-squeeze --merchant-gmv 480 --yuno-rate 92.3 --competitor-rate 88.6
```

## Usage

```
Usage: interchange-squeeze [OPTIONS]

  Launch the Interchange Squeeze TUI dashboard.

Options:
  --merchant-gmv FLOAT     Monthly GMV in millions EUR (default: 40)
  --yuno-rate FLOAT        Yuno approval rate % (default: 92.3)
  --competitor-rate FLOAT  Competitor approval rate % (default: 88.6)
  --yuno-bp FLOAT          Yuno take rate in basis points (default: 18)
  --competitor-bp FLOAT    Competitor take rate in basis points (default: 10)
  --non-interactive / -n   Print tables once and exit (no prompts)
  --help                   Show this message and exit.
```

### Non-interactive (scripting / CI)

```bash
uv run interchange-squeeze --non-interactive
uv run python -m interchange_squeeze --non-interactive
```

### Interactive Controls

Once the dashboard is running:
- Type new values at the prompts to update GMV, rates, approval deltas, merchant margin, chargeback rate, or failed payment rate
- Press `Ctrl+C` or type `q` to quit

## Dashboard Panels

1. **Merchant Value Analysis** — Approval rate delta → incremental GP and ROI multiple (GP-basis: ~16x GP per €1 premium)
2. **Scenario Comparison** — S1–S4 revenue, gross profit, margin side by side; S3 marked ★ recommended, S4 marked ⚠ growth assumption
3. **Sensitivity Analysis** — GMV growth required at each rate to match S3 baseline revenue
4. **Break-Even Analysis** — Max Enterprise churn S3 can absorb before GP falls below S2 (~75%)
5. **Chargeback Reduction** — Fee + dispute cost savings from smart routing
6. **Failed Payment Recovery** — Revenue recovered via retry logic
7. **12-Month P&L** — Recommended scenario with EU debit seasonality (Q1 light, Q4 heavy)
8. **Strategic Recommendation** — S3 → S4 path; explicit optimization target (market share over short-term margin); why enterprise churns at 18bp (€384K/year premium cost at €480M GMV); S4 growth derived from approval rate model (~3.7% organic + 4% new wins = ~7.7% ≈ 8%)
9. **Churn Sensitivity** — S1 Hold revenue at varying enterprise retention levels vs S3
10. **Segment Value Analysis** — Approval rate ROI by merchant tier
11. **Competitive Dynamics** — Why S2 flat 10bp is a margin trap; structural cost argument for why regional specialists (Mollie, Stripe EU, Adyen, local acquirers) can price at 10bp; EU market structure (SEPA, iDEAL, Bancontact); Yuno's defensible premium
12. **Implementation Roadmap** — S3 → S4 migration phases with merchant communication strategy, sales objection handling ('competitor offers 8bp'), and contingency trigger (if churn >30%)

## Run Tests

```bash
uv run pytest          # 127 tests
```

## Project Structure

```
src/interchange_squeeze/
├── models.py      # Core financial dataclasses + calc functions
├── value.py       # Approval rate → merchant revenue converter
│                  #   ApprovalRateAnalysis, ChargebackAnalysis, FailedPaymentRecovery
├── scenarios.py   # 4 scenario definitions + comparison engine
│                  #   calc_breakeven_attrition(), calc_monthly_pl(), MONTHLY_SEASONALITY
│                  #   calc_approval_rate_implied_gmv_growth() — derives S4 8% growth from first principles
├── tui.py         # Rich TUI layout and tables (12 panel builders)
└── cli.py         # Typer CLI entry point
```
