"""Tests for AWS cost optimization modules."""

import pytest
from cloudcost.aws.ec2_optimizer import (
    EC2Optimizer, INSTANCE_HOURLY, RIGHTSIZE_MAP, GRAVITON_MIGRATION,
)
from cloudcost.aws.rds_optimizer import (
    RDSOptimizer, RDS_HOURLY, RDS_GRAVITON_MAP, ENGINE_DETAILS,
)
from cloudcost.aws.s3_analyzer import S3Analyzer, S3_STORAGE_COSTS, LIFECYCLE_TEMPLATE
from cloudcost.aws.elasticache_optimizer import (
    ElastiCacheOptimizer, CACHE_HOURLY, CACHE_GRAVITON_MAP, NODE_MEMORY_GB,
)
from cloudcost.aws.ri_planner import RIPlanner


# ── EC2 Tests ──────────────────────────────────────────────────────

def test_ec2_right_size_map():
    for instance, (smaller, pct) in RIGHTSIZE_MAP.items():
        assert instance in INSTANCE_HOURLY, f"{instance} missing from pricing"
        assert smaller in INSTANCE_HOURLY, f"{smaller} missing from pricing"
        assert 0 < pct < 1


def test_graviton_migration_map():
    assert len(GRAVITON_MIGRATION) > 10
    for x86, (graviton, pct) in GRAVITON_MIGRATION.items():
        assert x86 in INSTANCE_HOURLY, f"{x86} missing from pricing"
        assert graviton in INSTANCE_HOURLY, f"{graviton} missing from pricing"
        assert 0 < pct < 50
        assert INSTANCE_HOURLY[graviton] < INSTANCE_HOURLY[x86]


def test_graviton_covers_all_families():
    families = set(k.split(".")[0] for k in GRAVITON_MIGRATION)
    for prefix in ["m", "c", "r", "t"]:
        assert any(f.startswith(prefix) for f in families)


def test_ec2_pricing_complete():
    all_refs = set()
    all_refs.update(RIGHTSIZE_MAP.keys())
    all_refs.update(v[0] for v in RIGHTSIZE_MAP.values())
    all_refs.update(GRAVITON_MIGRATION.keys())
    all_refs.update(v[0] for v in GRAVITON_MIGRATION.values())
    for ref in all_refs:
        assert ref in INSTANCE_HOURLY, f"{ref} missing from EC2 pricing"


# ── RDS Tests ──────────────────────────────────────────────────────

def test_rds_pricing():
    assert len(RDS_HOURLY) > 15, "Should cover multiple families"
    assert all(v > 0 for v in RDS_HOURLY.values())


def test_rds_graviton_map():
    assert len(RDS_GRAVITON_MAP) > 10
    for x86, (graviton, pct) in RDS_GRAVITON_MAP.items():
        assert x86 in RDS_HOURLY, f"{x86} missing from RDS pricing"
        assert graviton in RDS_HOURLY, f"{graviton} missing from RDS pricing"
        assert 0 < pct < 50
        assert RDS_HOURLY[graviton] < RDS_HOURLY[x86], \
            f"Graviton {graviton} must be cheaper than {x86}"


def test_rds_graviton_families():
    """Covers db.m, db.r, db.t families."""
    families = set(".".join(k.split(".")[:2]) for k in RDS_GRAVITON_MAP)
    for prefix in ["db.m", "db.r", "db.t"]:
        assert any(f.startswith(prefix) for f in families), \
            f"Missing {prefix}* RDS family in Graviton map"


def test_engine_details():
    assert "mysql" in ENGINE_DETAILS
    assert "postgres" in ENGINE_DETAILS
    assert ENGINE_DETAILS["mysql"]["aurora_compatible"] is True
    assert ENGINE_DETAILS["mysql"]["aurora_engine"] == "aurora-mysql"


# ── ElastiCache Tests ──────────────────────────────────────────────

def test_cache_pricing():
    assert len(CACHE_HOURLY) > 10
    assert all(v > 0 for v in CACHE_HOURLY.values())


def test_cache_graviton_map():
    assert len(CACHE_GRAVITON_MAP) > 5
    for x86, (graviton, pct) in CACHE_GRAVITON_MAP.items():
        assert x86 in CACHE_HOURLY, f"{x86} missing from ElastiCache pricing"
        assert graviton in CACHE_HOURLY, f"{graviton} missing from ElastiCache pricing"
        assert 0 < pct < 50
        assert CACHE_HOURLY[graviton] < CACHE_HOURLY[x86]


def test_cache_graviton_families():
    families = set(".".join(k.split(".")[:2]) for k in CACHE_GRAVITON_MAP)
    for prefix in ["cache.m", "cache.r", "cache.t"]:
        assert any(f.startswith(prefix) for f in families)


def test_node_memory():
    """Node memory map should match pricing keys for common types."""
    for ntype in ["cache.m7g.large", "cache.r7g.xlarge", "cache.t4g.medium"]:
        assert ntype in NODE_MEMORY_GB, f"{ntype} missing from memory map"
        assert NODE_MEMORY_GB[ntype] > 0


# ── S3 Tests ───────────────────────────────────────────────────────

def test_s3_storage_costs_complete():
    for class_name in ["STANDARD", "INTELLIGENT_TIERING", "STANDARD_IA",
                        "ONEZONE_IA", "GLACIER_INSTANT_RETRIEVAL",
                        "GLACIER_FLEXIBLE_RETRIEVAL", "GLACIER_DEEP_ARCHIVE"]:
        assert class_name in S3_STORAGE_COSTS
        assert "storage" in S3_STORAGE_COSTS[class_name]


def test_s3_cost_hierarchy():
    costs = {k: v["storage"] for k, v in S3_STORAGE_COSTS.items()}
    assert costs["STANDARD_IA"] < costs["STANDARD"]
    assert costs["GLACIER_DEEP_ARCHIVE"] < costs["GLACIER_FLEXIBLE_RETRIEVAL"]


def test_lifecycle_template():
    assert len(LIFECYCLE_TEMPLATE) >= 4
    days = [t["days"] for t in LIFECYCLE_TEMPLATE]
    assert days == sorted(days)


# ── RI Planner ─────────────────────────────────────────────────────

def test_ri_break_even():
    from cloudcost.aws.ri_planner import _break_even
    assert _break_even("1year", "partial-upfront") == 3
    assert _break_even("3year", "all-upfront") == 9


# ── Package ────────────────────────────────────────────────────────

def test_version():
    from cloudcost import __version__
    assert __version__ == "0.1.0"
