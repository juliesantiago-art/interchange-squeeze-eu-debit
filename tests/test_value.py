"""Unit tests for approval rate value quantification model."""

import pytest
from interchange_squeeze.value import (
    ApprovalRateAnalysis,
    ChargebackAnalysis,
    FailedPaymentRecovery,
    DEFAULT_YUNO_APPROVAL_RATE,
    DEFAULT_COMPETITOR_APPROVAL_RATE,
    DEFAULT_AVG_ORDER_VALUE_EUR,
)


MERCHANT_A_GMV = 40_000_000  # €40M/month


@pytest.fixture
def merchant_a():
    """Merchant A baseline: €40M/month, default approval rates, 18bp vs 10bp."""
    return ApprovalRateAnalysis(
        monthly_gmv=MERCHANT_A_GMV,
        avg_order_value=DEFAULT_AVG_ORDER_VALUE_EUR,
        yuno_approval_rate=DEFAULT_YUNO_APPROVAL_RATE,
        competitor_approval_rate=DEFAULT_COMPETITOR_APPROVAL_RATE,
        yuno_bp=18.0,
        competitor_bp=10.0,
    )


class TestApprovalRateDelta:
    def test_default_delta(self, merchant_a):
        # 92.3% - 88.6% = 3.7pp
        assert merchant_a.approval_rate_delta == pytest.approx(3.7, abs=1e-9)

    def test_zero_delta(self):
        a = ApprovalRateAnalysis(1_000_000, yuno_approval_rate=90.0, competitor_approval_rate=90.0)
        assert a.approval_rate_delta == 0.0


class TestMonthlyTransactions:
    def test_merchant_a(self, merchant_a):
        # €40M / €85 ≈ 470,588
        expected = 40_000_000 / 85
        assert merchant_a.calc_monthly_transactions() == pytest.approx(expected, rel=1e-6)


class TestIncrementalApprovals:
    def test_merchant_a(self, merchant_a):
        # 470,588 × 3.7% ≈ 17,412
        transactions = 40_000_000 / 85
        expected = transactions * 3.7 / 100
        assert merchant_a.calc_incremental_approvals() == pytest.approx(expected, rel=1e-6)


class TestIncrementalMerchantRevenue:
    def test_merchant_a_approx_1_48m(self, merchant_a):
        # ~€1.48M/month incremental revenue
        result = merchant_a.calc_incremental_merchant_revenue()
        assert result == pytest.approx(1_480_000, rel=0.01)  # within 1%

    def test_zero_delta(self):
        a = ApprovalRateAnalysis(
            40_000_000,
            yuno_approval_rate=90.0,
            competitor_approval_rate=90.0,
        )
        assert a.calc_incremental_merchant_revenue() == 0.0


class TestPricingPremiumCost:
    def test_merchant_a_premium(self, merchant_a):
        # €40M × 8bp (18-10) = €32,000/month
        assert merchant_a.calc_pricing_premium_cost() == pytest.approx(32_000, rel=1e-6)

    def test_equal_rates_zero_cost(self):
        a = ApprovalRateAnalysis(40_000_000, yuno_bp=10.0, competitor_bp=10.0)
        assert a.calc_pricing_premium_cost() == 0.0

    def test_competitor_more_expensive(self):
        # If competitor is pricier, premium is negative (Yuno is cheaper)
        a = ApprovalRateAnalysis(40_000_000, yuno_bp=10.0, competitor_bp=15.0)
        assert a.calc_pricing_premium_cost() < 0


class TestROIMultiple:
    def test_merchant_a_roi_approx_16x(self, merchant_a):
        # ~16x ROI (net profit basis): incremental GP / premium
        # GP ≈ €1.48M × 35% ≈ €518k; premium = €32k; ROI ≈ 16.19x
        result = merchant_a.calc_roi_multiple()
        expected = merchant_a.calc_incremental_gross_profit() / merchant_a.calc_pricing_premium_cost()
        assert result == pytest.approx(expected, rel=1e-6)
        assert result == pytest.approx(16.19, rel=0.01)

    def test_zero_premium_returns_zero(self):
        a = ApprovalRateAnalysis(40_000_000, yuno_bp=10.0, competitor_bp=10.0)
        assert a.calc_roi_multiple() == 0.0

    def test_roi_greater_than_one(self, merchant_a):
        # The value proposition must be significantly positive
        assert merchant_a.calc_roi_multiple() > 10.0


