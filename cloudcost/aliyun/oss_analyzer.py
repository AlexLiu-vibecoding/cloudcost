"""
Alibaba Cloud OSS Analyzer — storage optimization and lifecycle recommendations.
"""

from __future__ import annotations

from typing import Any


# OSS storage class costs (CNY per GB-month, cn-hangzhou)
OSS_COSTS_CNY = {
    "Standard": 0.12,
    "IA": 0.08,
    "Archive": 0.03,
    "ColdArchive": 0.015,
    "DeepColdArchive": 0.007,
}

CNY_TO_USD = 0.14


class OSSAnalyzer:
    """Analyze OSS buckets for storage cost optimization."""


    def __init__(self, regions: list[str] | None = None):
        self.regions = regions or ["cn-hangzhou", "cn-shanghai"]

    def analyze(self) -> list[dict[str, Any]]:
        findings = []
        for region in self.regions:
            findings.extend(self.scan_region(region))
        return sorted(
            findings,
            key=lambda x: x.get("estimated_monthly_savings_usd", 0),
            reverse=True,
        )

    def scan_region(self, region: str) -> list[dict[str, Any]]:
        """Scan OSS buckets in a region."""
        findings = []

        # General OSS recommendations (applicable without API access)
        # Estimate: 1TB of Standard storage → potential savings
        est_tb = 1
        standard_cost = est_tb * 1024 * OSS_COSTS_CNY["Standard"]  # CNY/month
        ia_cost = est_tb * 1024 * OSS_COSTS_CNY["IA"]
        savings_cny = standard_cost - ia_cost

        findings.append({
            "service": "oss",
            "region": region,
            "finding": "lifecycle_recommendation",
            "severity": "medium",
            "detail": (
                f"Per TB of Standard storage: ¥{standard_cost:.0f}/month. "
                f"Moving infrequent data to IA saves ~{savings_cny:.0f} CNY/TB/month"
            ),
            "action": (
                "Set OSS lifecycle rules:\n"
                "  - Transition to IA after 30 days (saves 33%)\n"
                "  - Transition to Archive after 90 days (saves 75%)\n"
                "  - Transition to Cold Archive after 180 days (saves 94%)"
            ),
            "estimated_monthly_savings_usd": round(savings_cny * CNY_TO_USD, 2),
        })

        # Check for versioning costs
        findings.append({
            "service": "oss",
            "region": region,
            "finding": "versioning_cleanup",
            "severity": "low",
            "detail": "OSS versioning accumulates old versions — set lifecycle rules to expire noncurrent versions",
            "action": "Configure lifecycle to delete noncurrent versions after 30 days",
            "estimated_monthly_savings_usd": 15.00,
        })

        # Incomplete multipart uploads
        findings.append({
            "service": "oss",
            "region": region,
            "finding": "multipart_cleanup",
            "severity": "low",
            "detail": "Incomplete multipart uploads accumulate storage costs",
            "action": "Set lifecycle rule to abort incomplete multipart uploads after 7 days",
            "estimated_monthly_savings_usd": 5.00,
        })

        return findings
