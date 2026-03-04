# Interchange Squeeze — EU Debit Pricing Strategy Tool

Interactive Python CLI + Rich TUI for modeling Yuno's European debit pricing strategy scenarios.

## Overview

European debit interchange is being squeezed. This tool models four pricing strategies across merchant segments, quantifying the trade-off between volume retention and margin preservation.

**Key scenarios modeled:**
- **S1 Hold 18bp** — Defend current rates, risk GMV loss
- **S2 Flat 10bp** — Match market floor, maximize retention
- **S3 Tiered 12-18bp** — Segment by merchant size
- **S4 Tiered + Growth** — Tiered pricing with volume incentives

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
  --help                   Show this message and exit.
```

### Interactive Controls

Once the dashboard is running:
- Type new values at the prompts to update GMV, rates, or approval deltas
- Press `Ctrl+C` or type `q` to quit

## Dashboard Panels

1. **Merchant Value Analysis** — Approval rate delta → incremental revenue, ROI multiple
2. **Scenario Comparison** — S1–S4 revenue, gross profit, margin side by side
3. **Sensitivity Analysis** — GMV growth required at each rate to match baseline

## Run Tests

```bash
uv run pytest
```

## Project Structure

```
src/interchange_squeeze/
├── models.py      # Core financial dataclasses + calc functions
├── value.py       # Approval rate → merchant revenue converter
├── scenarios.py   # 4 scenario definitions + comparison engine
├── tui.py         # Rich TUI layout and tables
└── cli.py         # Typer CLI entry point
```
