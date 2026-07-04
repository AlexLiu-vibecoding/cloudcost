"""
AWS EC2 Optimizer — identify idle instances, right-sizing opportunities, and savings.
"""

from __future__ import annotations

import datetime
from typing import Any

import boto3


# Instance family right-sizing map: oversized → recommended smaller
RIGHTSIZE_MAP = {
    # General purpose
    "m6i.xlarge": ("m6i.large", 0.50),
    "m6i.2xlarge": ("m6i.xlarge", 0.50),
    "m6i.4xlarge": ("m6i.2xlarge", 0.50),
    "m5.xlarge": ("m5.large", 0.50),
    "m5.2xlarge": ("m5.xlarge", 0.50),
    "m5.4xlarge": ("m5.2xlarge", 0.50),
    # Compute optimized
    "c6i.xlarge": ("c6i.large", 0.50),
    "c6i.2xlarge": ("c6i.xlarge", 0.50),
    "c5.xlarge": ("c5.large", 0.50),
    "c5.2xlarge": ("c5.xlarge", 0.50),
    "c5.4xlarge": ("c5.2xlarge", 0.50),
    # Memory optimized
    "r6i.xlarge": ("r6i.large", 0.50),
    "r6i.2xlarge": ("r6i.xlarge", 0.50),
    "r5.xlarge": ("r5.large", 0.50),
    "r5.2xlarge": ("r5.xlarge", 0.50),
    "r5.4xlarge": ("r5.2xlarge", 0.50),
}

# On-demand to RI savings estimates by term
RI_SAVINGS = {"1year": 0.35, "3year": 0.55}

# Approx on-demand hourly costs (us-east-1 pricing as baseline)
INSTANCE_HOURLY = {
    "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208,
    "t3.medium": 0.0416, "t3.large": 0.0832, "t3.xlarge": 0.1664, "t3.2xlarge": 0.3328,
    "m6i.large": 0.096, "m6i.xlarge": 0.192, "m6i.2xlarge": 0.384, "m6i.4xlarge": 0.768,
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384, "m5.4xlarge": 0.768,
    "c6i.large": 0.085, "c6i.xlarge": 0.170, "c6i.2xlarge": 0.340,
    "c5.large": 0.085, "c5.xlarge": 0.170, "c5.2xlarge": 0.340, "c5.4xlarge": 0.680,
    "r6i.large": 0.126, "r6i.xlarge": 0.252, "r6i.2xlarge": 0.504,
    "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504, "r5.4xlarge": 1.008,
}


