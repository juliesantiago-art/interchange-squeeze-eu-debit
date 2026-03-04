"""Unit tests for core financial models and calculation functions."""

import pytest
from interchange_squeeze.models import (
    MerchantSegment,
    calc_revenue,
    calc_gross_profit,
    calc_gross_margin,
    bp_to_rate,
    DEFAULT_COST_TO_SERVE_BP,
    MIN_VIABLE_RATE_BP,
    DEFAULT_SEGMENTS,
)


class TestBpToRate:
    def test_12bp(self):
        assert bp_to_rate(12) == pytest.approx(0.0012)

    def test_18bp(self):
        assert bp_to_rate(18) == pytest.approx(0.0018)

    def test_zero(self):
        assert bp_to_rate(0) == 0.0


class TestCalcRevenue:
    def test_enterprise_12bp(self):
        # €480M × 12bp = €576,000
        result = calc_revenue(480_000_000, 12)
        assert result == pytest.approx(576_000, rel=1e-6)

    def test_smb_18bp(self):
        # €40M × 18bp = €72,000
        result = calc_revenue(40_000_000, 18)
        assert result == pytest.approx(72_000, rel=1e-6)

    def test_mid_market_15bp(self):
        # €180M × 15bp = €270,000
        result = calc_revenue(180_000_000, 15)
        assert result == pytest.approx(270_000, rel=1e-6)

    def test_zero_gmv(self):
        assert calc_revenue(0, 12) == 0.0

    def test_zero_rate(self):
        assert calc_revenue(1_000_000, 0) == 0.0


class TestCalcGrossProfit:
    def test_basic(self):
        # €100M × 12bp revenue - €100M × 6.5bp cost = €120k - €65k = €55k
        result = calc_gross_profit(100_000_000, 12, 6.5)
        assert result == pytest.approx(55_000, rel=1e-6)

    def test_enterprise_12bp_cost_6_5bp(self):
        # €480M × (12 - 6.5)bp = €480M × 5.5bp = €264,000
        result = calc_gross_profit(480_000_000, 12, 6.5)
        assert result == pytest.approx(264_000, rel=1e-6)

    def test_negative_when_cost_exceeds_rate(self):
        # Take rate below cost → negative gross profit
        result = calc_gross_profit(100_000_000, 6, 6.5)
        assert result < 0

    def test_at_min_viable_rate(self):
        # At exactly MIN_VIABLE_RATE_BP (8bp) with 6.5bp cost → positive
        result = calc_gross_profit(100_000_000, MIN_VIABLE_RATE_BP, DEFAULT_COST_TO_SERVE_BP)
        assert result > 0


class TestCalcGrossMargin:
    def test_typical_margin(self):
        # 12bp rate, 6.5bp cost → margin = 5.5/12 ≈ 45.8%
        gross_profit = calc_gross_profit(100_000_000, 12, 6.5)
        revenue = calc_revenue(100_000_000, 12)
        margin = calc_gross_margin(gross_profit, revenue)
        assert margin == pytest.approx(5.5 / 12, rel=1e-6)

    def test_zero_revenue(self):
        assert calc_gross_margin(1000, 0) == 0.0

    def test_full_margin(self):
        # No cost → 100% margin
        margin = calc_gross_margin(100, 100)
        assert margin == pytest.approx(1.0)


class TestMerchantSegment:
    def test_monthly_gmv(self):
        seg = MerchantSegment("Test", 480_000_000, 12.0)
        assert seg.monthly_gmv_eur == pytest.approx(40_000_000)

    def test_default_cost(self):
        seg = MerchantSegment("Test", 100_000_000, 12.0)
        assert seg.cost_to_serve_bp == DEFAULT_COST_TO_SERVE_BP

    def test_custom_cost(self):
        seg = MerchantSegment("Test", 100_000_000, 12.0, cost_to_serve_bp=5.0)
        assert seg.cost_to_serve_bp == 5.0


class TestDefaultSegments:
    def test_three_segments(self):
        assert len(DEFAULT_SEGMENTS) == 3

    def test_enterprise_gmv(self):
        enterprise = DEFAULT_SEGMENTS[0]
        assert enterprise.annual_gmv_eur == 480_000_000
        assert enterprise.take_rate_bp == 12.0

    def test_total_gmv(self):
        total = sum(s.annual_gmv_eur for s in DEFAULT_SEGMENTS)
        assert total == pytest.approx(700_000_000)
