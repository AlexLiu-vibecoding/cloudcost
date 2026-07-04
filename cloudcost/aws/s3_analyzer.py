"""
AWS S3 Analyzer — storage optimization and lifecycle policy recommendations.
"""

from __future__ import annotations

import datetime
from typing import Any

import boto3


# Storage class cost per GB-month (approx us-east-1)
STORAGE_COSTS = {
    "STANDARD": 0.023,
    "STANDARD_IA": 0.0125,
    "INTELLIGENT_TIERING": 0.023,  # base, auto-moves
    "ONEZONE_IA": 0.01,
    "GLACIER": 0.004,
    "GLACIER_IR": 0.01,
    "DEEP_ARCHIVE": 0.00099,
    "GLACIER_DEEP_ARCHIVE": 0.00099,
}


class S3Analyzer:
    """Analyze S3 buckets for storage cost optimization."""


    def __init__(
        self,
        session: boto3.Session | None = None,
        profile: str | None = None,
    ):
        if session:
            self._session = session
        else:
            kwargs = {"profile_name": profile} if profile else {}
            self._session = boto3.Session(**kwargs)

    def analyze(self) -> list[dict[str, Any]]:
        """Analyze all buckets for savings opportunities."""
        findings = []
        for region in self._get_regions():
            findings.extend(self.scan_region(region))
        return sorted(
            findings,
            key=lambda x: x.get("estimated_monthly_savings_usd", 0),
            reverse=True,
        )

    def scan_region(self, region: str) -> list[dict[str, Any]]:
        """Scan S3 buckets in a single region."""
        findings = []
        s3 = self._session.client("s3", region_name=region)

        try:
            buckets = s3.list_buckets()
        except Exception:
            return []

        for bucket in buckets.get("Buckets", []):
            bucket_name = bucket["Name"]
            creation_date = bucket.get("CreationDate")

            try:
                # Check bucket region (may differ from client region)
                bucket_region = s3.get_bucket_location(Bucket=bucket_name)["LocationConstraint"]
                if not bucket_region or bucket_region == "null":
                    bucket_region = "us-east-1"
            except Exception:
                bucket_region = region
                continue

            if bucket_region != region:
                continue

            # Check for lifecycle policies
            try:
                lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                has_lifecycle = len(lifecycle.get("Rules", [])) > 0
            except Exception:
                has_lifecycle = False

            # Check versioning
            try:
                versioning = s3.get_bucket_versioning(Bucket=bucket_name)
                has_versioning = versioning.get("Status") == "Enabled"
            except Exception:
                has_versioning = False

            # Buckets without lifecycle → recommend Intelligent Tiering
            if not has_lifecycle:
                # Estimate: assume 500GB of data
                est_storage_gb = 500
                potential_savings = est_storage_gb * (STORAGE_COSTS["STANDARD"] - STORAGE_COSTS["INTELLIGENT_TIERING"] * 0.7)

                findings.append({
                    "service": "s3",
                    "region": bucket_region,
                    "resource_id": bucket_name,
                    "finding": "no_lifecycle_policy",
                    "severity": "medium",
                    "detail": f"Bucket '{bucket_name}' has no lifecycle policy",
                    "action": "Set up Intelligent Tiering or lifecycle rules to auto-archive old objects",
                    "estimated_monthly_savings_usd": round(potential_savings, 2),
                })

            # Versioning without expiration can accumulate costs
            if has_versioning and not has_lifecycle:
                findings.append({
                    "service": "s3",
                    "region": bucket_region,
                    "resource_id": bucket_name,
                    "finding": "versioning_no_expiry",
                    "severity": "low",
                    "detail": f"Bucket '{bucket_name}' has versioning enabled without lifecycle expiry",
                    "action": "Add noncurrent version expiration to lifecycle rules",
                    "estimated_monthly_savings_usd": 20.00,
                })

        return findings

    def lifecycle_recommendations(self) -> list[dict[str, Any]]:
        """Generate specific lifecycle policy recommendations."""
        recommendations = []
        for region in self._get_regions():
            s3 = self._session.client("s3", region_name=region)
            try:
                buckets = s3.list_buckets()
            except Exception:
                continue

            for bucket in buckets.get("Buckets", []):
                bucket_name = bucket["Name"]
                try:
                    lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                    rules = lifecycle.get("Rules", [])
                except Exception:
                    rules = []

                # Recommend standard lifecycle template
                recs = {
                    "bucket": bucket_name,
                    "region": region,
                    "current_rules": len(rules),
                    "recommendations": [
                        {
                            "rule": "Transition to STANDARD_IA after 30 days",
                            "estimated_savings_pct": "~45% for aged objects",
                        },
                        {
                            "rule": "Transition to GLACIER after 90 days",
                            "estimated_savings_pct": "~80% for archival objects",
                        },
                        {
                            "rule": "Expire noncurrent versions after 60 days",
                            "estimated_savings_pct": "Variable",
                        },
                        {
                            "rule": "Delete incomplete multipart uploads after 7 days",
                            "estimated_savings_pct": "Cleanup dangling uploads",
                        },
                    ],
                }
                recommendations.append(recs)

        return recommendations

    def _get_regions(self) -> list[str]:
        ec2 = self._session.client("ec2", region_name="us-east-1")
        try:
            return [r["RegionName"] for r in ec2.describe_regions()["Regions"]]
        except Exception:
            return ["us-east-1", "us-east-2", "us-west-2"]
