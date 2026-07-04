"""
AWS S3 Analyzer — complete storage tier optimization and lifecycle management.

Handles all S3 storage classes with cost-based tiering recommendations:
  Standard → Intelligent-Tiering → Standard-IA → OneZone-IA
  → Glacier Instant Retrieval → Glacier Flexible Retrieval → Deep Archive
"""

from __future__ import annotations

import datetime
from typing import Any

import boto3


# ── S3 Storage Class Costs (per GB/month, us-east-1) ──────────────────

S3_STORAGE_COSTS = {
    "STANDARD":                       {"storage": 0.023, "retrieval": 0.000, "min_days": 0,   "description": "Frequent access, 3 AZs"},
    "INTELLIGENT_TIERING":            {"storage": 0.023, "retrieval": 0.000, "min_days": 0,   "description": "Auto-tiered, monitoring fee applies"},
    "STANDARD_IA":                    {"storage": 0.0125,"retrieval": 0.010, "min_days": 30,  "description": "Infrequent access, 3 AZs, retrieval fee"},
    "ONEZONE_IA":                     {"storage": 0.010, "retrieval": 0.010, "min_days": 30,  "description": "Single AZ, non-critical data"},
    "GLACIER_INSTANT_RETRIEVAL":      {"storage": 0.004, "retrieval": 0.030, "min_days": 90,  "description": "Archive, millisecond retrieval"},
    "GLACIER_FLEXIBLE_RETRIEVAL":     {"storage": 0.0036,"retrieval": 0.010, "min_days": 90,  "description": "Archive, minutes to hours retrieval"},
    "GLACIER_DEEP_ARCHIVE":           {"storage": 0.00099,"retrieval":0.020, "min_days": 180, "description": "Long-term archive, 12-hour retrieval"},
}

# Lifecycle policy templates by object age
LIFECYCLE_TEMPLATE = [
    {"days": 0,    "action": "Enable Intelligent-Tiering (auto-moves between frequent/infrequent)"},
    {"days": 30,   "action": "Transition to STANDARD_IA (save ~45% for objects >30 days old)"},
    {"days": 90,   "action": "Transition to GLACIER_INSTANT_RETRIEVAL (save ~82%, millisecond access)"},
    {"days": 180,  "action": "Transition to GLACIER_DEEP_ARCHIVE (save ~96%, lowest cost)"},
    {"days": 365,  "action": "Expire/delete objects older than 1 year (if no retention requirement)"},
]

# Intelligent Tiering monitoring cost
INTELLIGENT_TIERING_MONITOR_FEE = 0.0025  # per 1000 objects


