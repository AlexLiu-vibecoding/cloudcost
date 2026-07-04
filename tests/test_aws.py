"""Tests for AWS cost optimization modules."""

import pytest
from cloudcost.aws.ec2_optimizer import EC2Optimizer
from cloudcost.aws.rds_optimizer import RDSOptimizer
from cloudcost.aws.s3_analyzer import S3Analyzer
from cloudcost.aws.ri_planner import RIPlanner


def test_ec2_right_size_map():
    """Verify right-size map is consistent."""
    from cloudcost.aws.ec2_optimizer import RIGHTSIZE_MAP, INSTANCE_HOURLY
    for instance, (smaller, pct) in RIGHTSIZE_MAP.items():
        assert instance in INSTANCE_HOURLY, f"{instance} missing from pricing"
        assert smaller in INSTANCE_HOURLY, f"{smaller} missing from pricing"
        assert 0 < pct < 1, f"Invalid savings ratio for {instance}"


def test_rds_instance_costs():
    """Verify RDS pricing data."""
    from cloudcost.aws.rds_optimizer import RDS_HOURLY
    assert len(RDS_HOURLY) > 5
    assert all(v > 0 for v in RDS_HOURLY.values())


def test_s3_storage_costs():
    """Verify S3 storage class pricing."""
    from cloudcost.aws.s3_analyzer import STORAGE_COSTS
    assert "STANDARD" in STORAGE_COSTS
    assert "GLACIER" in STORAGE_COSTS
    assert STORAGE_COSTS["GLACIER"] < STORAGE_COSTS["STANDARD"]


def test_ri_break_even():
    """Verify break-even calculations."""
    from cloudcost.aws.ri_planner import _break_even
    assert _break_even("1year", "partial-upfront") == 3
    assert _break_even("3year", "all-upfront") == 9
    assert _break_even("1year", "no-upfront") == 1


def test_version():
    """Verify package version."""
    from cloudcost import __version__
    assert __version__ == "0.1.0"
