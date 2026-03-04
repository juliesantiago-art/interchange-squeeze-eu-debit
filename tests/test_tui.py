"""Smoke tests for TUI table builders."""

import pytest
from rich.table import Table
from interchange_squeeze.tui import (
    build_value_table,
    build_scenario_table,
    build_sensitivity_table,
)
from interchange_squeeze.scenarios import DEFAULT_SCENARIOS, S3_TIERED


class TestBuildValueTable:
    def test_returns_rich_table(self):
        table = build_value_table()
        assert isinstance(table, Table)

    def test_default_inputs(self):
        table = build_value_table(
            monthly_gmv=40_000_000,
            yuno_rate=92.3,
            competitor_rate=88.6,
        )
        assert isinstance(table, Table)
        assert table.row_count > 0

    def test_custom_inputs(self):
        table = build_value_table(
            monthly_gmv=10_000_000,
            yuno_rate=91.0,
            competitor_rate=87.5,
            yuno_bp=15.0,
            competitor_bp=10.0,
        )
        assert isinstance(table, Table)

    def test_has_expected_columns(self):
        table = build_value_table()
        col_names = [col.header for col in table.columns]
        assert "Metric" in col_names
        assert "Value" in col_names

    def test_zero_gmv_does_not_crash(self):
        table = build_value_table(monthly_gmv=0)
        assert isinstance(table, Table)

    def test_equal_approval_rates(self):
        table = build_value_table(yuno_rate=90.0, competitor_rate=90.0)
        assert isinstance(table, Table)


class TestBuildScenarioTable:
    def test_returns_rich_table(self):
        table = build_scenario_table()
        assert isinstance(table, Table)

    def test_has_rows(self):
        table = build_scenario_table()
        assert table.row_count > 0

    def test_custom_scenarios(self):
        table = build_scenario_table(scenarios=DEFAULT_SCENARIOS)
        assert isinstance(table, Table)
        # One metric column + four scenario columns
        assert len(table.columns) == 5

    def test_single_scenario(self):
        table = build_scenario_table(scenarios=[S3_TIERED])
        assert isinstance(table, Table)
        assert len(table.columns) == 2

    def test_custom_gmv(self):
        table = build_scenario_table(enterprise_gmv=1_000_000_000)
        assert isinstance(table, Table)


class TestBuildSensitivityTable:
    def test_returns_rich_table(self):
        table = build_sensitivity_table()
        assert isinstance(table, Table)

    def test_has_rows(self):
        table = build_sensitivity_table()
        assert table.row_count > 0

    def test_has_expected_columns(self):
        table = build_sensitivity_table()
        col_names = [col.header for col in table.columns]
        assert "Blended Rate Scenario" in col_names
        assert "GMV Growth Needed" in col_names

    def test_custom_base_revenue(self):
        table = build_sensitivity_table(base_revenue=5_000_000)
        assert isinstance(table, Table)
