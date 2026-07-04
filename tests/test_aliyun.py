"""Tests for Alibaba Cloud optimization modules."""

from cloudcost.aliyun.ecs_optimizer import ECSOptimizer, ECS_HOURLY_CNY, UPGRADE_MAP
from cloudcost.aliyun.oss_analyzer import OSSAnalyzer, OSS_COSTS_CNY


def test_ecs_upgrade_map():
    """Verify ECS upgrade map."""
    assert len(UPGRADE_MAP) > 0
    for old, new in UPGRADE_MAP.items():
        assert old.startswith("ecs.")
        assert new.startswith("ecs.")


def test_ecs_pricing():
    """Verify ECS pricing data."""
    assert len(ECS_HOURLY_CNY) > 10
    assert all(v > 0 for v in ECS_HOURLY_CNY.values())


def test_oss_costs():
    """Verify OSS storage class costs."""
    assert "Standard" in OSS_COSTS_CNY
    assert "Archive" in OSS_COSTS_CNY
    assert OSS_COSTS_CNY["Archive"] < OSS_COSTS_CNY["Standard"]
