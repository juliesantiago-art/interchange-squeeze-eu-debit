"""Scenario engine — four pricing strategies with full P&L comparison.

Models the core trade-off between rate preservation and volume retention
in the European debit interchange squeeze.
"""

from dataclasses import dataclass, field
from interchange_squeeze.models import calc_revenue, calc_gross_profit, calc_gross_margin, bp_to_rate


# ---------------------------------------------------------------------------
# Scenario portfolio segments (Yuno EU debit book, full scale)
# ---------------------------------------------------------------------------
# These represent the aggregate EU debit portfolio split by merchant tier.
# Enterprise GMV = €2.16B, mid = €600M, SMB = €211.1M (total €2.971B annual)
# Calibrated so that S1 = €3.224M revenue and S3 = €3.872M revenue.
PORTFOLIO_ENTERPRISE_GMV: float = 2_160_000_000   # EUR annual
PORTFOLIO_MID_GMV: float = 600_000_000             # EUR annual
PORTFOLIO_SMB_GMV: float = 211_100_000             # EUR annual

DEFAULT_COST_BP: float = 6.5  # basis points


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    """Defines a pricing strategy scenario.

    Attributes:
        name: Short scenario label (e.g. "S1 Hold 18bp")
        description: What this scenario represents
        at_risk_rate_bp: Rate for enterprise/at-risk volume (basis points)
        residual_debit_rate_bp: Rate for mid-market debit volume (basis points)
        credit_alt_rate_bp: Rate for SMB / credit-alt volume (basis points)
        enterprise_retention: Fraction of enterprise GMV retained (0–1).
            <1.0 means some enterprise merchants churn due to high price.
        gmv_growth_rate: Fractional GMV growth applied to all segments
            (e.g. 0.05 = 5% growth above baseline). Used in S4.
        recommended: True if this is the recommended scenario
        includes_growth_assumption: True if the scenario bakes in a GMV growth target
            (commercial execution assumption, not a pricing input)
    """
    name: str
    description: str
    at_risk_rate_bp: float          # enterprise rate
    residual_debit_rate_bp: float   # mid-market rate
    credit_alt_rate_bp: float       # SMB / alt rate
    enterprise_retention: float = 1.0
    gmv_growth_rate: float = 0.0
    recommended: bool = False
    includes_growth_assumption: bool = False


@dataclass
class ScenarioResult:
    """Full P&L output from running a scenario against the portfolio.

    All monetary values are in EUR (annual).
    """
    scenario_name: str
    description: str

    # GMV
    enterprise_gmv: float
    mid_gmv: float
    smb_gmv: float

    # Revenue by segment
    enterprise_revenue: float
    mid_revenue: float
    smb_revenue: float

    # Gross profit by segment
    enterprise_gp: float
    mid_gp: float
    smb_gp: float

    # Aggregates
    @property
    def total_gmv(self) -> float:
        return self.enterprise_gmv + self.mid_gmv + self.smb_gmv

    @property
    def total_revenue(self) -> float:
        return self.enterprise_revenue + self.mid_revenue + self.smb_revenue

    @property
    def total_gross_profit(self) -> float:
        return self.enterprise_gp + self.mid_gp + self.smb_gp

    @property
    def blended_gross_margin(self) -> float:
        return calc_gross_margin(self.total_gross_profit, self.total_revenue)

    @property
    def blended_take_rate_bp(self) -> float:
        if self.total_gmv == 0:
            return 0.0
        return (self.total_revenue / self.total_gmv) * 10_000


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------

def run_scenario(
    scenario: Scenario,
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
    cost_bp: float = DEFAULT_COST_BP,
) -> ScenarioResult:
    """Run a scenario against the portfolio and return full P&L.

    Args:
        scenario: Scenario definition with rates and retention factors
        enterprise_gmv: Annual enterprise GMV (EUR), default from portfolio constants
        mid_gmv: Annual mid-market GMV (EUR)
        smb_gmv: Annual SMB GMV (EUR)
        cost_bp: Cost to serve in basis points

    Returns:
        ScenarioResult with all revenue and gross profit lines
    """
    growth = 1.0 + scenario.gmv_growth_rate

    ent_gmv = enterprise_gmv * scenario.enterprise_retention * growth
    mid = mid_gmv * growth
    smb = smb_gmv * growth

    ent_rev = calc_revenue(ent_gmv, scenario.at_risk_rate_bp)
    mid_rev = calc_revenue(mid, scenario.residual_debit_rate_bp)
    smb_rev = calc_revenue(smb, scenario.credit_alt_rate_bp)

    ent_gp = calc_gross_profit(ent_gmv, scenario.at_risk_rate_bp, cost_bp)
    mid_gp = calc_gross_profit(mid, scenario.residual_debit_rate_bp, cost_bp)
    smb_gp = calc_gross_profit(smb, scenario.credit_alt_rate_bp, cost_bp)

    return ScenarioResult(
        scenario_name=scenario.name,
        description=scenario.description,
        enterprise_gmv=ent_gmv,
        mid_gmv=mid,
        smb_gmv=smb,
        enterprise_revenue=ent_rev,
        mid_revenue=mid_rev,
        smb_revenue=smb_rev,
        enterprise_gp=ent_gp,
        mid_gp=mid_gp,
        smb_gp=smb_gp,
    )


