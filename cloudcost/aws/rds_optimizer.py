"""
AWS RDS Optimizer — find over-provisioned databases and savings opportunities.
"""

from __future__ import annotations

import datetime
from typing import Any

import boto3


# Approx RDS instance hourly costs (us-east-1, standard, single-AZ)
RDS_HOURLY = {
    "db.t3.micro": 0.017, "db.t3.small": 0.034, "db.t3.medium": 0.068,
    "db.t3.large": 0.136, "db.t3.xlarge": 0.272, "db.t3.2xlarge": 0.544,
    "db.m6i.large": 0.182, "db.m6i.xlarge": 0.364, "db.m6i.2xlarge": 0.728,
    "db.r6i.large": 0.253, "db.r6i.xlarge": 0.506, "db.r6i.2xlarge": 1.012,
    "db.m5.large": 0.171, "db.m5.xlarge": 0.342, "db.m5.2xlarge": 0.684,
    "db.r5.large": 0.237, "db.r5.xlarge": 0.474, "db.r5.2xlarge": 0.948,
}

# Multi-AZ multiplier
MULTI_AZ_MULTIPLIER = 2.0


class RDSOptimizer:
    """Analyze RDS instances for cost-saving opportunities."""


    def __init__(
        self,
        session: boto3.Session | None = None,
        profile: str | None = None,
        regions: list[str] | None = None,
    ):
        if session:
            self._session = session
        else:
            kwargs = {"profile_name": profile} if profile else {}
            self._session = boto3.Session(**kwargs)

        if not regions:
            self.regions = ["us-east-1", "us-east-2", "us-west-2"]
        else:
            self.regions = regions

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
        findings = []
        rds = self._session.client("rds", region_name=region)
        cw = self._session.client("cloudwatch", region_name=region)

        try:
            dbs = rds.describe_db_instances()
        except Exception:
            return []

        for db in dbs.get("DBInstances", []):
            db_id = db["DBInstanceIdentifier"]
            db_class = db.get("DBInstanceClass", "unknown")
            engine = db.get("Engine", "unknown")
            multi_az = db.get("MultiAZ", False)
            storage_gb = db.get("AllocatedStorage", 20)

            hourly_base = RDS_HOURLY.get(db_class, 0.20)
            if multi_az:
                hourly_base *= MULTI_AZ_MULTIPLIER
            monthly_cost = hourly_base * 730

            findings_to_add = []

            # Check if RDS is stopped (already saving)
            if db.get("DBInstanceStatus") == "stopped":
                findings_to_add.append({
                    "service": "rds",
                    "region": region,
                    "resource_id": db_id,
                    "finding": "stopped_instance",
                    "severity": "low",
                    "detail": f"RDS {db_id} is stopped — will auto-start after 7 days",
                    "action": "Snapshot and delete if no longer needed",
                    "estimated_monthly_savings_usd": 0,
                })
                continue

            # Check storage over-provisioning
            if storage_gb >= 1000:
                findings_to_add.append({
                    "service": "rds",
                    "region": region,
                    "resource_id": db_id,
                    "finding": "large_storage",
                    "severity": "low",
                    "detail": f"RDS {db_id} has {storage_gb}GB allocated — review actual usage",
                    "action": "Check actual usage via CloudWatch; reduce allocation",
                    "estimated_monthly_savings_usd": round(storage_gb * 0.03, 2),
                })

            # Multi-AZ for non-prod
            if multi_az and engine not in ("aurora-mysql", "aurora-postgresql"):
                findings_to_add.append({
                    "service": "rds",
                    "region": region,
                    "resource_id": db_id,
                    "finding": "multiaz_review",
                    "severity": "medium",
                    "detail": f"RDS {db_id} has Multi-AZ enabled — verify need for non-prod",
                    "action": "Consider Single-AZ for dev/test (~50% savings)",
                    "estimated_monthly_savings_usd": round(monthly_cost * 0.5, 2),
                })

            # Check for RI coverage (heuristic)
            if db_class != "unknown" and monthly_cost > 100:
                findings_to_add.append({
                    "service": "rds",
                    "region": region,
                    "resource_id": db_id,
                    "finding": "ri_candidate",
                    "severity": "medium",
                    "detail": f"RDS {db_id} ({db_class}) costs ~${monthly_cost:.0f}/month — consider Reserved Instance",
                    "action": "Purchase RI for ~30-50% savings",
                    "estimated_monthly_savings_usd": round(monthly_cost * 0.35, 2),
                })

            findings.extend(findings_to_add)

        return findings
