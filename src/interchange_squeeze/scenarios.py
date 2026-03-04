"""Scenario engine — four pricing strategies with full P&L comparison.

Models the core trade-off between rate preservation and volume retention
in the European debit interchange squeeze.
"""

from dataclasses import dataclass, field
from interchange_squeeze.models import calc_revenue, calc_gross_profit, calc_gross_margin


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
    """
    name: str
    description: str
    at_risk_rate_bp: float          # enterprise rate
    residual_debit_rate_bp: float   # mid-market rate
    credit_alt_rate_bp: float       # SMB / alt rate
    enterprise_retention: float = 1.0
    gmv_growth_rate: float = 0.0


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
)

S4_TIERED_GROWTH = Scenario(
    name="S4 Tiered + Growth",
    description="Tiered pricing with 8% GMV growth from improved approval rates and new merchant wins.",
    at_risk_rate_bp=12.0,
    residual_debit_rate_bp=15.0,
    credit_alt_rate_bp=18.0,
    enterprise_retention=1.0,
    gmv_growth_rate=0.08,
)

DEFAULT_SCENARIOS: list[Scenario] = [S1_HOLD, S2_FLAT_10BP, S3_TIERED, S4_TIERED_GROWTH]
