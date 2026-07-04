"""
Alibaba Cloud ECS Optimizer.

Checks: Generation upgrades, x86 → Yitian ARM migration, right-sizing,
idle instances.
"""

from __future__ import annotations

from typing import Any


# ── ECS instance pricing (CNY/hour, cn-hangzhou, pay-as-you-go) ────

ECS_HOURLY_CNY = {
    # General purpose — x86 (Intel)
    "ecs.g7.large": 0.48, "ecs.g7.xlarge": 0.96, "ecs.g7.2xlarge": 1.92,
    "ecs.g7.4xlarge": 3.84, "ecs.g7.8xlarge": 7.68,
    "ecs.g6.large": 0.52, "ecs.g6.xlarge": 1.04, "ecs.g6.2xlarge": 2.08,
    "ecs.g6.4xlarge": 4.16,
    "ecs.g5.large": 0.58, "ecs.g5.xlarge": 1.16, "ecs.g5.2xlarge": 2.32,
    # General purpose — Yitian ARM (g8y)
    "ecs.g8y.large": 0.39, "ecs.g8y.xlarge": 0.78, "ecs.g8y.2xlarge": 1.56,
    "ecs.g8y.4xlarge": 3.12, "ecs.g8y.8xlarge": 6.24,
    # Compute optimized — x86 (Intel)
    "ecs.c7.large": 0.42, "ecs.c7.xlarge": 0.85, "ecs.c7.2xlarge": 1.70,
    "ecs.c7.4xlarge": 3.40,
    "ecs.c6.large": 0.46, "ecs.c6.xlarge": 0.92, "ecs.c6.2xlarge": 1.84,
    "ecs.c5.large": 0.52, "ecs.c5.xlarge": 1.04, "ecs.c5.2xlarge": 2.08,
    # Compute optimized — Yitian ARM (c8y)
    "ecs.c8y.large": 0.34, "ecs.c8y.xlarge": 0.69, "ecs.c8y.2xlarge": 1.38,
    "ecs.c8y.4xlarge": 2.76,
    # Memory optimized — x86 (Intel)
    "ecs.r7.large": 0.63, "ecs.r7.xlarge": 1.26, "ecs.r7.2xlarge": 2.52,
    "ecs.r7.4xlarge": 5.04,
    "ecs.r6.large": 0.68, "ecs.r6.xlarge": 1.36, "ecs.r6.2xlarge": 2.72,
    "ecs.r5.large": 0.74, "ecs.r5.xlarge": 1.48, "ecs.r5.2xlarge": 2.96,
    # Memory optimized — Yitian ARM (r8y)
    "ecs.r8y.large": 0.52, "ecs.r8y.xlarge": 1.04, "ecs.r8y.2xlarge": 2.08,
    "ecs.r8y.4xlarge": 4.16,
}

CNY_TO_USD = 0.14


# ── x86 → Yitian ARM (倚天) migration ─────────────────────────────

YITIAN_MIGRATION = {
    # General purpose: g7/g6/g5 → g8y
    "ecs.g7.large": ("ecs.g8y.large", 18.8),
    "ecs.g7.xlarge": ("ecs.g8y.xlarge", 18.8),
    "ecs.g7.2xlarge": ("ecs.g8y.2xlarge", 18.8),
    "ecs.g7.4xlarge": ("ecs.g8y.4xlarge", 18.8),
    "ecs.g6.large": ("ecs.g8y.large", 25.0),
    "ecs.g6.xlarge": ("ecs.g8y.xlarge", 25.0),
    "ecs.g6.2xlarge": ("ecs.g8y.2xlarge", 25.0),
    "ecs.g6.4xlarge": ("ecs.g8y.4xlarge", 25.0),
    "ecs.g5.large": ("ecs.g8y.large", 32.8),
    "ecs.g5.xlarge": ("ecs.g8y.xlarge", 32.8),
    "ecs.g5.2xlarge": ("ecs.g8y.2xlarge", 32.8),
    # Compute: c7/c6/c5 → c8y
    "ecs.c7.large": ("ecs.c8y.large", 19.0),
    "ecs.c7.xlarge": ("ecs.c8y.xlarge", 18.8),
    "ecs.c7.2xlarge": ("ecs.c8y.2xlarge", 18.8),
    "ecs.c6.large": ("ecs.c8y.large", 26.1),
    "ecs.c6.xlarge": ("ecs.c8y.xlarge", 25.0),
    "ecs.c6.2xlarge": ("ecs.c8y.2xlarge", 25.0),
    "ecs.c5.large": ("ecs.c8y.large", 34.6),
    "ecs.c5.xlarge": ("ecs.c8y.xlarge", 33.7),
    # Memory: r7/r6/r5 → r8y
    "ecs.r7.large": ("ecs.r8y.large", 17.5),
    "ecs.r7.xlarge": ("ecs.r8y.xlarge", 17.5),
    "ecs.r7.2xlarge": ("ecs.r8y.2xlarge", 17.5),
    "ecs.r6.large": ("ecs.r8y.large", 23.5),
    "ecs.r6.xlarge": ("ecs.r8y.xlarge", 23.5),
    "ecs.r6.2xlarge": ("ecs.r8y.2xlarge", 23.5),
    "ecs.r5.large": ("ecs.r8y.large", 29.7),
    "ecs.r5.xlarge": ("ecs.r8y.xlarge", 29.7),
}


# ── Generation upgrade map ─────────────────────────────────────────

