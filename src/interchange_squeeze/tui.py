"""Rich TUI dashboard for the Interchange Squeeze tool.

Provides panels:
1. Merchant Value Analysis — approval rate delta → incremental revenue + ROI
2. Scenario Comparison — S1–S4 side-by-side P&L
3. Sensitivity Analysis — GMV growth needed at each rate to match baseline revenue
4. Break-Even Analysis — max Enterprise churn before S3 loses to S2
5. Chargeback & Failed Payment Recovery — additional value levers
6. Monthly P&L — 12-month seasonality breakdown for recommended scenario
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

from interchange_squeeze.value import ApprovalRateAnalysis, ChargebackAnalysis, FailedPaymentRecovery
from dataclasses import replace as _replace
from interchange_squeeze.models import DEFAULT_SEGMENTS
from interchange_squeeze.scenarios import (
    DEFAULT_SCENARIOS,
    run_scenario,
    compare_scenarios,
    calc_breakeven_attrition,
    calc_monthly_pl,
    calc_approval_rate_implied_gmv_growth,
    ScenarioResult,
    Scenario,
    PORTFOLIO_ENTERPRISE_GMV,
    PORTFOLIO_MID_GMV,
    PORTFOLIO_SMB_GMV,
    S1_HOLD,
    S2_FLAT_10BP,
    S3_TIERED,
    S4_TIERED_GROWTH,
    RECOMMENDED_SCENARIO,
)
from interchange_squeeze.scenarios import DEFAULT_COST_BP as _DEFAULT_COST_BP

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


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
    merchant_margin: float = 0.35,
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
        merchant_gross_margin=merchant_margin,
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
    table.add_row("Incremental Gross Profit", f"[green]+{fmt_eur(inc_gp, 'K')}/mo[/green]", f"@ {fmt_pct(merchant_margin)} GM")
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
        "GP per €1 premium",
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

    scenario_by_name = {s.name: s for s in scenarios}
    results = compare_scenarios(scenarios, enterprise_gmv, mid_gmv, smb_gmv)

    table = Table(
        title="[bold cyan]Scenario Comparison — EU Debit Pricing[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=90,
        caption="[dim]★ = Recommended scenario  |  S4 growth assumption is a commercial execution target, not a pricing input[/dim]",
    )
    table.add_column("Metric", style="dim white", min_width=24)

    for result in results:
        scenario = scenario_by_name.get(result.scenario_name)
        is_recommended = scenario is not None and scenario.recommended
        is_growth = scenario is not None and scenario.includes_growth_assumption

        if is_recommended:
            col_label = f"[bold green]{result.scenario_name} ★[/bold green]"
        elif is_growth:
            col_label = f"[yellow]{result.scenario_name} ⚠[/yellow]"
        elif result == results[0]:
            col_label = f"[bold green]{result.scenario_name}[/bold green]"
        else:
            col_label = result.scenario_name

        table.add_column(col_label, justify="right", min_width=18)

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


def build_breakeven_table(
    test_scenario: Scenario = S3_TIERED,
    vs_scenario: Scenario = S2_FLAT_10BP,
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
) -> Table:
    """Break-Even Analysis: how much Enterprise churn before test_scenario GP falls below vs_scenario GP.

    Columns: Comparison | GP Cushion | Max Churn % | GMV at Risk | Merchants Lost | Decision
    """
    result = calc_breakeven_attrition(
        test_scenario=test_scenario,
        vs_scenario=vs_scenario,
        enterprise_gmv=enterprise_gmv,
        mid_gmv=mid_gmv,
        smb_gmv=smb_gmv,
    )

    table = Table(
        title="[bold cyan]Break-Even Analysis — Enterprise Attrition Tolerance[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=90,
    )
    table.add_column("Comparison", style="dim white", min_width=22)
    table.add_column("GP Cushion", justify="right", min_width=14)
    table.add_column("Max Churn %", justify="right", min_width=12)
    table.add_column("GMV at Risk", justify="right", min_width=14)
    table.add_column("Merchants Lost", justify="right", min_width=15)
    table.add_column("Decision", style="dim", min_width=22)

    churn_pct = result["breakeven_churn_pct"]
    churn_color = "green" if churn_pct >= 50 else "yellow" if churn_pct >= 25 else "red"

    table.add_row(
        f"{test_scenario.name} vs {vs_scenario.name}",
        fmt_eur(result["gp_cushion"], "M"),
        f"[bold {churn_color}]{churn_pct:.1f}%[/bold {churn_color}]",
        fmt_eur(result["breakeven_gmv_eur"], "M"),
        f"~{result['merchants_equiv']} merchants",
        f"{test_scenario.name} survives up to {churn_pct:.0f}% Enterprise churn",
    )
    table.add_section()
    table.add_row(
        "Test scenario GP",
        fmt_eur(result["test_gp"], "M"),
        "", "", "",
        f"vs. floor GP {fmt_eur(result['vs_gp'], 'M')}",
    )

    return table


def build_chargeback_table(
    monthly_gmv: float = 40_000_000,
    chargeback_rate: float = 0.5,
    expected_reduction: float = 0.1,
) -> Table:
    """Chargeback reduction value: fee savings + operational cost savings."""
    analysis = ChargebackAnalysis(
        monthly_gmv=monthly_gmv,
        chargeback_rate_pct=chargeback_rate,
        expected_reduction_pct=expected_reduction,
    )

    table = Table(
        title="[bold cyan]Chargeback Reduction Value[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=55,
    )
    table.add_column("Metric", style="dim white", min_width=28)
    table.add_column("Value", justify="right", style="bold green", min_width=14)

    table.add_row("Monthly Chargebacks", f"{analysis.calc_monthly_chargebacks():,.0f}")
    table.add_row("Chargebacks Avoided", f"[green]+{analysis.calc_chargebacks_avoided():,.0f}[/green]")
    table.add_section()
    table.add_row("Acquirer Fee Savings", fmt_eur(analysis.calc_fee_savings(), "K") + "/mo")
    table.add_row("Dispute Cost Savings", fmt_eur(analysis.calc_dispute_cost_savings(), "K") + "/mo")
    table.add_row(
        "[bold]Total Monthly Savings[/bold]",
        f"[bold green]{fmt_eur(analysis.calc_total_monthly_savings(), 'K')}/mo[/bold green]",
    )

    return table


def build_recovery_table(
    monthly_gmv: float = 40_000_000,
    failed_rate: float = 3.0,
    retry_recovery: float = 25.0,
) -> Table:
    """Failed payment recovery value: revenue recovered via retry logic."""
    analysis = FailedPaymentRecovery(
        monthly_gmv=monthly_gmv,
        failed_payment_rate_pct=failed_rate,
        retry_recovery_rate_pct=retry_recovery,
    )

    table = Table(
        title="[bold cyan]Failed Payment Recovery[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=55,
    )
    table.add_column("Metric", style="dim white", min_width=28)
    table.add_column("Value", justify="right", style="bold green", min_width=14)

    table.add_row("Failed Transactions/mo", f"{analysis.calc_failed_transactions():,.0f}")
    table.add_row("Recovered Transactions/mo", f"[green]+{analysis.calc_recovered_transactions():,.0f}[/green]")
    table.add_section()
    table.add_row(
        "[bold]Recovered Revenue/mo[/bold]",
        f"[bold green]{fmt_eur(analysis.calc_recovered_revenue(), 'K')}/mo[/bold green]",
    )

    return table


def build_monthly_pl_table(
    scenario: Scenario = S3_TIERED,
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
) -> Table:
    """12-month P&L for the given scenario with EU debit seasonality.

    Columns: Month | GMV | Revenue | Gross Profit | GM%
    """
    rows = calc_monthly_pl(scenario, enterprise_gmv, mid_gmv, smb_gmv)

    table = Table(
        title=f"[bold cyan]12-Month P&L — {scenario.name} (with EU Debit Seasonality)[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=72,
    )
    table.add_column("Month", style="dim white", min_width=6)
    table.add_column("GMV", justify="right", min_width=14)
    table.add_column("Revenue", justify="right", min_width=14)
    table.add_column("Gross Profit", justify="right", min_width=14)
    table.add_column("GM%", justify="right", min_width=8)

    for row in rows:
        month_name = MONTHS[row["month"] - 1]
        gm_pct = row["gross_margin_pct"] * 100
        gm_color = "green" if gm_pct >= 40 else "yellow" if gm_pct >= 30 else "white"
        table.add_row(
            month_name,
            fmt_eur(row["gmv"], "M"),
            fmt_eur(row["revenue"], "K"),
            fmt_eur(row["gross_profit"], "K"),
            f"[{gm_color}]{gm_pct:.1f}%[/{gm_color}]",
        )

    # Totals row
    total_gmv = sum(r["gmv"] for r in rows)
    total_rev = sum(r["revenue"] for r in rows)
    total_gp = sum(r["gross_profit"] for r in rows)
    total_gm = total_gp / total_rev if total_rev > 0 else 0.0
    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{fmt_eur(total_gmv, 'M')}[/bold]",
        f"[bold]{fmt_eur(total_rev, 'M')}[/bold]",
        f"[bold green]{fmt_eur(total_gp, 'M')}[/bold green]",
        f"[bold]{total_gm * 100:.1f}%[/bold]",
    )

    return table


def build_recommendation_panel() -> Panel:
    """Strategic recommendation: why S3 → S4 path beats S1 and S2."""
    breakeven = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
    breakeven_churn_pct = breakeven["breakeven_churn_pct"]
    merchants_equiv = breakeven["merchants_equiv"]

    # Derive S4 growth from approval rate advantage (first principles)
    implied_growth = calc_approval_rate_implied_gmv_growth()  # ~7.7%
    implied_growth_pct = implied_growth * 100

    # Cost of staying at 18bp for a representative enterprise merchant
    representative_enterprise_gmv = 480_000_000  # €480M annual
    premium_bp = 8.0  # S1 18bp vs competitor 10bp
    enterprise_annual_premium_eur = representative_enterprise_gmv * premium_bp / 10_000  # €384K

    # Revenue per basis point surrendered at portfolio scale
    total_portfolio_gmv = PORTFOLIO_ENTERPRISE_GMV + PORTFOLIO_MID_GMV + PORTFOLIO_SMB_GMV
    rev_per_bp = total_portfolio_gmv / 10_000  # EUR per bp

    content = (
        f"[bold]Recommended:[/bold] {RECOMMENDED_SCENARIO.name} (S3 Tiered) → S4 path\n\n"
        f"[bold]Strategic objective:[/bold] Yuno is optimizing for EU debit market share and enterprise "
        f"logo retention over short-term margin. At €2.97B annual portfolio GMV, a single enterprise "
        f"defection (€480M GMV) costs more in long-term LTV than a 6bp rate concession. "
        f"This is a deliberate market-share play, not a margin defense.\n\n"
        f"[bold]Why enterprise churns at 18bp:[/bold] a representative enterprise merchant (€480M GMV) "
        f"pays €{enterprise_annual_premium_eur/1_000:.0f}K/year in premium vs a regional specialist "
        f"at 10bp. That exceeds most switching-cost thresholds — Yuno must demonstrate ≥€{enterprise_annual_premium_eur/1_000:.0f}K "
        f"in value uplift to justify retention.\n\n"
        f"[bold]What's sacrificed:[/bold] blended rate ~18bp (S1) → ~13bp (S3/S4). "
        f"Each bp surrendered = €{rev_per_bp/1_000:.0f}K annual revenue at portfolio scale. "
        f"Total rate give-up vs S1: ~5bp = ~€{5*rev_per_bp/1_000:.0f}K/year — justified by €648K "
        f"enterprise revenue recovered and enterprise LTV preserved.\n\n"
        f"[bold]S4 growth derivation:[/bold] 3.7pp approval rate advantage → ~{implied_growth_pct-4:.1f}% "
        f"organic GMV uplift (more transactions approved on existing book) + ~4% new merchant wins "
        f"= ~{implied_growth_pct:.1f}% ≈ 8% target. S4 is only viable with commercial execution — "
        f"it is not a pricing input and should not be presented to merchants as committed.\n\n"
        f"[bold]Breakeven cushion:[/bold] S3 GP can absorb {breakeven_churn_pct:.1f}% enterprise "
        f"churn (~{merchants_equiv} merchants) before falling below S2. "
        f"S1's modeled 50% churn is well inside this cushion — S3 dominates on GP unless churn "
        f"far exceeds expectations."
    )
    return Panel(content, title="Strategic Recommendation", border_style="green")


def build_churn_sensitivity_table(
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
) -> Table:
    """Churn sensitivity: how S1 Hold performs at varying enterprise retention levels vs S3."""
    table = Table(
        title="[bold cyan]Churn Sensitivity — S1 Hold Enterprise Retention vs S3 Tiered[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=80,
    )
    table.add_column("Retention Rate", style="dim white", min_width=16)
    table.add_column("S1 Revenue", justify="right", min_width=14)
    table.add_column("S1 GP", justify="right", min_width=14)
    table.add_column("vs S3 Revenue", justify="right", min_width=16)
    table.add_column("Break-even?", justify="center", min_width=12)

    s3_result = run_scenario(S3_TIERED, enterprise_gmv, mid_gmv, smb_gmv)

    for r in range(2, 11):
        retention = r / 10.0
        s1_variant = _replace(S1_HOLD, enterprise_retention=retention)
        s1_result = run_scenario(s1_variant, enterprise_gmv, mid_gmv, smb_gmv)
        delta = s1_result.total_revenue - s3_result.total_revenue
        delta_color = "green" if delta >= 0 else "red"
        breakeven_str = "[green]Yes[/green]" if delta >= 0 else "[red]No[/red]"
        delta_str = f"[{delta_color}]{fmt_eur(delta, 'M')}[/{delta_color}]"
        table.add_row(
            fmt_pct(retention),
            fmt_eur(s1_result.total_revenue, "M"),
            fmt_eur(s1_result.total_gross_profit, "M"),
            delta_str,
            breakeven_str,
        )

    table.add_section()
    table.add_row(
        "S3 Tiered (ref)",
        fmt_eur(s3_result.total_revenue, "M"),
        fmt_eur(s3_result.total_gross_profit, "M"),
        "—",
        "[bold green]Baseline[/bold green]",
    )

    return table


def build_segment_value_table() -> Table:
    """Per-segment ROI analysis using approval rate advantage at each tier's pricing."""
    table = Table(
        title="[bold cyan]Segment Value Analysis — Approval Rate ROI by Tier[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=90,
        caption="[dim]3.7pp approval rate delta applied uniformly across tiers; "
                "actual delta may vary by merchant volume, card mix, and routing complexity[/dim]",
    )
    table.add_column("Segment", style="dim white", min_width=20)
    table.add_column("Monthly GMV", justify="right", min_width=14)
    table.add_column("Incremental Rev/mo", justify="right", min_width=20)
    table.add_column("Pricing Premium/mo", justify="right", min_width=20)
    table.add_column("ROI Multiple", justify="right", min_width=14)
    table.add_column("Net Value/mo", justify="right", min_width=14)

    for seg in DEFAULT_SEGMENTS:
        analysis = ApprovalRateAnalysis(
            monthly_gmv=seg.monthly_gmv_eur,
            yuno_bp=seg.take_rate_bp,
        )
        inc_rev = analysis.calc_incremental_merchant_revenue()
        premium = analysis.calc_pricing_premium_cost()
        roi = analysis.calc_roi_multiple()
        net = analysis.calc_net_value()
        roi_color = "green" if roi > 5 else "yellow"
        table.add_row(
            seg.name,
            fmt_eur(seg.monthly_gmv_eur, "M"),
            f"[green]+{fmt_eur(inc_rev, 'K')}/mo[/green]",
            f"[yellow]+{fmt_eur(premium, 'K')}/mo[/yellow]",
            f"[bold {roi_color}]{roi:.1f}x[/bold {roi_color}]",
            f"[green]{fmt_eur(net, 'K')}/mo[/green]",
        )

    return table


