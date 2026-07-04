"""Tests for Terraform cost estimation."""

from pathlib import Path
from cloudcost.core.terraform import TerraformEstimator


FIXTURES = Path(__file__).parent / "fixtures"


def test_estimate_plan():
    estimator = TerraformEstimator()
    plan_path = FIXTURES / "sample_plan.json"

    resources = estimator.estimate_plan(plan_path)
    assert len(resources) > 0

    for r in resources:
        assert "resource_type" in r
        assert "resource_name" in r
        assert "estimated_monthly_cost_usd" in r
        assert r["estimated_monthly_cost_usd"] >= 0


def test_summarize():
    estimator = TerraformEstimator()
    plan_path = FIXTURES / "sample_plan.json"
    resources = estimator.estimate_plan(plan_path)

    summary = estimator.summarize(resources)
    assert "total_monthly_usd" in summary
    assert "total_annual_usd" in summary
    assert "by_type" in summary

    # Total should be positive (multiple resources)
    assert summary["total_monthly_usd"] > 0
    # Annual = monthly * 12
    assert summary["total_annual_usd"] == round(summary["total_monthly_usd"] * 12, 2)


def test_terraform_cli():
    """Test the terraform CLI command works."""
    import subprocess
    import sys

    plan_path = FIXTURES / "sample_plan.json"
    result = subprocess.run(
        [sys.executable, "-m", "cloudcost.cli", "terraform", str(plan_path), "-o", "summary"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert "Total monthly" in result.stdout
    assert "Total annual" in result.stdout