UPGRADE_MAP = {
    "ecs.g6.xlarge": "ecs.g7.xlarge",
    "ecs.g6.2xlarge": "ecs.g7.2xlarge",
    "ecs.g6.4xlarge": "ecs.g7.4xlarge",
    "ecs.c6.xlarge": "ecs.c7.xlarge",
    "ecs.c6.2xlarge": "ecs.c7.2xlarge",
    "ecs.r6.xlarge": "ecs.r7.xlarge",
    "ecs.r6.2xlarge": "ecs.r7.2xlarge",
    "ecs.g5.xlarge": "ecs.g7.xlarge",
    "ecs.g5.2xlarge": "ecs.g7.2xlarge",
    "ecs.c5.xlarge": "ecs.c7.xlarge",
    "ecs.c5.2xlarge": "ecs.c7.2xlarge",
    "ecs.r5.xlarge": "ecs.r7.xlarge",
    "ecs.r5.2xlarge": "ecs.r7.2xlarge",
}


class ECSOptimizer:
    """Analyze ECS instances for cost-saving opportunities.

    Checks: Yitian ARM migration, generation upgrades, right-sizing, idle detection.
    """

    def __init__(self, regions: list[str] | None = None):
        self.regions = regions or ["cn-hangzhou", "cn-shanghai", "cn-beijing"]

    def analyze_all(self) -> list[dict[str, Any]]:
        findings = []
        for region in self.regions:
            findings.extend(self.scan_region(region))
        return sorted(findings, key=lambda x: x.get("estimated_monthly_savings_usd", 0), reverse=True)

    def scan_region(self, region: str) -> list[dict[str, Any]]:
        findings = []
        findings.extend(self.yitian_recommendations(region))
        findings.extend(self._upgrade_recommendations(region))
        findings.extend(self.find_idle_instances(region))
        findings.extend(self.right_size_recommendations(region))
        return findings

    # ── Yitian ARM (倚天) migration ──────────────────────────────────

    def yitian_recommendations(self, region: str | None = None) -> list[dict[str, Any]]:
        """Recommend migrating x86 instances to Yitian ARM for ~20% savings.

        Alibaba Yitian 710 (倚天710) is an ARM-based server chip:
        - Up to 20% lower cost vs comparable x86
        - Up to 40% better energy efficiency
        - Compatible with Linux workloads (not Windows)
        """
        findings = []
        regions = [region] if region else self.regions

        for r in regions:
            for x86_type, (yitian_type, savings_pct) in YITIAN_MIGRATION.items():
                x86_cost = ECS_HOURLY_CNY.get(x86_type, 1.0)
                yitian_cost = ECS_HOURLY_CNY.get(yitian_type, x86_cost * 0.8)
                monthly_saving_cny = round((x86_cost - yitian_cost) * 730, 2)
                monthly_saving_usd = round(monthly_saving_cny * CNY_TO_USD, 2)

                if monthly_saving_usd < 1:
                    continue

                findings.append({
                    "service": "ecs",
                    "region": r,
                    "resource_id": f"type:{x86_type}",
                    "finding": "yitian_migration",
                    "severity": "high" if monthly_saving_usd > 30 else "medium",
                    "instance_type": x86_type,
                    "recommended_type": yitian_type,
                    "chip_architecture": "x86 → ARM (Yitian 倚天710)",
                    "savings_pct": round(savings_pct, 1),
                    "detail": (
                        f"ECS {x86_type} (x86) → {yitian_type} (倚天 ARM) "
                        f"– save {savings_pct:.0f}% (￥{monthly_saving_cny:.0f}/mo, ${monthly_saving_usd:.2f}/mo)"
                    ),
                    "action": (
                        f"Migrate to {yitian_type}. Yitian 710 supports most Linux apps. "
                        f"Use ECS instance type change or re-deploy with ARM image."
                    ),
                    "estimated_monthly_savings_usd": monthly_saving_usd,
                })

        return findings

    # ── Generation upgrades ──────────────────────────────────────────

    def _upgrade_recommendations(self, region: str) -> list[dict[str, Any]]:
        findings = []
        for old, new in UPGRADE_MAP.items():
            old_cost = ECS_HOURLY_CNY.get(old, 1.0)
            new_cost = ECS_HOURLY_CNY.get(new, old_cost * 0.9)
            monthly_saving_cny = max(0, (old_cost - new_cost) * 730)
            monthly_saving_usd = round(monthly_saving_cny * CNY_TO_USD, 2)

            findings.append({
                "service": "ecs",
                "region": region,
                "resource_id": f"type:{old}",
                "finding": "generation_upgrade",
                "severity": "medium" if monthly_saving_usd > 10 else "low",
                "detail": (
                    f"Upgrade ECS {old} → {new}: newer gen, better perf/cost "
                    f"(save ￥{monthly_saving_cny:.0f}/mo per instance)"
                ),
                "action": f"Migrate from {old} to {new}",
                "estimated_monthly_savings_usd": monthly_saving_usd,
            })

        return findings

    # ── Idle / placeholder checks ────────────────────────────────────

    def find_idle_instances(self, region: str | None = None) -> list[dict[str, Any]]:
        regions = [region] if region else self.regions
        findings = []
        for r in regions:
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
        regions = [region] if region else self.regions
        findings = []
        for r in regions:
            findings.append({
                "service": "ecs",
                "region": r,
                "resource_id": "placeholder (API access required)",
                "finding": "right_size_hint",
                "severity": "info",
                "detail": (
                    "ECS right-sizing: check CloudMonitor CPU metrics. "
                    "Instances with <20% avg CPU can downsize (save ~50%)"
                ),
                "action": "1) Check CloudMonitor 2) Use renewal downgrade 3) Save 30-50% per instance",
                "estimated_monthly_savings_usd": 0,
            })
        return findings
