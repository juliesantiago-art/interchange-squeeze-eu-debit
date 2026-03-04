"""Core financial dataclasses and pure calculation functions."""

from dataclasses import dataclass, field

# --- Constants ---
DEFAULT_COST_TO_SERVE_BP: float = 6.5  # basis points
MIN_VIABLE_RATE_BP: float = 8.0        # basis points — floor below which debit is unprofitable
BASIS_POINTS_DIVISOR: float = 10_000.0


@dataclass
class MerchantSegment:
    """Represents a merchant segment with GMV and pricing parameters."""
    name: str
    annual_gmv_eur: float            # EUR
    take_rate_bp: float              # basis points (current blended take rate)
    cost_to_serve_bp: float = field(default=DEFAULT_COST_TO_SERVE_BP)

    @property
    def monthly_gmv_eur(self) -> float:
        return self.annual_gmv_eur / 12.0


def bp_to_rate(bp: float) -> float:
    """Convert basis points to decimal rate."""
    return bp / BASIS_POINTS_DIVISOR


def calc_revenue(gmv: float, take_rate_bp: float) -> float:
    """Calculate gross revenue from GMV and take rate in basis points.

    Args:
        gmv: Gross Merchandise Volume in EUR
        take_rate_bp: Take rate in basis points (e.g. 12 = 0.12%)

    Returns:
        Revenue in EUR
    """
    return gmv * bp_to_rate(take_rate_bp)


def calc_gross_profit(gmv: float, take_rate_bp: float, cost_bp: float) -> float:
    """Calculate gross profit (revenue minus cost to serve).

    Args:
        gmv: Gross Merchandise Volume in EUR
        take_rate_bp: Take rate in basis points
        cost_bp: Cost to serve in basis points

    Returns:
        Gross profit in EUR
    """
    revenue = calc_revenue(gmv, take_rate_bp)
    cost = calc_revenue(gmv, cost_bp)
    return revenue - cost


def calc_gross_margin(gross_profit: float, revenue: float) -> float:
    """Calculate gross margin percentage.

    Args:
        gross_profit: Gross profit in EUR
        revenue: Revenue in EUR

    Returns:
        Gross margin as a fraction (e.g. 0.46 = 46%)
    """
    if revenue == 0:
        return 0.0
    return gross_profit / revenue


# --- Predefined merchant segments from Yuno EU debit portfolio ---

SEGMENT_ENTERPRISE = MerchantSegment(
    name="Enterprise (>€500M GMV)",
    annual_gmv_eur=480_000_000,
    take_rate_bp=12.0,
)

SEGMENT_MID_MARKET = MerchantSegment(
    name="Mid-Market (€50-500M GMV)",
    annual_gmv_eur=180_000_000,
    take_rate_bp=15.0,
)

SEGMENT_SMB = MerchantSegment(
    name="SMB (<€50M GMV)",
    annual_gmv_eur=40_000_000,
    take_rate_bp=18.0,
)

DEFAULT_SEGMENTS: list[MerchantSegment] = [
    SEGMENT_ENTERPRISE,
    SEGMENT_MID_MARKET,
    SEGMENT_SMB,
]