def build_competitive_dynamics_panel() -> Panel:
    """Competitive positioning: structural cost argument, named competitors, EU market nuance."""
    breakeven = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
    breakeven_churn_pct = breakeven["breakeven_churn_pct"]
    merchants_equiv = breakeven["merchants_equiv"]

    total_gmv = PORTFOLIO_ENTERPRISE_GMV + PORTFOLIO_MID_GMV + PORTFOLIO_SMB_GMV
    s2_revenue = total_gmv * 10 / 10_000
    s3_result = run_scenario(S3_TIERED)
    s3_revenue = s3_result.total_revenue
    shortfall = s3_revenue - s2_revenue

    # Net margin at 10bp: 10 - 6.5 = 3.5bp; at S3 blended: ~13 - 6.5 = 6.5bp
    s2_net_bp = 10.0 - 6.5
    s3_blended_bp = s3_result.blended_take_rate_bp
    s3_net_bp = s3_blended_bp - 6.5

    content = (
        f"[bold]Why S2 flat 10bp is a margin trap:[/bold] revenue €{s2_revenue/1_000_000:.3f}M vs "
        f"S3 €{s3_revenue/1_000_000:.3f}M = €{shortfall/1_000:.0f}K shortfall. "
        f"Net margin: S2={s2_net_bp:.1f}bp vs S3={s3_net_bp:.1f}bp. "
        f"At portfolio scale, S2's 3.5bp net cannot sustain multi-region routing infrastructure.\n\n"
        f"[bold]Why regional specialists price at 10bp — structural cost advantage:[/bold]\n"
        f"Mollie (NL/DE), Stripe EU, Adyen (enterprise direct), and local acquirers operate "
        f"single-market infrastructure: one payment scheme (iDEAL, SEPA CT, or Bancontact), "
        f"one PSD2/AML compliance jurisdiction, no multi-currency settlement complexity, "
        f"and no orchestration or smart-retry layer. Lower fixed cost per transaction allows "
        f"them to price at 10bp sustainably. Yuno's multi-region model is structurally different: "
        f"cross-border routing, multi-country licensing, approval rate optimization, and retry "
        f"logic all add cost — but also create the value that justifies the premium.\n\n"
        f"[bold]Key EU debit market structure:[/bold] SEPA Direct Debit (pan-EU, ~8–12bp "
        f"interchange floor); iDEAL (NL, flat-fee scheme, dominated by local low-cost PSPs); "
        f"Bancontact (BE, local scheme, low interchange); SEPA Instant (growing, shifts "
        f"settlement economics). Regional players dominate single-scheme markets and cannot "
        f"serve merchants needing pan-EU coverage — Yuno's addressable moat.\n\n"
        f"[bold]Defensible positioning:[/bold] Yuno's 3.7pp approval rate advantage converts "
        f"to €1.48M/mo incremental merchant revenue on €40M GMV — worth a 8bp premium (~€32K/mo). "
        f"Regional specialists cannot replicate this without Yuno's multi-market routing data.\n\n"
        f"[bold]GP-based ROI:[/bold] ~16x GP per €1 premium "
        f"(3.7pp → €518K GP/mo at SMB tier on €32K premium). "
        f"S3 cushion vs S2: absorbs {breakeven_churn_pct:.1f}% enterprise churn "
        f"(~{merchants_equiv} merchants) before GP falls below S2 floor."
    )
    return Panel(content, title="Competitive Dynamics", border_style="yellow")


