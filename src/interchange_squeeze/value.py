"""Approval rate → merchant revenue value quantification model.

Converts the payment approval rate delta between Yuno and a competitor
into incremental merchant revenue and ROI, making the pricing premium
tangible for merchant conversations.
"""

from dataclasses import dataclass, field


# --- Defaults (from Yuno EU debit data) ---
DEFAULT_YUNO_APPROVAL_RATE: float = 92.3       # %
DEFAULT_COMPETITOR_APPROVAL_RATE: float = 88.6  # %
DEFAULT_AVG_ORDER_VALUE_EUR: float = 85.0       # EUR
DEFAULT_MERCHANT_GROSS_MARGIN: float = 0.35     # 35% — typical ecom gross margin


@dataclass
class ApprovalRateAnalysis:
    """Models the value of Yuno's approval rate advantage.

    Args:
        monthly_gmv: Merchant's monthly GMV processed through Yuno (EUR)
        avg_order_value: Average transaction value (EUR)
        yuno_approval_rate: Yuno's authorization rate (%)
        competitor_approval_rate: Competitor's authorization rate (%)
        merchant_gross_margin: Merchant's gross margin on approved transactions
        yuno_bp: Yuno's take rate in basis points
        competitor_bp: Competitor's take rate in basis points
    """
    monthly_gmv: float
    avg_order_value: float = DEFAULT_AVG_ORDER_VALUE_EUR
    yuno_approval_rate: float = DEFAULT_YUNO_APPROVAL_RATE
    competitor_approval_rate: float = DEFAULT_COMPETITOR_APPROVAL_RATE
    merchant_gross_margin: float = DEFAULT_MERCHANT_GROSS_MARGIN
    yuno_bp: float = 18.0       # SMB rate (highest tier — worst-case for ROI)
    competitor_bp: float = 10.0  # Market floor / competitor rate

    @property
    def approval_rate_delta(self) -> float:
        """Percentage point difference in approval rates."""
        return self.yuno_approval_rate - self.competitor_approval_rate

    def calc_monthly_transactions(self) -> float:
        """Estimated total monthly transaction attempts."""
        return self.monthly_gmv / self.avg_order_value

    def calc_incremental_approvals(self) -> float:
        """Additional approved transactions per month due to higher approval rate."""
        total_transactions = self.calc_monthly_transactions()
        return total_transactions * (self.approval_rate_delta / 100.0)

    def calc_incremental_merchant_revenue(self) -> float:
        """Additional merchant revenue per month from incremental approvals (EUR)."""
        incremental = self.calc_incremental_approvals()
        return incremental * self.avg_order_value

    def calc_pricing_premium_cost(self) -> float:
        """Monthly cost of Yuno's higher take rate vs competitor (EUR).

        Positive = Yuno is more expensive.
        """
        rate_delta_bp = self.yuno_bp - self.competitor_bp
        return self.monthly_gmv * (rate_delta_bp / 10_000.0)

    def calc_incremental_gross_profit(self) -> float:
        """Merchant's incremental gross profit from extra approvals (EUR)."""
        return self.calc_incremental_merchant_revenue() * self.merchant_gross_margin

    def calc_net_value(self) -> float:
        """Net monthly value to merchant: incremental GP minus pricing premium (EUR).

        Positive = Yuno is net beneficial despite higher price.
        """
        return self.calc_incremental_gross_profit() - self.calc_pricing_premium_cost()

    def calc_roi_multiple(self) -> float:
        """ROI multiple: incremental merchant revenue per EUR of pricing premium.

        e.g. 46.0 = merchant gains €46 in revenue for every €1 extra spent on Yuno.
        Returns 0 if pricing premium is zero or negative (no cost premium).
        """
        premium = self.calc_pricing_premium_cost()
        if premium <= 0:
            return 0.0
        return self.calc_incremental_merchant_revenue() / premium
