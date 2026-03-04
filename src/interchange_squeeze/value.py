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
        """Net profit per EUR of pricing premium.

        e.g. 16.0 = merchant gains €16 in gross profit for every €1 extra spent on Yuno.
        Returns 0 if pricing premium is zero or negative (no cost premium).
        """
        premium = self.calc_pricing_premium_cost()
        if premium <= 0:
            return 0.0
        return self.calc_incremental_gross_profit() / premium


@dataclass
class ChargebackAnalysis:
    """Models chargeback cost savings from smart payment routing.

    Args:
        monthly_gmv: Merchant's monthly GMV (EUR)
        avg_order_value: Average transaction value (EUR)
        chargeback_rate_pct: % of transactions resulting in a chargeback
        expected_reduction_pct: Percentage point reduction achievable via smart routing
        chargeback_fee_eur: Acquirer fee per chargeback (EUR)
    """
    monthly_gmv: float
    avg_order_value: float = 85.0
    chargeback_rate_pct: float = 0.5        # % of transactions
    expected_reduction_pct: float = 0.1     # pp reduction from smart routing
    chargeback_fee_eur: float = 20.0        # acquirer fee per chargeback

    def calc_monthly_chargebacks(self) -> float:
        """Total monthly chargebacks at current rate."""
        transactions = self.monthly_gmv / self.avg_order_value
        return transactions * (self.chargeback_rate_pct / 100.0)

    def calc_chargebacks_avoided(self) -> float:
        """Monthly chargebacks avoided via smart routing."""
        transactions = self.monthly_gmv / self.avg_order_value
        return transactions * (self.expected_reduction_pct / 100.0)

    def calc_fee_savings(self) -> float:
        """Monthly acquirer fee savings from avoided chargebacks (EUR)."""
        return self.calc_chargebacks_avoided() * self.chargeback_fee_eur

    def calc_dispute_cost_savings(self) -> float:
        """Monthly operational cost savings from avoided disputes (EUR).

        Estimated at ~€15 per avoided dispute (internal handling cost).
        """
        return self.calc_chargebacks_avoided() * 15.0

    def calc_total_monthly_savings(self) -> float:
        """Total monthly savings: acquirer fees + operational dispute costs (EUR)."""
        return self.calc_fee_savings() + self.calc_dispute_cost_savings()


@dataclass
class FailedPaymentRecovery:
    """Models revenue recovered via intelligent retry logic on failed payments.

    Args:
        monthly_gmv: Merchant's monthly GMV (EUR)
        avg_order_value: Average transaction value (EUR)
        failed_payment_rate_pct: % of transactions that fail initially
        retry_recovery_rate_pct: % of failed transactions recovered via retry logic
    """
    monthly_gmv: float
    avg_order_value: float = 85.0
    failed_payment_rate_pct: float = 3.0    # % of transactions that fail
    retry_recovery_rate_pct: float = 25.0   # % of failed that retry logic recovers

    def calc_failed_transactions(self) -> float:
        """Total monthly failed transaction attempts."""
        transactions = self.monthly_gmv / self.avg_order_value
        return transactions * (self.failed_payment_rate_pct / 100.0)

    def calc_recovered_transactions(self) -> float:
        """Monthly transactions recovered via retry logic."""
        return self.calc_failed_transactions() * (self.retry_recovery_rate_pct / 100.0)

    def calc_recovered_revenue(self) -> float:
        """Monthly revenue recovered via retry logic (EUR)."""
        return self.calc_recovered_transactions() * self.avg_order_value
