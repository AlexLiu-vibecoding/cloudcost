"""Tests for AWS cost optimization modules."""

import pytest
from cloudcost.aws.ec2_optimizer import (
    EC2Optimizer, INSTANCE_HOURLY, RIGHTSIZE_MAP, GRAVITON_MIGRATION,
)
from cloudcost.aws.rds_optimizer import RDSOptimizer, RDS_HOURLY
from cloudcost.aws.s3_analyzer import S3Analyzer, S3_STORAGE_COSTS, LIFECYCLE_TEMPLATE
from cloudcost.aws.ri_planner import RIPlanner


# ── EC2 Tests ──────────────────────────────────────────────────────

def test_ec2_right_size_map():
    for instance, (smaller, pct) in RIGHTSIZE_MAP.items():
        assert instance in INSTANCE_HOURLY, f"{instance} missing from pricing"
        assert smaller in INSTANCE_HOURLY, f"{smaller} missing from pricing"
        assert 0 < pct < 1, f"Invalid savings ratio for {instance}"


def test_graviton_migration_map():
    """Verify Graviton migration map has savings for each x86 type."""
    assert len(GRAVITON_MIGRATION) > 10, "Should cover major instance types"
    for x86, (graviton, pct) in GRAVITON_MIGRATION.items():
        assert x86 in INSTANCE_HOURLY, f"{x86} missing from pricing"
        assert graviton in INSTANCE_HOURLY, f"{graviton} missing from pricing"
        assert 0 < pct < 50, f"Savings {pct}% for {x86}→{graviton} outside expected range"
        # Graviton should be cheaper
        assert INSTANCE_HOURLY[graviton] < INSTANCE_HOURLY[x86], \
            f"Graviton {graviton} should be cheaper than x86 {x86}"


def test_graviton_covers_all_families():
    """Graviton migration should cover m, c, r, t families."""
    families = set(k.split(".")[0] for k in GRAVITON_MIGRATION)
    for prefix in ["m", "c", "r", "t"]:
        assert any(f.startswith(prefix) for f in families), \
            f"Missing {prefix}* family in Graviton migration map"


def test_ec2_pricing_complete():
    """Verify all referenced types have pricing."""
    all_refs = set()
    all_refs.update(RIGHTSIZE_MAP.keys())
    all_refs.update(v[0] for v in RIGHTSIZE_MAP.values())
    all_refs.update(GRAVITON_MIGRATION.keys())
    all_refs.update(v[0] for v in GRAVITON_MIGRATION.values())
    for ref in all_refs:
        assert ref in INSTANCE_HOURLY, f"{ref} referenced in maps but missing from pricing"


# ── RDS Tests ──────────────────────────────────────────────────────

def test_rds_instance_costs():
    assert len(RDS_HOURLY) > 5
    assert all(v > 0 for v in RDS_HOURLY.values())


# ── S3 Tests ───────────────────────────────────────────────────────

def test_s3_storage_costs_complete():
    """Verify all major S3 storage classes are present."""
    for class_name in ["STANDARD", "INTELLIGENT_TIERING", "STANDARD_IA",
                        "ONEZONE_IA", "GLACIER_INSTANT_RETRIEVAL",
                        "GLACIER_FLEXIBLE_RETRIEVAL", "GLACIER_DEEP_ARCHIVE"]:
        assert class_name in S3_STORAGE_COSTS, f"Missing S3 class: {class_name}"
        assert "storage" in S3_STORAGE_COSTS[class_name]
        assert "retrieval" in S3_STORAGE_COSTS[class_name]
        assert "min_days" in S3_STORAGE_COSTS[class_name]


def test_s3_cost_hierarchy():
    """Deeper archive tiers should cost less per GB."""
    costs = {k: v["storage"] for k, v in S3_STORAGE_COSTS.items()}
    assert costs["STANDARD_IA"] < costs["STANDARD"]
    assert costs["GLACIER_INSTANT_RETRIEVAL"] < costs["STANDARD_IA"]
    assert costs["GLACIER_DEEP_ARCHIVE"] < costs["GLACIER_FLEXIBLE_RETRIEVAL"]


def test_lifecycle_template():
    """Lifecycle template should be properly ordered."""
    assert len(LIFECYCLE_TEMPLATE) >= 4
    days = [t["days"] for t in LIFECYCLE_TEMPLATE]
    assert days == sorted(days), "Lifecycle days should be ascending"
    for t in LIFECYCLE_TEMPLATE:
        assert "days" in t
        assert "action" in t


# ── RI Planner Tests ───────────────────────────────────────────────

def test_ri_break_even():
    from cloudcost.aws.ri_planner import _break_even
    assert _break_even("1year", "partial-upfront") == 3
    assert _break_even("3year", "all-upfront") == 9
    assert _break_even("1year", "no-upfront") == 1


# ── Package Tests ──────────────────────────────────────────────────

def test_version():
    from cloudcost import __version__
    assert __version__ == "0.1.0"