class TestChargebackAnalysis:
    @pytest.fixture
    def cb(self):
        return ChargebackAnalysis(monthly_gmv=40_000_000)

    def test_monthly_chargebacks(self, cb):
        # 40M / 85 * 0.5% ≈ 2352.9
        transactions = 40_000_000 / 85
        expected = transactions * 0.5 / 100
        assert cb.calc_monthly_chargebacks() == pytest.approx(expected, rel=1e-6)

    def test_chargebacks_avoided(self, cb):
        # 40M / 85 * 0.1% ≈ 470.6
        transactions = 40_000_000 / 85
        expected = transactions * 0.1 / 100
        assert cb.calc_chargebacks_avoided() == pytest.approx(expected, rel=1e-6)

    def test_fee_savings(self, cb):
        # chargebacks_avoided × €20
        expected = cb.calc_chargebacks_avoided() * 20.0
        assert cb.calc_fee_savings() == pytest.approx(expected, rel=1e-6)

    def test_dispute_cost_savings(self, cb):
        # chargebacks_avoided × €15
        expected = cb.calc_chargebacks_avoided() * 15.0
        assert cb.calc_dispute_cost_savings() == pytest.approx(expected, rel=1e-6)

    def test_total_monthly_savings(self, cb):
        expected = cb.calc_fee_savings() + cb.calc_dispute_cost_savings()
        assert cb.calc_total_monthly_savings() == pytest.approx(expected, rel=1e-6)

    def test_total_savings_positive(self, cb):
        assert cb.calc_total_monthly_savings() > 0

    def test_zero_reduction_means_no_savings(self):
        cb = ChargebackAnalysis(monthly_gmv=40_000_000, expected_reduction_pct=0.0)
        assert cb.calc_fee_savings() == 0.0
        assert cb.calc_total_monthly_savings() == 0.0


class TestFailedPaymentRecovery:
    @pytest.fixture
    def fpr(self):
        return FailedPaymentRecovery(monthly_gmv=40_000_000)

    def test_failed_transactions(self, fpr):
        # 40M / 85 * 3% ≈ 14117.6
        transactions = 40_000_000 / 85
        expected = transactions * 3.0 / 100
        assert fpr.calc_failed_transactions() == pytest.approx(expected, rel=1e-6)

    def test_recovered_transactions(self, fpr):
        # failed × 25%
        expected = fpr.calc_failed_transactions() * 0.25
        assert fpr.calc_recovered_transactions() == pytest.approx(expected, rel=1e-6)

    def test_recovered_revenue(self, fpr):
        expected = fpr.calc_recovered_transactions() * 85.0
        assert fpr.calc_recovered_revenue() == pytest.approx(expected, rel=1e-6)

    def test_recovered_revenue_positive(self, fpr):
        assert fpr.calc_recovered_revenue() > 0

    def test_zero_recovery_rate(self):
        fpr = FailedPaymentRecovery(monthly_gmv=40_000_000, retry_recovery_rate_pct=0.0)
        assert fpr.calc_recovered_transactions() == 0.0
        assert fpr.calc_recovered_revenue() == 0.0


class TestNetValue:
    def test_positive_net_value(self, merchant_a):
        # Even with premium, net value should be strongly positive
        net = merchant_a.calc_net_value()
        assert net > 0

    def test_net_value_magnitude(self, merchant_a):
        # Incremental GP (€518k) - premium (€32k) ≈ €486k
        expected_gp = merchant_a.calc_incremental_merchant_revenue() * merchant_a.merchant_gross_margin
        expected_net = expected_gp - merchant_a.calc_pricing_premium_cost()
        assert merchant_a.calc_net_value() == pytest.approx(expected_net, rel=1e-6)