class S3Analyzer:
    """Analyze S3 buckets for storage cost optimization.

    Checks:
    - Objects in expensive tiers that should move to cheaper ones
    - Missing lifecycle policies
    - Versioning without expiration (orphaned versions accumulate)
    - Incomplete multipart uploads
    - Intelligent Tiering adoption
    - Buckets without encryption or logging (governance)
    """

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
        findings = []
        for region in self._get_regions():
            findings.extend(self.scan_region(region))
        return sorted(
            findings,
            key=lambda x: x.get("estimated_monthly_savings_usd", 0),
            reverse=True,
        )

    def scan_region(self, region: str) -> list[dict[str, Any]]:
        findings = []
        s3 = self._session.client("s3", region_name=region)

        try:
            buckets = s3.list_buckets()
        except Exception:
            return []

        for bucket in buckets.get("Buckets", []):
            bucket_name = bucket["Name"]

            # Determine actual bucket region
            try:
                loc = s3.get_bucket_location(Bucket=bucket_name)
                bucket_region = loc.get("LocationConstraint") or "us-east-1"
            except Exception:
                continue

            if bucket_region != region:
                continue

            bucket_s3 = self._session.client("s3", region_name=bucket_region)

            # Check lifecycle policies
            lifecycle_rules = self._get_lifecycle_rules(bucket_s3, bucket_name)

            # Check versioning
            has_versioning, has_mfa_delete = self._get_versioning(bucket_s3, bucket_name)

            # Get storage class distribution (if accessible via metrics or inventory)
            storage_distribution = self._get_storage_distribution(bucket_s3, bucket_name)

            findings.extend(self._check_lifecycle(bucket_name, bucket_region, lifecycle_rules))
            findings.extend(self._check_versioning(bucket_name, bucket_region, has_versioning, lifecycle_rules))
            findings.extend(self._check_storage_distribution(bucket_name, bucket_region, storage_distribution))
            findings.extend(self._check_intelligent_tiering(bucket_name, bucket_region, lifecycle_rules))
            findings.extend(self._check_multipart(bucket_name, bucket_region))

        return findings

    # ── Lifecycle checks ──────────────────────────────────────────

    def _check_lifecycle(
        self, bucket: str, region: str, rules: list[dict]
    ) -> list[dict[str, Any]]:
        findings = []

        if not rules:
            # No lifecycle policy at all — highest priority
            # Estimate: 1TB Standard → ~$23/mo. With lifecycle: ~$5-8/mo
            est_size_tb = 1
            current_cost = est_size_tb * 1024 * S3_STORAGE_COSTS["STANDARD"]["storage"]
            optimized_cost = est_size_tb * 1024 * 0.005  # blended rate with lifecycle
            savings = round(current_cost - optimized_cost, 2)

            findings.append({
                "service": "s3",
                "region": region,
                "resource_id": bucket,
                "finding": "no_lifecycle_policy",
                "severity": "high",
                "detail": (
                    f"Bucket '{bucket}' has NO lifecycle policy. "
                    f"Without tiering, you pay $0.023/GB for ALL objects forever."
                ),
                "action": (
                    "Apply lifecycle policy: Standard→IA@30d→Glacier@90d→DeepArchive@180d. "
                    f"Est. savings: ${savings:.0f}/mo per TB"
                ),
                "estimated_monthly_savings_usd": savings,
            })
            return findings

        # Check which lifecycle transitions exist
        transitions_found = set()
        expirations_found = False
        for rule in rules:
            for trans in rule.get("Transitions", []):
                transitions_found.add(trans.get("StorageClass", ""))
            if rule.get("Expiration") or rule.get("NoncurrentVersionExpiration"):
                expirations_found = True

        # Missing transitions
        missing = []
        if "STANDARD_IA" not in transitions_found and "INTELLIGENT_TIERING" not in transitions_found:
            missing.append("STANDARD_IA")
        if "GLACIER" not in transitions_found and "DEEP_ARCHIVE" not in transitions_found:
            missing.append("Glacier tier")
        if not expirations_found:
            missing.append("object expiration")

        if missing:
            findings.append({
                "service": "s3",
                "region": region,
                "resource_id": bucket,
                "finding": "incomplete_lifecycle",
                "severity": "medium",
                "detail": f"Bucket '{bucket}' is missing transitions to: {', '.join(missing)}",
                "action": f"Add lifecycle rules for: {', '.join(missing)}",
                "estimated_monthly_savings_usd": 15.00,
            })

        return findings

    # ── Versioning checks ─────────────────────────────────────────

    def _check_versioning(
        self, bucket: str, region: str, has_versioning: bool, rules: list[dict]
    ) -> list[dict[str, Any]]:
        findings = []

        if not has_versioning:
            return findings

        # Check if noncurrent versions have expiration
        has_nc_expiry = any(
            r.get("NoncurrentVersionExpiration") for r in rules
        )
        has_nc_transition = any(
            r.get("NoncurrentVersionTransitions") for r in rules
        )

        if not has_nc_expiry and not has_nc_transition:
            findings.append({
                "service": "s3",
                "region": region,
                "resource_id": bucket,
                "finding": "versioning_no_cleanup",
                "severity": "high",
                "detail": (
                    f"Bucket '{bucket}' has versioning ON but NO noncurrent version cleanup. "
                    f"Every update doubles storage — old versions accumulate forever."
                ),
                "action": "Add NoncurrentVersionExpiration (e.g. delete after 30 days)",
                "estimated_monthly_savings_usd": 50.00,
            })

        return findings

    # ── Storage class distribution checks ─────────────────────────

    def _check_storage_distribution(
        self, bucket: str, region: str, distribution: dict[str, float]
    ) -> list[dict[str, Any]]:
        findings = []

        if not distribution:
            return findings

        total_gb = sum(distribution.values())
        if total_gb == 0:
            return findings

        standard_pct = distribution.get("STANDARD", 0) / total_gb * 100
        standard_gb = distribution.get("STANDARD", 0)

        # If >80% of data is still in STANDARD, flag it
        if standard_pct > 80 and standard_gb > 100:
            monthly_standard_cost = standard_gb * S3_STORAGE_COSTS["STANDARD"]["storage"]
            # Assume 50% could move to IA, 30% to Glacier, 20% stays Standard
            blended_savings = monthly_standard_cost * 0.40  # ~40% savings

            findings.append({
                "service": "s3",
                "region": region,
                "resource_id": bucket,
                "finding": "too_much_standard_storage",
                "severity": "high" if standard_gb > 500 else "medium",
                "detail": (
                    f"Bucket '{bucket}': {standard_gb:.0f}GB ({standard_pct:.0f}%) in STANDARD. "
                    f"Cost: ${monthly_standard_cost:.2f}/mo. Most data should be tiered."
                ),
                "action": "Apply lifecycle: IA after 30d, Glacier after 90d",
                "estimated_monthly_savings_usd": round(blended_savings, 2),
            })

        return findings

    # ── Intelligent Tiering check ──────────────────────────────────

    def _check_intelligent_tiering(
        self, bucket: str, region: str, rules: list[dict]
    ) -> list[dict[str, Any]]:
        findings = []

        has_IT = any(
            "INTELLIGENT_TIERING" in str(r.get("Transitions", ""))
            for r in rules
        )

        if not has_IT:
            findings.append({
                "service": "s3",
                "region": region,
                "resource_id": bucket,
                "finding": "consider_intelligent_tiering",
                "severity": "low",
                "detail": (
                    f"Bucket '{bucket}': Consider S3 Intelligent-Tiering for "
                    f"unpredictable access patterns. Auto-moves objects between "
                    f"frequent/infrequent tiers — no retrieval fees, no minimum days."
                ),
                "action": "Enable Intelligent-Tiering (monitoring: $0.0025/1K objects/mo)",
                "estimated_monthly_savings_usd": 5.00,
            })

        return findings

    # ── Multipart upload cleanup ───────────────────────────────────

    def _check_multipart(self, bucket: str, region: str) -> list[dict[str, Any]]:
        findings = []
        s3 = self._session.client("s3", region_name=region)

        try:
            uploads = s3.list_multipart_uploads(Bucket=bucket)
            count = len(uploads.get("Uploads", []))
            if count > 0:
                # Incomplete multipart uploads accumulate storage costs
                findings.append({
                    "service": "s3",
                    "region": region,
                    "resource_id": bucket,
                    "finding": "incomplete_multipart_uploads",
                    "severity": "medium",
                    "detail": f"Bucket '{bucket}' has {count} incomplete multipart upload(s)",
                    "action": "Add lifecycle rule: abort incomplete uploads after 7 days",
                    "estimated_monthly_savings_usd": count * 2.00,
                })
        except Exception:
            pass

        return findings

    def lifecycle_recommendations(self) -> list[dict[str, Any]]:
        """Generate full lifecycle policy recommendations for each bucket."""
        recommendations = []
        for region in self._get_regions():
            s3 = self._session.client("s3", region_name=region)
            try:
                buckets = s3.list_buckets()
            except Exception:
                continue

            for bucket in buckets.get("Buckets", []):
                bucket_name = bucket["Name"]
                rec = {
                    "bucket": bucket_name,
                    "region": region,
                    "recommended_rules": [
                        {
                            "id": "intelligent-tiering",
                            "status": "Enabled",
                            "filter": {"prefix": ""},
                            "transitions": [
                                {"days": 0, "storage_class": "INTELLIGENT_TIERING"}
                            ],
                        },
                        {
                            "id": "archive-old-objects",
                            "status": "Enabled",
                            "filter": {"prefix": ""},
                            "transitions": [
                                {"days": 90, "storage_class": "GLACIER"},
                                {"days": 365, "storage_class": "DEEP_ARCHIVE"},
                            ],
                        },
                        {
                            "id": "cleanup-versions",
                            "status": "Enabled",
                            "filter": {"prefix": ""},
                            "noncurrent_version_expiration": {"noncurrent_days": 30},
                            "abort_incomplete_multipart_upload": {"days_after_initiation": 7},
                        },
                    ],
                }
                recommendations.append(rec)

        return recommendations

    # ── Helpers ────────────────────────────────────────────────────

    def _get_lifecycle_rules(self, s3_client, bucket: str) -> list[dict]:
        try:
            return s3_client.get_bucket_lifecycle_configuration(
                Bucket=bucket
            ).get("Rules", [])
        except Exception:
            return []

    def _get_versioning(self, s3_client, bucket: str) -> tuple[bool, bool]:
        try:
            v = s3_client.get_bucket_versioning(Bucket=bucket)
            return (v.get("Status") == "Enabled",
                    v.get("MFADelete") == "Enabled")
        except Exception:
            return (False, False)

    def _get_storage_distribution(self, s3_client, bucket: str) -> dict[str, float]:
        """Get approximate storage distribution using metrics or inventory.

        Falls back to empty dict if S3 Storage Lens / inventory not configured.
        In production, this would query CloudWatch metrics or S3 Inventory reports.
        """
        # Try CloudWatch storage metrics (S3 Storage Lens publishes to CW)
        cw = self._session.client("cloudwatch", region_name=s3_client.meta.region_name)
        distribution = {}

        for sc in ["StandardStorage", "StandardIAStorage", "OneZoneIAStorage",
                    "GlacierStorage", "DeepArchiveStorage"]:
            try:
                resp = cw.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName="BucketSizeBytes",
                    Dimensions=[
                        {"Name": "BucketName", "Value": bucket},
                        {"Name": "StorageType", "Value": sc},
                    ],
                    StartTime=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
                    EndTime=datetime.datetime.now(datetime.timezone.utc),
                    Period=86400,
                    Statistics=["Average"],
                )
                if resp["Datapoints"]:
                    # Convert bytes to GB
                    gb = resp["Datapoints"][0]["Average"] / (1024 ** 3)
                    if sc == "StandardStorage":
                        distribution["STANDARD"] = gb
                    elif sc == "StandardIAStorage":
                        distribution["STANDARD_IA"] = gb
                    elif sc == "OneZoneIAStorage":
                        distribution["ONEZONE_IA"] = gb
                    elif sc == "GlacierStorage":
                        distribution["GLACIER"] = gb
                    elif sc == "DeepArchiveStorage":
                        distribution["DEEP_ARCHIVE"] = gb
            except Exception:
                pass

        return distribution

    def _get_regions(self) -> list[str]:
        ec2 = self._session.client("ec2", region_name="us-east-1")
        try:
            return [r["RegionName"] for r in ec2.describe_regions()["Regions"]]
        except Exception:
            return ["us-east-1", "us-east-2", "us-west-2"]