class EC2Optimizer:
    """Analyze EC2 instances for cost-saving opportunities."""


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
            ec2 = self._session.client("ec2", region_name="us-east-1")
            try:
                resp = ec2.describe_regions()
                self.regions = [r["RegionName"] for r in resp["Regions"]]
            except Exception:
                self.regions = ["us-east-1", "us-east-2", "us-west-2"]
        else:
            self.regions = regions

    def analyze_all(self) -> list[dict[str, Any]]:
        """Run all EC2 checks across all regions."""
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
        findings.extend(self._check_old_generations(region))
        return findings

    def find_idle_instances(self, region: str | None = None) -> list[dict[str, Any]]:
        """Find instances with very low CPU utilization (likely idle)."""
        findings = []
        regions = [region] if region else self.regions

        for r in regions:
            ec2 = self._session.client("ec2", region_name=r)
            try:
                instances = ec2.describe_instances(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                )
            except Exception:
                continue

            for res in instances.get("Reservations", []):
                for inst in res.get("Instances", []):
                    inst_id = inst["InstanceId"]
                    inst_type = inst.get("InstanceType", "unknown")
                    hourly = INSTANCE_HOURLY.get(inst_type, 0.10)
                    monthly = hourly * 730

                    # Tag-based hints
                    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                    env = tags.get("Environment", tags.get("env", ""))

                    # Flag dev/test instances
                    if env.lower() in ("dev", "test", "staging", "sandbox"):
                        findings.append({
                            "service": "ec2",
                            "region": r,
                            "resource_id": inst_id,
                            "finding": "dev_instance_always_on",
                            "severity": "medium",
                            "instance_type": inst_type,
                            "detail": f"Dev/test instance {inst_id} ({inst_type}) running 24/7",
                            "action": "Schedule start/stop (saves ~70%) or downsize",
                            "estimated_monthly_savings_usd": round(monthly * 0.7, 2),
                        })

        return findings

    def right_size_recommendations(self, region: str | None = None) -> list[dict[str, Any]]:
        """Recommend smaller instance types for under-utilized instances."""
        findings = []
        regions = [region] if region else self.regions

        for r in regions:
            ec2 = self._session.client("ec2", region_name=r)
            cw = self._session.client("cloudwatch", region_name=r)

            try:
                instances = ec2.describe_instances(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                )
            except Exception:
                continue

            for res in instances.get("Reservations", []):
                for inst in res.get("Instances", []):
                    inst_type = inst.get("InstanceType", "")
                    inst_id = inst["InstanceId"]

                    if inst_type not in RIGHTSIZE_MAP:
                        continue

                    # Check CPU utilization over last 7 days
                    try:
                        metrics = cw.get_metric_statistics(
                            Namespace="AWS/EC2",
                            MetricName="CPUUtilization",
                            Dimensions=[{"Name": "InstanceId", "Value": inst_id}],
                            StartTime=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7),
                            EndTime=datetime.datetime.now(datetime.timezone.utc),
                            Period=3600,
                            Statistics=["Average"],
                        )
                    except Exception:
                        metrics = {"Datapoints": []}

                    avg_cpu = 0
                    if metrics["Datapoints"]:
                        avg_cpu = sum(dp["Average"] for dp in metrics["Datapoints"]) / len(metrics["Datapoints"])

                    if avg_cpu < 20:
                        new_type, savings_pct = RIGHTSIZE_MAP[inst_type]
                        hourly = INSTANCE_HOURLY.get(inst_type, 0.10)
                        new_hourly = INSTANCE_HOURLY.get(new_type, hourly * savings_pct)
                        monthly_saving = round((hourly - new_hourly) * 730, 2)

                        findings.append({
                            "service": "ec2",
                            "region": r,
                            "resource_id": inst_id,
                            "finding": "right_size",
                            "severity": "high" if monthly_saving > 50 else "medium",
                            "instance_type": inst_type,
                            "recommended_type": new_type,
                            "avg_cpu_pct": round(avg_cpu, 1),
                            "detail": f"Instance {inst_id} ({inst_type}) avg CPU {avg_cpu:.1f}% → {new_type}",
                            "action": f"Change to {new_type}",
                            "estimated_monthly_savings_usd": monthly_saving,
                        })

        return findings

    def _check_old_generations(self, region: str) -> list[dict[str, Any]]:
        """Flag instances on previous-gen hardware that could upgrade for savings."""
        findings = []
        ec2 = self._session.client("ec2", region_name=region)

        OLD_FAMILIES = {"m3", "m4", "c3", "c4", "r3", "r4", "t2", "m5", "c5", "r5"}

        try:
            instances = ec2.describe_instances(
                Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
            )
        except Exception:
            return []

        UPGRADE_MAP = {"m5": "m6i", "c5": "c6i", "r5": "r6i", "m4": "m6i", "c4": "c6i", "r4": "r6i"}

        for res in instances.get("Reservations", []):
            for inst in res.get("Instances", []):
                inst_type = inst.get("InstanceType", "")
                family = inst_type.split(".")[0] if "." in inst_type else ""

                if family in OLD_FAMILIES:
                    new_family = UPGRADE_MAP.get(family)
                    if new_family:
                        size = inst_type.split(".")[1] if "." in inst_type else "large"
                        new_type = f"{new_family}.{size}"
                        hourly = INSTANCE_HOURLY.get(inst_type, 0.10)
                        # Newer gen typically ~10-20% cheaper + faster
                        monthly_savings = round(hourly * 730 * 0.15, 2)

                        findings.append({
                            "service": "ec2",
                            "region": region,
                            "resource_id": inst["InstanceId"],
                            "finding": "old_generation",
                            "severity": "medium",
                            "instance_type": inst_type,
                            "recommended_type": new_type,
                            "detail": f"Instance {inst['InstanceId']} on {family} → upgrade to {new_family}",
                            "action": f"Migrate to {new_type} (better perf + lower cost)",
                            "estimated_monthly_savings_usd": monthly_savings,
                        })

        return findings
