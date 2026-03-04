"""CLI entry point for the Interchange Squeeze tool."""

import typer
from rich.console import Console

from interchange_squeeze.tui import run_interactive

app = typer.Typer(
    name="interchange-squeeze",
    help="EU Debit Pricing Strategy Dashboard — model Yuno's interchange scenarios.",
    add_completion=False,
)


@app.command()
def run(
    merchant_gmv: float = typer.Option(
        40.0,
        "--merchant-gmv",
        help="Monthly merchant GMV in millions EUR (used for value analysis).",
        show_default=True,
    ),
    yuno_rate: float = typer.Option(
        92.3,
        "--yuno-rate",
        help="Yuno payment approval rate %%.",
        show_default=True,
    ),
    competitor_rate: float = typer.Option(
        88.6,
        "--competitor-rate",
        help="Competitor payment approval rate %%.",
        show_default=True,
    ),
    yuno_bp: float = typer.Option(
        18.0,
        "--yuno-bp",
        help="Yuno take rate in basis points.",
        show_default=True,
    ),
    competitor_bp: float = typer.Option(
        10.0,
        "--competitor-bp",
        help="Competitor take rate in basis points.",
        show_default=True,
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        "-n",
        help="Print tables once and exit (no interactive prompts).",
        show_default=True,
    ),
) -> None:
    """Launch the Interchange Squeeze TUI dashboard.

    Displays three panels:
    - Merchant Value Analysis (approval rate ROI)
    - Scenario Comparison (S1–S4 pricing strategies)
    - Sensitivity Analysis (GMV growth needed at each rate)

    In interactive mode (default), you can update inputs to refresh the tables.
    """
    console = Console()
    monthly_gmv = merchant_gmv * 1_000_000

    if non_interactive:
        from rich.columns import Columns
        from interchange_squeeze.tui import (
            build_value_table,
            build_scenario_table,
            build_sensitivity_table,
            build_breakeven_table,
            build_chargeback_table,
            build_recovery_table,
            build_monthly_pl_table,
            build_recommendation_panel,
            build_churn_sensitivity_table,
            build_segment_value_table,
            build_competitive_dynamics_panel,
            build_implementation_table,
        )
        from interchange_squeeze.scenarios import RECOMMENDED_SCENARIO
        console.print(build_value_table(monthly_gmv, yuno_rate, competitor_rate, yuno_bp, competitor_bp))
        console.print()
        console.print(build_scenario_table())
        console.print()
        console.print(build_sensitivity_table())
        console.print()
        console.print(build_breakeven_table())
        console.print()
        console.print(Columns([
            build_chargeback_table(monthly_gmv),
            build_recovery_table(monthly_gmv),
        ]))
        console.print()
        console.print(build_monthly_pl_table(RECOMMENDED_SCENARIO))
        console.print()
        console.print(build_recommendation_panel())
        console.print()
        console.print(build_churn_sensitivity_table())
        console.print()
        console.print(build_segment_value_table())
        console.print()
        console.print(build_competitive_dynamics_panel())
        console.print()
        console.print(build_implementation_table())
    else:
        run_interactive(console, monthly_gmv, yuno_rate, competitor_rate, yuno_bp, competitor_bp)
