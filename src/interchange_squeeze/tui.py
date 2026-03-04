"""Rich TUI dashboard for the Interchange Squeeze tool.

Provides three panels:
1. Merchant Value Analysis — approval rate delta → incremental revenue + ROI
2. Scenario Comparison — S1–S4 side-by-side P&L
3. Sensitivity Analysis — GMV growth needed at each rate to match baseline revenue
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich.prompt import Prompt
from rich import box

from interchange_squeeze.value import ApprovalRateAnalysis
from interchange_squeeze.scenarios import (
    DEFAULT_SCENARIOS,
    run_scenario,
    compare_scenarios,
    ScenarioResult,
    Scenario,
    PORTFOLIO_ENTERPRISE_GMV,
    PORTFOLIO_MID_GMV,
    PORTFOLIO_SMB_GMV,
)
from interchange_squeeze.scenarios import DEFAULT_COST_BP as _DEFAULT_COST_BP


def fmt_eur(amount: float, unit: str = "M") -> str:
    """Format EUR amount with unit (K or M)."""
    if unit == "M":
        return f"€{amount / 1_000_000:.3f}M"
    elif unit == "K":
        return f"€{amount / 1_000:.1f}K"
    return f"€{amount:,.0f}"


def fmt_bp(bp: float) -> str:
    return f"{bp:.1f}bp"


def fmt_pct(fraction: float) -> str:
    return f"{fraction * 100:.1f}%"


def fmt_rate(rate: float) -> str:
    return f"{rate:.1f}%"


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

def build_value_table(
    monthly_gmv: float = 40_000_000,
    yuno_rate: float = 92.3,
    competitor_rate: float = 88.6,
    yuno_bp: float = 18.0,
    competitor_bp: float = 10.0,
) -> Table:
    """Build the Merchant Value Analysis table.

    Shows how Yuno's approval rate advantage translates to merchant revenue
    and a compelling ROI vs the pricing premium.
    """
    analysis = ApprovalRateAnalysis(
        monthly_gmv=monthly_gmv,
        yuno_approval_rate=yuno_rate,
        competitor_approval_rate=competitor_rate,
        yuno_bp=yuno_bp,
        competitor_bp=competitor_bp,
    )

    table = Table(
        title="[bold cyan]Merchant Value Analysis[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=62,
    )
    table.add_column("Metric", style="dim white", min_width=30)
    table.add_column("Value", justify="right", style="bold green", min_width=18)
    table.add_column("Notes", style="dim", min_width=14)

    delta = analysis.approval_rate_delta
    transactions = analysis.calc_monthly_transactions()
    inc_approvals = analysis.calc_incremental_approvals()
    inc_revenue = analysis.calc_incremental_merchant_revenue()
    premium = analysis.calc_pricing_premium_cost()
    inc_gp = analysis.calc_incremental_gross_profit()
    net = analysis.calc_net_value()
    roi = analysis.calc_roi_multiple()

    table.add_row("Monthly GMV", fmt_eur(monthly_gmv), "Input")
    table.add_row("Yuno Approval Rate", fmt_rate(yuno_rate), "")
    table.add_row("Competitor Approval Rate", fmt_rate(competitor_rate), "")
    table.add_row("Approval Rate Delta", f"[bold yellow]+{delta:.1f}pp[/bold yellow]", "Yuno advantage")
    table.add_section()
    table.add_row("Monthly Transactions", f"{transactions:,.0f}", f"AOV €{analysis.avg_order_value:.0f}")
    table.add_row("Incremental Approvals/mo", f"[green]+{inc_approvals:,.0f}[/green]", "Extra approved txns")
    table.add_row("Incremental Merchant Revenue", f"[bold green]+{fmt_eur(inc_revenue, 'M')}/mo[/bold green]", "")
    table.add_section()
    table.add_row("Yuno Rate", fmt_bp(yuno_bp), "")
    table.add_row("Competitor Rate", fmt_bp(competitor_bp), "")
    table.add_row(
        "Pricing Premium Cost",
        f"[yellow]+{fmt_eur(premium, 'K')}/mo[/yellow]",
        "Extra cost vs competitor",
    )
    table.add_row("Incremental Gross Profit", f"[green]+{fmt_eur(inc_gp, 'K')}/mo[/green]", f"@ {fmt_pct(analysis.merchant_gross_margin)} GM")
    table.add_section()
    net_color = "green" if net > 0 else "red"
    table.add_row(
        "Net Monthly Value",
        f"[bold {net_color}]{fmt_eur(net, 'K')}/mo[/bold {net_color}]",
        "GP - premium cost",
    )
    roi_color = "green" if roi > 5 else "yellow"
    table.add_row(
        "ROI Multiple",
        f"[bold {roi_color}]{roi:.1f}x[/bold {roi_color}]",
        "Rev per €1 premium",
    )

    return table


def build_scenario_table(
    scenarios: list[Scenario] | None = None,
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
) -> Table:
    """Build the Scenario Comparison table with S1–S4 side by side."""
    if scenarios is None:
        scenarios = DEFAULT_SCENARIOS

    results = compare_scenarios(scenarios, enterprise_gmv, mid_gmv, smb_gmv)

    table = Table(
        title="[bold cyan]Scenario Comparison — EU Debit Pricing[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=90,
    )
    table.add_column("Metric", style="dim white", min_width=24)

    for result in results:
        # Highlight the best scenario (highest revenue)
        if result == results[0]:
            table.add_column(f"[bold green]{result.scenario_name}[/bold green]", justify="right", min_width=18)
        else:
            table.add_column(result.scenario_name, justify="right", min_width=18)

    def row(label: str, values: list[str]) -> None:
        table.add_row(label, *values)

    row("Total GMV Retained", [fmt_eur(r.total_gmv, "M") for r in results])
    row("Enterprise GMV", [fmt_eur(r.enterprise_gmv, "M") for r in results])
    table.add_section()

    # Revenue rows — highlight the max
    rev_vals = [r.total_revenue for r in results]
    max_rev = max(rev_vals)
    rev_strs = []
    for r in results:
        color = "bold green" if r.total_revenue == max_rev else "white"
        rev_strs.append(f"[{color}]{fmt_eur(r.total_revenue, 'M')}[/{color}]")
    row("Total Revenue", rev_strs)
    row("  Enterprise Rev", [fmt_eur(r.enterprise_revenue, "M") for r in results])
    row("  Mid-Market Rev", [fmt_eur(r.mid_revenue, "M") for r in results])
    row("  SMB Rev", [fmt_eur(r.smb_revenue, "M") for r in results])
    table.add_section()

    gp_vals = [r.total_gross_profit for r in results]
    max_gp = max(gp_vals)
    gp_strs = []
    for r in results:
        color = "bold green" if r.total_gross_profit == max_gp else "white"
        gp_strs.append(f"[{color}]{fmt_eur(r.total_gross_profit, 'M')}[/{color}]")
    row("Gross Profit", gp_strs)
    row("Blended Margin", [fmt_pct(r.blended_gross_margin) for r in results])
    row("Blended Take Rate", [fmt_bp(r.blended_take_rate_bp) for r in results])

    return table


def build_sensitivity_table(
    base_rate_bp: float = 12.0,
    base_revenue: float | None = None,
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
) -> Table:
    """Build the Sensitivity Analysis table.

    Shows how much GMV growth is needed at various rates to match the
    baseline revenue (S3 Tiered at default GMV).
    """
    from interchange_squeeze.scenarios import S3_TIERED, run_scenario, Scenario

    if base_revenue is None:
        base_result = run_scenario(S3_TIERED, enterprise_gmv, mid_gmv, smb_gmv)
        base_revenue = base_result.total_revenue

    table = Table(
        title=f"[bold cyan]Sensitivity — GMV Growth to Match Baseline Rev ({fmt_eur(base_revenue, 'M')})[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=70,
    )
    table.add_column("Blended Rate Scenario", style="dim white", min_width=28)
    table.add_column("Current Revenue", justify="right", min_width=16)
    table.add_column("GMV Growth Needed", justify="right", min_width=18)
    table.add_column("Feasible?", justify="center", min_width=10)

    test_scenarios = [
        ("Flat 8bp (floor)", 8.0),
        ("Flat 10bp", 10.0),
        ("Flat 12bp", 12.0),
        ("Flat 15bp", 15.0),
        ("S3 Tiered (baseline)", None),  # None = use actual S3
        ("Flat 18bp", 18.0),
    ]

    total_gmv = enterprise_gmv + mid_gmv + smb_gmv

    for label, flat_rate in test_scenarios:
        if flat_rate is None:
            current_rev = base_revenue
            growth_pct = 0.0
        else:
            current_rev = total_gmv * flat_rate / 10_000
            if current_rev > 0:
                required_gmv = base_revenue / (flat_rate / 10_000)
                growth_pct = (required_gmv - total_gmv) / total_gmv * 100
            else:
                growth_pct = float("inf")

        feasible = growth_pct <= 15.0
        feasible_str = "[green]Yes[/green]" if feasible else "[red]No[/red]"
        if flat_rate is None:
            feasible_str = "[bold green]Baseline[/bold green]"

        growth_str = f"+{growth_pct:.1f}%" if flat_rate is not None else "—"
        rev_str = fmt_eur(current_rev, "M")

        table.add_row(label, rev_str, growth_str, feasible_str)

    return table


# ---------------------------------------------------------------------------
# Dashboard layout
# ---------------------------------------------------------------------------

HEADER_TEXT = """[bold white]Interchange Squeeze[/bold white] [dim]|[/dim] [cyan]EU Debit Pricing Strategy Dashboard[/cyan]
[dim]Model Yuno's European debit pricing scenarios. Update inputs to refresh.[/dim]"""


