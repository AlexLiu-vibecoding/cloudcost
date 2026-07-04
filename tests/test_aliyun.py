"""Tests for Alibaba Cloud optimization modules."""

from cloudcost.aliyun.ecs_optimizer import ECSOptimizer, ECS_HOURLY_CNY, YITIAN_MIGRATION, UPGRADE_MAP
from cloudcost.aliyun.oss_analyzer import OSSAnalyzer, OSS_COSTS_CNY


def test_ecs_upgrade_map():
    """Verify ECS upgrade map."""
    assert len(UPGRADE_MAP) > 0
    for old, new in UPGRADE_MAP.items():
        assert old.startswith("ecs.")
        assert new.startswith("ecs.")


def test_ecs_pricing():
    """Verify ECS pricing data covers all families."""
    assert len(ECS_HOURLY_CNY) > 10
    assert all(v > 0 for v in ECS_HOURLY_CNY.values())


def test_yitian_migration_map():
    """Verify Yitian ARM migration map."""
    assert len(YITIAN_MIGRATION) > 10, "Should cover major ECS families"
    for x86, (yitian, pct) in YITIAN_MIGRATION.items():
        assert x86 in ECS_HOURLY_CNY, f"{x86} missing from ECS pricing"
        assert yitian in ECS_HOURLY_CNY, f"{yitian} missing from ECS pricing"
        assert 0 < pct < 50, f"Savings {pct}% out of range for {x86}→{yitian}"
        # Yitian must be cheaper
        assert ECS_HOURLY_CNY[yitian] < ECS_HOURLY_CNY[x86], \
            f"Yitian {yitian} must be cheaper than x86 {x86}"


def test_yitian_covers_all_families():
    """Yitian migration should cover g, c, r families."""
    families = set(".".join(k.split(".")[:2]) for k in YITIAN_MIGRATION)
    for prefix in ["ecs.g", "ecs.c", "ecs.r"]:
        assert any(f.startswith(prefix) for f in families), \
            f"Missing {prefix}* family in Yitian migration"


def test_yitian_recommendations_generate_savings():
    """Yitian recommendations should produce positive savings."""
    opt = ECSOptimizer(regions=["cn-hangzhou"])
    recs = opt.yitian_recommendations("cn-hangzhou")
    assert len(recs) > 0
    for r in recs:
        assert r["finding"] == "yitian_migration"
        assert r["chip_architecture"] == "x86 → ARM (Yitian 倚天710)"
        assert r["estimated_monthly_savings_usd"] > 0


def test_oss_costs():
    """Verify OSS storage class costs."""
    assert "Standard" in OSS_COSTS_CNY
    assert "Archive" in OSS_COSTS_CNY
    assert OSS_COSTS_CNY["Archive"] < OSS_COSTS_CNY["Standard"]