def build_implementation_table() -> Table:
    """Implementation roadmap: S3 → S4 migration with comms, objection handling, contingency."""
    table = Table(
        title="[bold cyan]Implementation Roadmap — S3 → S4 Migration[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        min_width=110,
    )
    table.add_column("Phase", style="dim white", min_width=6)
    table.add_column("Timeline", min_width=16)
    table.add_column("Action", min_width=52)
    table.add_column("Success Metric", min_width=30)

    # Merchant communication — pre-launch
    table.add_row(
        "0",
        "Month 0 (pre-launch)",
        "Draft segment-specific rate change letters. Frame as ROI: "
        "'Your 3.7pp approval rate advantage = €X incremental revenue; "
        "your net value after rate change = +€Y/mo.' Issue 90-day contractual notice "
        "to enterprise accounts; grandfather mid-contract merchants until renewal.",
        "Merchant acknowledgment ≥ 95%; zero surprise churn",
    )
    table.add_row("1", "Month 1–2", "Launch S3 tiered pricing for all new merchant onboarding", "100% new contracts at 12/15/18bp")
    table.add_row("2", "Month 3–6", "Migrate enterprise merchants to 12bp at contract renewal; "
        "offer approval rate dashboard access as part of transition to reinforce value narrative",
        "Enterprise retention ≥ 90%; blended rate ≥ 13bp")
    table.add_row("3", "Month 6–9", "Activate S4 growth incentives: volume rebates unlocked at 8% GMV uplift; "
        "target new merchant wins using approval rate ROI as lead pitch",
        "GMV +8% YoY; blended take rate ≥ 13bp")
    table.add_row("4", "Quarterly", "Rerun approval rate analysis per segment; re-validate 6.5bp cost assumption; "
        "review competitive floor (regional specialist pricing)", "ROI multiple ≥ 10x per segment")

    # Objection handling
    table.add_section()
    table.add_row(
        "OBJ",
        "Sales — ongoing",
        "[bold]'Competitor offers 8bp'[/bold] → Response: 'At your GMV, our 3.7pp approval "
        "rate advantage = €X/mo incremental revenue. After our 8bp premium (€Y/mo), your net "
        "gain is +€Z/mo. The competitor saves you €Y — but costs you €X+Z in lost revenue. "
        "We can model this live for your exact GMV.'",
        "Merchant signs at negotiated tier; no rate-match below 12bp",
    )

    # Contingency trigger
    table.add_row(
        "CTG",
        "Month 4 trigger",
        "[bold]If enterprise churn > 30% by Month 4:[/bold] activate emergency review — "
        "remodel churn assumptions with observed data, offer 12bp flat rate to at-risk "
        "accounts as a retention bridge, pause new S3 onboarding pending re-calibration. "
        "Do NOT drop to S2 (10bp) — floor at 12bp preserves viability.",
        "Churn stabilizes ≤ 25%; blended rate floor ≥ 12bp",
    )

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
    merchant_margin: float = 0.35,
    chargeback_rate: float = 0.5,
    failed_rate: float = 3.0,
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
        build_value_table(monthly_gmv, yuno_rate, competitor_rate, yuno_bp, competitor_bp, merchant_margin)
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
    merchant_margin: float = 0.35,
    chargeback_rate: float = 0.5,
    failed_rate: float = 3.0,
) -> None:
    """Run the interactive TUI loop.

    Renders the dashboard, then prompts the user to update inputs.
    Loops until the user types 'q' or presses Ctrl+C.
    """
    while True:
        console.clear()
        console.print(build_value_table(monthly_gmv, yuno_rate, competitor_rate, yuno_bp, competitor_bp, merchant_margin))
        console.print()
        console.print(build_scenario_table())
        console.print()
        console.print(build_sensitivity_table())
        console.print()
        console.print(build_breakeven_table())
        console.print()
        console.print(
            Columns([
                build_chargeback_table(monthly_gmv, chargeback_rate),
                build_recovery_table(monthly_gmv, failed_rate),
            ])
        )
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
        console.print()
        console.print(
            f"[dim]Current inputs:[/dim] GMV=[cyan]€{monthly_gmv/1_000_000:.0f}M/mo[/cyan]  "
            f"Yuno=[cyan]{yuno_rate}%[/cyan]  Competitor=[cyan]{competitor_rate}%[/cyan]  "
            f"Yuno rate=[cyan]{yuno_bp}bp[/cyan]  Competitor rate=[cyan]{competitor_bp}bp[/cyan]  "
            f"Margin=[cyan]{merchant_margin*100:.0f}%[/cyan]  "
            f"CB rate=[cyan]{chargeback_rate}%[/cyan]  "
            f"Failed rate=[cyan]{failed_rate}%[/cyan]"
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

            margin_input = Prompt.ask(
                f"  Merchant gross margin % (currently {merchant_margin*100:.0f})",
                default="",
                console=console,
            )
            if margin_input.strip().lower() == "q":
                break
            if margin_input.strip():
                merchant_margin = float(margin_input.strip()) / 100.0

            cb_input = Prompt.ask(
                f"  Chargeback rate % (currently {chargeback_rate})",
                default="",
                console=console,
            )
            if cb_input.strip().lower() == "q":
                break
            if cb_input.strip():
                chargeback_rate = float(cb_input.strip())

            failed_input = Prompt.ask(
                f"  Failed payment rate % (currently {failed_rate})",
                default="",
                console=console,
            )
            if failed_input.strip().lower() == "q":
                break
            if failed_input.strip():
                failed_rate = float(failed_input.strip())

        except (KeyboardInterrupt, EOFError):
            break
        except ValueError as e:
            console.print(f"[red]Invalid input: {e}. Keeping current values.[/red]")
            continue

    console.print("\n[dim]Goodbye.[/dim]")
