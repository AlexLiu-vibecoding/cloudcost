"""
Alibaba Cloud ECS Optimizer.

Idle instance detection, right-sizing, and upgrade recommendations for ECS.
"""

from __future__ import annotations

from typing import Any


# ECS instance type right-sizing map (older gen → newer gen)
UPGRADE_MAP = {
    "ecs.g6.xlarge": "ecs.g7.xlarge",
    "ecs.g6.2xlarge": "ecs.g7.2xlarge",
    "ecs.g6.4xlarge": "ecs.g7.4xlarge",
    "ecs.c6.xlarge": "ecs.c7.xlarge",
    "ecs.c6.2xlarge": "ecs.c7.2xlarge",
    "ecs.r6.xlarge": "ecs.r7.xlarge",
    "ecs.r6.2xlarge": "ecs.r7.2xlarge",
    "ecs.g5.xlarge": "ecs.g7.xlarge",
    "ecs.c5.xlarge": "ecs.c7.xlarge",
    "ecs.r5.xlarge": "ecs.r7.xlarge",
}

# ECS downsize map: oversized → recommended
DOWNSIZE_MAP = {
    "ecs.g7.2xlarge": ("ecs.g7.xlarge", 0.50),
    "ecs.g7.4xlarge": ("ecs.g7.2xlarge", 0.50),
    "ecs.g7.8xlarge": ("ecs.g7.4xlarge", 0.50),
    "ecs.c7.2xlarge": ("ecs.c7.xlarge", 0.50),
    "ecs.c7.4xlarge": ("ecs.c7.2xlarge", 0.50),
    "ecs.r7.2xlarge": ("ecs.r7.xlarge", 0.50),
    "ecs.r7.4xlarge": ("ecs.r7.2xlarge", 0.50),
}

# Approximate ECS hourly costs (CNY, cn-hangzhou, pay-as-you-go)
ECS_HOURLY_CNY = {
    "ecs.g7.large": 0.48, "ecs.g7.xlarge": 0.96, "ecs.g7.2xlarge": 1.92,
    "ecs.g7.4xlarge": 3.84, "ecs.g7.8xlarge": 7.68,
    "ecs.c7.large": 0.42, "ecs.c7.xlarge": 0.85, "ecs.c7.2xlarge": 1.70,
    "ecs.r7.large": 0.63, "ecs.r7.xlarge": 1.26, "ecs.r7.2xlarge": 2.52,
    "ecs.g6.large": 0.52, "ecs.g6.xlarge": 1.04, "ecs.g6.2xlarge": 2.08,
    "ecs.c6.large": 0.46, "ecs.c6.xlarge": 0.92, "ecs.c6.2xlarge": 1.84,
    "ecs.r6.large": 0.68, "ecs.r6.xlarge": 1.36, "ecs.r6.2xlarge": 2.72,
    "ecs.g5.large": 0.58, "ecs.g5.xlarge": 1.16, "ecs.g5.2xlarge": 2.32,
}

# CNY to USD approximate
CNY_TO_USD = 0.14


class ECSOptimizer:
    """Analyze ECS instances for cost-saving opportunities."""


    def __init__(self, regions: list[str] | None = None):
        self.regions = regions or ["cn-hangzhou", "cn-shanghai", "cn-beijing"]

    def analyze_all(self) -> list[dict[str, Any]]:
        findings = []
        for region in self.regions:
            findings.extend(self.scan_region(region))
        return sorted(
            findings,
            key=lambda x: x.get("estimated_monthly_savings_usd", 0),
            reverse=True,
        )

    def scan_region(self, region: str) -> list[dict[str, Any]]:
        """Single-region scan for the scanner orchestrator."""
        findings = []
        findings.extend(self.find_idle_instances(region))
        findings.extend(self.right_size_recommendations(region))
        findings.extend(self._upgrade_recommendations(region))
        return findings

    def find_idle_instances(self, region: str | None = None) -> list[dict[str, Any]]:
        """Find potentially idle ECS instances (heuristic-based without API)."""
        findings = []
        regions = [region] if region else self.regions

        for r in regions:
            # Placeholder: in production, this queries ECS API + CloudMonitor
            findings.append({
                "service": "ecs",
                "region": r,
                "resource_id": "placeholder (API access required)",
                "finding": "api_credentials_needed",
                "severity": "info",
                "detail": "ECS idle detection requires Alibaba Cloud API credentials",
                "action": "export ALIBABA_CLOUD_ACCESS_KEY_ID=... to enable automated scanning",
                "estimated_monthly_savings_usd": 0,
            })

        return findings

    def right_size_recommendations(self, region: str | None = None) -> list[dict[str, Any]]:
        """Recommend downsizing for under-utilized instances."""
        findings = []
        regions = [region] if region else self.regions

        for r in regions:
            findings.append({
                "service": "ecs",
                "region": r,
                "resource_id": "placeholder (API access required)",
                "finding": "right_size_hint",
                "severity": "info",
                "detail": (
                    "ECS right-sizing: check CloudMonitor CPU metrics. "
                    "Instances with <20% avg CPU are candidates for downsizing (save ~50%)"
                ),
                "action": (
                    "1) Check CloudMonitor for low-CPU instances\n"
                    "2) Use renewal downgrade or migration to smaller type\n"
                    "3) Estimated savings: 30-50% per downsized instance"
                ),
                "estimated_monthly_savings_usd": 0,
            })

        return findings

    def _upgrade_recommendations(self, region: str) -> list[dict[str, Any]]:
        """Recommend upgrading to newer-gen instances (g6→g7, etc.)."""
        findings = []
        for old, new in UPGRADE_MAP.items():
            old_cost = ECS_HOURLY_CNY.get(old, 1.0)
            new_cost = ECS_HOURLY_CNY.get(new, old_cost * 0.9)
            monthly_saving_cny = (old_cost - new_cost) * 730
            monthly_saving_usd = round(monthly_saving_cny * CNY_TO_USD, 2)

            findings.append({
                "service": "ecs",
                "region": region,
                "resource_id": f"type:{old}",
                "finding": "generation_upgrade",
                "severity": "medium",
                "detail": f"Upgrade ECS {old} → {new}: better perf + lower cost",
                "action": f"Migrate from {old} to {new} (save ~${monthly_saving_usd}/month per instance)",
                "estimated_monthly_savings_usd": monthly_saving_usd,
            })

        return findings