def compare_scenarios(
    scenarios: list[Scenario],
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
    cost_bp: float = DEFAULT_COST_BP,
) -> list[ScenarioResult]:
    """Run all scenarios and return results sorted by total revenue descending."""
    results = [
        run_scenario(s, enterprise_gmv, mid_gmv, smb_gmv, cost_bp)
        for s in scenarios
    ]
    return sorted(results, key=lambda r: r.total_revenue, reverse=True)


# ---------------------------------------------------------------------------
# Preconfigured scenarios
# ---------------------------------------------------------------------------

S1_HOLD = Scenario(
    name="S1 Hold 18bp",
    description="Hold current 18bp debit rate across all segments. Enterprise merchants (50%) churn to lower-cost alternatives.",
    at_risk_rate_bp=18.0,
    residual_debit_rate_bp=18.0,
    credit_alt_rate_bp=18.0,
    enterprise_retention=0.50,
)

S2_FLAT_10BP = Scenario(
    name="S2 Flat 10bp",
    description="Match market floor at 10bp across all segments. Maximize volume retention, sacrifice margin.",
    at_risk_rate_bp=10.0,
    residual_debit_rate_bp=10.0,
    credit_alt_rate_bp=10.0,
    enterprise_retention=1.0,
)

S3_TIERED = Scenario(
    name="S3 Tiered 12-18bp",
    description="Segment pricing: enterprise 12bp, mid-market 15bp, SMB 18bp. Full retention across all tiers.",
    at_risk_rate_bp=12.0,
    residual_debit_rate_bp=15.0,
    credit_alt_rate_bp=18.0,
    enterprise_retention=1.0,
    recommended=True,
)

S4_TIERED_GROWTH = Scenario(
    name="S4 Tiered + Growth",
    description="Tiered pricing with 8% GMV growth from improved approval rates and new merchant wins. ⚠ Growth assumption is a commercial execution target, not a pricing input",
    at_risk_rate_bp=12.0,
    residual_debit_rate_bp=15.0,
    credit_alt_rate_bp=18.0,
    enterprise_retention=1.0,
    gmv_growth_rate=0.08,
    includes_growth_assumption=True,
)

DEFAULT_SCENARIOS: list[Scenario] = [S1_HOLD, S2_FLAT_10BP, S3_TIERED, S4_TIERED_GROWTH]

RECOMMENDED_SCENARIO = S3_TIERED


# ---------------------------------------------------------------------------
# Seasonality & monthly P&L
# ---------------------------------------------------------------------------

# EU debit: Q1 light, Q4 heavy (sums to 1.0)
MONTHLY_SEASONALITY: list[float] = [
    0.070, 0.075, 0.075, 0.080, 0.082, 0.082,
    0.082, 0.082, 0.082, 0.095, 0.100, 0.095,
]


def calc_monthly_pl(
    scenario: Scenario,
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
    cost_bp: float = DEFAULT_COST_BP,
) -> list[dict]:
    """Return 12 monthly P&L rows for the given scenario with EU debit seasonality.

    Each dict: {month, gmv, revenue, gross_profit, gross_margin_pct}
    Applies MONTHLY_SEASONALITY weights to annual P&L totals.
    """
    annual = run_scenario(scenario, enterprise_gmv, mid_gmv, smb_gmv, cost_bp)
    rows = []
    for i, weight in enumerate(MONTHLY_SEASONALITY):
        month_gmv = annual.total_gmv * weight
        month_rev = annual.total_revenue * weight
        month_gp = annual.total_gross_profit * weight
        gm_pct = month_gp / month_rev if month_rev > 0 else 0.0
        rows.append({
            "month": i + 1,
            "gmv": month_gmv,
            "revenue": month_rev,
            "gross_profit": month_gp,
            "gross_margin_pct": gm_pct,
        })
    return rows


