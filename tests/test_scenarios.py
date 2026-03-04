"""Unit tests for scenario engine — four pricing strategies."""

import pytest
from interchange_squeeze.scenarios import (
    Scenario,
    ScenarioResult,
    run_scenario,
    compare_scenarios,
    calc_breakeven_attrition,
    calc_monthly_pl,
    S1_HOLD,
    S2_FLAT_10BP,
    S3_TIERED,
    S4_TIERED_GROWTH,
    DEFAULT_SCENARIOS,
    PORTFOLIO_ENTERPRISE_GMV,
    PORTFOLIO_MID_GMV,
    PORTFOLIO_SMB_GMV,
    MONTHLY_SEASONALITY,
    RECOMMENDED_SCENARIO,
)


class TestRunScenario:
    def test_s1_revenue(self):
        result = run_scenario(S1_HOLD)
        # Enterprise: €2.16B × 50% × 18bp = €1,944,000
        # Mid: €600M × 18bp = €1,080,000
        # SMB: €211.1M × 18bp = €379,980
        # Total ≈ €3,403,980... wait: mid uses residual_debit_rate, not enterprise rate
        # Mid: €600M × 18bp = €1,080,000 (residual_debit_rate = 18bp in S1)
        assert result.total_revenue == pytest.approx(3_403_980, rel=1e-4)

    def test_s1_enterprise_churn(self):
        result = run_scenario(S1_HOLD)
        # Enterprise GMV retained = 50%
        assert result.enterprise_gmv == pytest.approx(PORTFOLIO_ENTERPRISE_GMV * 0.5, rel=1e-9)

    def test_s3_revenue(self):
        result = run_scenario(S3_TIERED)
        # Enterprise: €2.16B × 12bp = €2,592,000
        # Mid: €600M × 15bp = €900,000
        # SMB: €211.1M × 18bp = €379,980
        # Total = €3,871,980
        assert result.total_revenue == pytest.approx(3_871_980, rel=1e-6)

    def test_s3_full_enterprise_retention(self):
        result = run_scenario(S3_TIERED)
        assert result.enterprise_gmv == pytest.approx(PORTFOLIO_ENTERPRISE_GMV, rel=1e-9)

    def test_s2_lowest_rate_highest_gmv(self):
        result = run_scenario(S2_FLAT_10BP)
        # All at 10bp with 100% retention
        total_gmv = PORTFOLIO_ENTERPRISE_GMV + PORTFOLIO_MID_GMV + PORTFOLIO_SMB_GMV
        assert result.total_gmv == pytest.approx(total_gmv, rel=1e-9)
        assert result.total_revenue == pytest.approx(total_gmv * 10 / 10_000, rel=1e-9)

    def test_s4_growth_applied(self):
        result = run_scenario(S4_TIERED_GROWTH)
        s3_result = run_scenario(S3_TIERED)
        # S4 should have 8% more GMV and revenue
        assert result.total_gmv == pytest.approx(s3_result.total_gmv * 1.08, rel=1e-6)
        assert result.total_revenue == pytest.approx(s3_result.total_revenue * 1.08, rel=1e-6)

    def test_gross_profit_positive_above_cost(self):
        result = run_scenario(S3_TIERED)
        # At 12bp rate with 6.5bp cost, GP is positive
        assert result.enterprise_gp > 0
        assert result.mid_gp > 0
        assert result.smb_gp > 0
        assert result.total_gross_profit > 0

    def test_blended_margin_between_0_and_1(self):
        for s in DEFAULT_SCENARIOS:
            result = run_scenario(s)
            assert 0 < result.blended_gross_margin < 1