def build_dashboard(
    monthly_gmv: float = 40_000_000,
    yuno_rate: float = 92.3,
    competitor_rate: float = 88.6,
    yuno_bp: float = 18.0,
    competitor_bp: float = 10.0,
) -> Layout:
    """Assemble the full Rich Layout for the dashboard."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body"),
    )
    layout["body"].split_column(
        Layout(name="top", ratio=2),
        Layout(name="bottom", ratio=1),
    )
    layout["top"].split_row(
        Layout(name="value", ratio=1),
        Layout(name="scenarios", ratio=2),
    )

    layout["header"].update(
        Panel(Text.from_markup(HEADER_TEXT), border_style="bold blue")
    )
    layout["value"].update(
        build_value_table(monthly_gmv, yuno_rate, competitor_rate, yuno_bp, competitor_bp)
    )
    layout["scenarios"].update(build_scenario_table())
    layout["bottom"].update(build_sensitivity_table())

    return layout


# ---------------------------------------------------------------------------
# Interactive loop
# ---------------------------------------------------------------------------

def run_interactive(
    console: Console,
    monthly_gmv: float = 40_000_000,
    yuno_rate: float = 92.3,
    competitor_rate: float = 88.6,
    yuno_bp: float = 18.0,
    competitor_bp: float = 10.0,
) -> None:
    """Run the interactive TUI loop.

    Renders the dashboard, then prompts the user to update inputs.
    Loops until the user types 'q' or presses Ctrl+C.
    """
    while True:
        console.clear()
        console.print(build_value_table(monthly_gmv, yuno_rate, competitor_rate, yuno_bp, competitor_bp))
        console.print()
        console.print(build_scenario_table())
        console.print()
        console.print(build_sensitivity_table())
        console.print()
        console.print(
            f"[dim]Current inputs:[/dim] GMV=[cyan]€{monthly_gmv/1_000_000:.0f}M/mo[/cyan]  "
            f"Yuno=[cyan]{yuno_rate}%[/cyan]  Competitor=[cyan]{competitor_rate}%[/cyan]  "
            f"Yuno rate=[cyan]{yuno_bp}bp[/cyan]  Competitor rate=[cyan]{competitor_bp}bp[/cyan]"
        )
        console.print()
        console.print("[bold]Update inputs[/bold] (press Enter to keep current value, type [bold red]q[/bold red] to quit):")

        try:
            gmv_input = Prompt.ask(
                f"  Monthly GMV in €M (currently {monthly_gmv/1_000_000:.0f})",
                default="",
                console=console,
            )
            if gmv_input.strip().lower() == "q":
                break
            if gmv_input.strip():
                monthly_gmv = float(gmv_input.strip()) * 1_000_000

            yuno_input = Prompt.ask(
                f"  Yuno approval rate % (currently {yuno_rate})",
                default="",
                console=console,
            )
            if yuno_input.strip().lower() == "q":
                break
            if yuno_input.strip():
                yuno_rate = float(yuno_input.strip())

            comp_input = Prompt.ask(
                f"  Competitor approval rate % (currently {competitor_rate})",
                default="",
                console=console,
            )
            if comp_input.strip().lower() == "q":
                break
            if comp_input.strip():
                competitor_rate = float(comp_input.strip())

            yuno_bp_input = Prompt.ask(
                f"  Yuno take rate bp (currently {yuno_bp})",
                default="",
                console=console,
            )
            if yuno_bp_input.strip().lower() == "q":
                break
            if yuno_bp_input.strip():
                yuno_bp = float(yuno_bp_input.strip())

            comp_bp_input = Prompt.ask(
                f"  Competitor take rate bp (currently {competitor_bp})",
                default="",
                console=console,
            )
            if comp_bp_input.strip().lower() == "q":
                break
            if comp_bp_input.strip():
                competitor_bp = float(comp_bp_input.strip())

        except (KeyboardInterrupt, EOFError):
            break
        except ValueError as e:
            console.print(f"[red]Invalid input: {e}. Keeping current values.[/red]")
            continue

    console.print("\n[dim]Goodbye.[/dim]")