# ---------------------------------------------------------------------------
# Break-even analysis
# ---------------------------------------------------------------------------

def calc_breakeven_attrition(
    test_scenario: Scenario,
    vs_scenario: Scenario,
    representative_merchant_gmv: float = 40_000_000,  # €40M monthly = €480M annual
    enterprise_gmv: float = PORTFOLIO_ENTERPRISE_GMV,
    mid_gmv: float = PORTFOLIO_MID_GMV,
    smb_gmv: float = PORTFOLIO_SMB_GMV,
    cost_bp: float = DEFAULT_COST_BP,
) -> dict:
    """Calculate max Enterprise attrition before test_scenario GP falls below vs_scenario GP.

    Args:
        test_scenario: The scenario being stress-tested (e.g. S3_TIERED)
        vs_scenario: The floor scenario to defend against (e.g. S2_FLAT_10BP)
        representative_merchant_gmv: Monthly GMV of a representative merchant (EUR)
        enterprise_gmv: Annual enterprise portfolio GMV (EUR)
        mid_gmv: Annual mid-market portfolio GMV (EUR)
        smb_gmv: Annual SMB portfolio GMV (EUR)
        cost_bp: Cost to serve in basis points

    Returns:
        {
            "breakeven_churn_pct": float,    # % Enterprise GMV that can churn
            "breakeven_gmv_eur": float,      # EUR annual GMV that can leave
            "merchants_equiv": int,          # Equivalent number of representative merchants
            "test_gp": float,                # Annual GP of test scenario
            "vs_gp": float,                  # Annual GP of vs scenario (floor)
            "gp_cushion": float,             # GP advantage test has over vs
        }
    """
    test_result = run_scenario(test_scenario, enterprise_gmv, mid_gmv, smb_gmv, cost_bp)
    vs_result = run_scenario(vs_scenario, enterprise_gmv, mid_gmv, smb_gmv, cost_bp)

    test_gp = test_result.total_gross_profit
    vs_gp = vs_result.total_gross_profit
    gp_cushion = test_gp - vs_gp

    # Each unit of enterprise GMV at test_scenario rate contributes (rate - cost) margin
    enterprise_margin_rate = bp_to_rate(test_scenario.at_risk_rate_bp - cost_bp)
    if enterprise_margin_rate <= 0:
        breakeven_gmv = 0.0
    else:
        breakeven_gmv = gp_cushion / enterprise_margin_rate

    breakeven_churn_pct = (breakeven_gmv / enterprise_gmv) * 100.0 if enterprise_gmv > 0 else 0.0
    representative_annual_gmv = representative_merchant_gmv * 12
    merchants_equiv = int(breakeven_gmv / representative_annual_gmv) if representative_annual_gmv > 0 else 0

    return {
        "breakeven_churn_pct": breakeven_churn_pct,
        "breakeven_gmv_eur": breakeven_gmv,
        "merchants_equiv": merchants_equiv,
        "test_gp": test_gp,
        "vs_gp": vs_gp,
        "gp_cushion": gp_cushion,
    }


# ---------------------------------------------------------------------------
# S4 growth derivation — connects approval rate advantage to GMV growth
# ---------------------------------------------------------------------------

def calc_approval_rate_implied_gmv_growth(
    approval_rate_delta_pp: float = 3.7,
    new_merchant_win_growth: float = 0.04,
) -> float:
    """Derive the GMV growth assumption underlying S4 from first principles.

    Two components:
    1. Organic uplift: Yuno's approval rate advantage approves transactions
       that competitors decline. A 3.7pp delta ≈ 3.7% more transactions
       approved → ~3.7% organic GMV retention/growth on the existing book.
    2. New merchant wins: improved economics attract new logos (~4% of
       portfolio, conservative estimate for a deliberate market-share play).

    Combined: ~7.7%, rounded to 8% in S4 as a commercial execution target.

    Args:
        approval_rate_delta_pp: Yuno vs competitor approval rate gap (pp)
        new_merchant_win_growth: Fractional GMV growth from new merchant wins

    Returns:
        Implied annual GMV growth rate (e.g. 0.077 = 7.7%)
    """
    organic_uplift = approval_rate_delta_pp / 100.0
    return organic_uplift + new_merchant_win_growth