class TestS1vsS3:
    def test_s3_outperforms_s1_on_revenue(self):
        s1 = run_scenario(S1_HOLD)
        s3 = run_scenario(S3_TIERED)
        assert s3.total_revenue > s1.total_revenue

    def test_s1_mid_revenue_uses_same_rate_as_enterprise(self):
        """In S1 all at 18bp — mid and SMB pay same rate as enterprise."""
        s1 = run_scenario(S1_HOLD)
        # All rates are 18bp in S1
        assert S1_HOLD.at_risk_rate_bp == S1_HOLD.residual_debit_rate_bp == 18.0

    def test_s3_enterprise_rate_lower_than_s1(self):
        assert S3_TIERED.at_risk_rate_bp < S1_HOLD.at_risk_rate_bp

    def test_s3_s1_rev_difference_648k(self):
        """S3 outperforms S1 on enterprise revenue by exactly €648,000."""
        s1 = run_scenario(S1_HOLD)
        s3 = run_scenario(S3_TIERED)
        # The mid and SMB revenue differs too (15bp vs 18bp for mid in S3 vs S1)
        # Enterprise contribution to difference:
        ent_s1 = s1.enterprise_revenue
        ent_s3 = s3.enterprise_revenue
        # €2.16B × (12bp - 18bp×50%) = €2.16B × (12 - 9)bp = €2.16B × 3bp = €648,000
        enterprise_diff = ent_s3 - ent_s1
        assert enterprise_diff == pytest.approx(648_000, rel=1e-4)

    def test_s3_higher_revenue_but_s1_higher_gp(self):
        """S3 wins on revenue (volume recovered); S1 wins on GP per retained volume.

        This captures the real trade-off: S1 has high margin on the volume it keeps,
        but loses enterprise GMV. S3 sacrifices rate to retain volume.
        """
        s1 = run_scenario(S1_HOLD)
        s3 = run_scenario(S3_TIERED)
        # S3 has more revenue (volume recovery > rate cut)
        assert s3.total_revenue > s1.total_revenue
        # S1 has more gross profit per EUR of GMV (higher blended rate)
        assert s1.blended_take_rate_bp > s3.blended_take_rate_bp


class TestCompareScenarios:
    def test_returns_all_four(self):
        results = compare_scenarios(DEFAULT_SCENARIOS)
        assert len(results) == 4

    def test_sorted_by_revenue_descending(self):
        results = compare_scenarios(DEFAULT_SCENARIOS)
        revenues = [r.total_revenue for r in results]
        assert revenues == sorted(revenues, reverse=True)

    def test_s4_highest_revenue(self):
        results = compare_scenarios(DEFAULT_SCENARIOS)
        assert results[0].scenario_name == S4_TIERED_GROWTH.name

    def test_s2_lowest_revenue_due_to_low_rate(self):
        results = compare_scenarios(DEFAULT_SCENARIOS)
        # S2 at 10bp has low revenue despite full volume
        s2_result = next(r for r in results if "S2" in r.scenario_name)
        s3_result = next(r for r in results if "S3" in r.scenario_name)
        assert s2_result.total_revenue < s3_result.total_revenue


class TestScenarioGrossMargin:
    def test_s1_higher_nominal_margin_than_s3(self):
        """S1 has higher margin on retained volume (18bp vs tiered), but less volume."""
        s1 = run_scenario(S1_HOLD)
        s3 = run_scenario(S3_TIERED)
        # S1 blended rate is 18bp (all retained at 18), S3 blended is ~14-15bp
        assert s1.blended_take_rate_bp > s3.blended_take_rate_bp

    def test_s4_revenue_exceeds_s3(self):
        s3 = run_scenario(S3_TIERED)
        s4 = run_scenario(S4_TIERED_GROWTH)
        assert s4.total_revenue > s3.total_revenue


class TestScenarioResult:
    def test_total_gmv_property(self):
        result = run_scenario(S3_TIERED)
        expected = result.enterprise_gmv + result.mid_gmv + result.smb_gmv
        assert result.total_gmv == expected

    def test_total_revenue_property(self):
        result = run_scenario(S3_TIERED)
        expected = result.enterprise_revenue + result.mid_revenue + result.smb_revenue
        assert result.total_revenue == expected

    def test_blended_take_rate_bp(self):
        result = run_scenario(S3_TIERED)
        # Blended rate = total_revenue / total_gmv * 10000
        expected = result.total_revenue / result.total_gmv * 10_000
        assert result.blended_take_rate_bp == pytest.approx(expected, rel=1e-9)


class TestScenarioFlags:
    def test_s3_recommended(self):
        assert S3_TIERED.recommended is True

    def test_s4_includes_growth_assumption(self):
        assert S4_TIERED_GROWTH.includes_growth_assumption is True

    def test_s1_not_recommended(self):
        assert S1_HOLD.recommended is False

    def test_s2_no_growth_assumption(self):
        assert S2_FLAT_10BP.includes_growth_assumption is False

    def test_recommended_scenario_is_s3(self):
        assert RECOMMENDED_SCENARIO is S3_TIERED


class TestBreakevenAttrition:
    def test_returns_expected_keys(self):
        result = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
        assert set(result.keys()) == {
            "breakeven_churn_pct", "breakeven_gmv_eur", "merchants_equiv",
            "test_gp", "vs_gp", "gp_cushion",
        }

    def test_s3_vs_s2_churn_approx_75pct(self):
        # S3 has ~75% churn tolerance before GP falls to S2 level
        result = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
        assert result["breakeven_churn_pct"] == pytest.approx(75.0, abs=2.0)

    def test_gp_cushion_positive(self):
        result = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
        assert result["gp_cushion"] > 0

    def test_test_gp_greater_pagina_vs_gp(self):
        result = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
        assert result["test_gp"] > result["vs_gp"]

    def test_merchants_equiv_is_int(self):
        result = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
        assert isinstance(result["merchants_equiv"], int)

    def test_merchants_equiv_positive(self):
        result = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
        assert result["merchants_equiv"] > 0

    def test_breakeven_gmv_consistent_with_churn_pct(self):
        result = calc_breakeven_attrition(S3_TIERED, S2_FLAT_10BP)
        expected_churn = (result["breakeven_gmv_eur"] / PORTFOLIO_ENTERPRISE_GMV) * 100
        assert result["breakeven_churn_pct"] == pytest.approx(expected_churn, rel=1e-9)


class TestMonthlyPL:
    def test_returns_12_rows(self):
        rows = calc_monthly_pl(S3_TIERED)
        assert len(rows) == 12

    def test_each_row_has_required_keys(self):
        rows = calc_monthly_pl(S3_TIERED)
        for row in rows:
            assert set(row.keys()) == {"month", "gmv", "revenue", "gross_profit", "gross_margin_pct"}

    def test_month_numbers_1_to_12(self):
        rows = calc_monthly_pl(S3_TIERED)
        assert [r["month"] for r in rows] == list(range(1, 13))

    def test_annual_gmv_sums_match_scenario(self):
        rows = calc_monthly_pl(S3_TIERED)
        annual = run_scenario(S3_TIERED)
        total_gmv = sum(r["gmv"] for r in rows)
        assert total_gmv == pytest.approx(annual.total_gmv, rel=1e-9)

    def test_annual_revenue_sums_match_scenario(self):
        rows = calc_monthly_pl(S3_TIERED)
        annual = run_scenario(S3_TIERED)
        total_rev = sum(r["revenue"] for r in rows)
        assert total_rev == pytest.approx(annual.total_revenue, rel=1e-9)

    def test_annual_gp_sums_match_scenario(self):
        rows = calc_monthly_pl(S3_TIERED)
        annual = run_scenario(S3_TIERED)
        total_gp = sum(r["gross_profit"] for r in rows)
        assert total_gp == pytest.approx(annual.total_gross_profit, rel=1e-9)

    def test_seasonality_sums_to_one(self):
        assert sum(MONTHLY_SEASONALITY) == pytest.approx(1.0, rel=1e-9)

    def test_q4_higher_than_q1(self):
        rows = calc_monthly_pl(S3_TIERED)
        q1_gmv = sum(rows[i]["gmv"] for i in range(3))   # Jan–Mar
        q4_gmv = sum(rows[i]["gmv"] for i in range(9, 12))  # Oct–Dec
        assert q4_gmv > q1_gmv

    def test_gross_margin_pct_consistent(self):
        rows = calc_monthly_pl(S3_TIERED)
        for row in rows:
            if row["revenue"] > 0:
                expected_gm = row["gross_profit"] / row["revenue"]
                assert row["gross_margin_pct"] == pytest.approx(expected_gm, rel=1e-9)
