"""
AWS EC2 Optimizer — idle instance detection, right-sizing, Graviton migration,
and generation upgrade recommendations.
"""

from __future__ import annotations

import datetime
from typing import Any

import boto3


# ── Instance pricing (us-east-1, on-demand, hourly USD) ──────────────

INSTANCE_HOURLY = {
    # T-series (burstable)
    "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208,
    "t3.medium": 0.0416, "t3.large": 0.0832, "t3.xlarge": 0.1664, "t3.2xlarge": 0.3328,
    "t4g.nano": 0.0042, "t4g.micro": 0.0084, "t4g.small": 0.0168,
    "t4g.medium": 0.0336, "t4g.large": 0.0672, "t4g.xlarge": 0.1344, "t4g.2xlarge": 0.2688,
    # M-series (general purpose) — Intel/AMD
    "m6i.large": 0.096, "m6i.xlarge": 0.192, "m6i.2xlarge": 0.384, "m6i.4xlarge": 0.768,
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384, "m5.4xlarge": 0.768,
    "m5a.large": 0.086, "m5a.xlarge": 0.172, "m5a.2xlarge": 0.344,
    # M-series (Graviton ARM)
    "m7g.large": 0.081, "m7g.xlarge": 0.163, "m7g.2xlarge": 0.326, "m7g.4xlarge": 0.652,
    "m6g.large": 0.077, "m6g.xlarge": 0.154, "m6g.2xlarge": 0.308,
    # C-series (compute optimized) — Intel/AMD
    "c6i.large": 0.085, "c6i.xlarge": 0.170, "c6i.2xlarge": 0.340, "c6i.4xlarge": 0.680,
    "c5.large": 0.085, "c5.xlarge": 0.170, "c5.2xlarge": 0.340, "c5.4xlarge": 0.680,
    "c5a.large": 0.077, "c5a.xlarge": 0.154, "c5a.2xlarge": 0.308,
    # C-series (Graviton ARM)
    "c7g.large": 0.072, "c7g.xlarge": 0.145, "c7g.2xlarge": 0.290, "c7g.4xlarge": 0.580,
    "c6g.large": 0.068, "c6g.xlarge": 0.136, "c6g.2xlarge": 0.272,
    # R-series (memory optimized) — Intel/AMD
    "r6i.large": 0.126, "r6i.xlarge": 0.252, "r6i.2xlarge": 0.504, "r6i.4xlarge": 1.008,
    "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504, "r5.4xlarge": 1.008,
    "r5a.large": 0.113, "r5a.xlarge": 0.226, "r5a.2xlarge": 0.452,
    # R-series (Graviton ARM)
    "r7g.large": 0.107, "r7g.xlarge": 0.214, "r7g.2xlarge": 0.428, "r7g.4xlarge": 0.856,
    "r6g.large": 0.101, "r6g.xlarge": 0.202, "r6g.2xlarge": 0.404,
}


# ── x86 → Graviton (ARM) migration map ────────────────────────────────
# Key insight: Graviton instances are ~20% cheaper + ~20% better perf/watt

GRAVITON_MIGRATION = {
    # General purpose: m6i/m5 → m7g
    "m6i.large": ("m7g.large", 15.6),
    "m6i.xlarge": ("m7g.xlarge", 15.1),
    "m6i.2xlarge": ("m7g.2xlarge", 15.1),
    "m6i.4xlarge": ("m7g.4xlarge", 15.1),
    "m5.large": ("m7g.large", 15.6),
    "m5.xlarge": ("m7g.xlarge", 15.1),
    "m5.2xlarge": ("m7g.2xlarge", 15.1),
    "m5.4xlarge": ("m7g.4xlarge", 15.1),
    "m5a.large": ("m7g.large", 5.8),
    "m5a.xlarge": ("m7g.xlarge", 5.2),
    # Compute: c6i/c5 → c7g
    "c6i.large": ("c7g.large", 15.3),
    "c6i.xlarge": ("c7g.xlarge", 14.7),
    "c6i.2xlarge": ("c7g.2xlarge", 14.7),
    "c6i.4xlarge": ("c7g.4xlarge", 14.7),
    "c5.large": ("c7g.large", 15.3),
    "c5.xlarge": ("c7g.xlarge", 14.7),
    "c5.2xlarge": ("c7g.2xlarge", 14.7),
    "c5.4xlarge": ("c7g.4xlarge", 14.7),
    "c5a.large": ("c7g.large", 6.5),
    "c5a.xlarge": ("c7g.xlarge", 5.8),
    # Memory: r6i/r5 → r7g
    "r6i.large": ("r7g.large", 15.1),
    "r6i.xlarge": ("r7g.xlarge", 15.1),
    "r6i.2xlarge": ("r7g.2xlarge", 15.1),
    "r6i.4xlarge": ("r7g.4xlarge", 15.1),
    "r5.large": ("r7g.large", 15.1),
    "r5.xlarge": ("r7g.xlarge", 15.1),
    "r5.2xlarge": ("r7g.2xlarge", 15.1),
    "r5.4xlarge": ("r7g.4xlarge", 15.1),
    "r5a.large": ("r7g.large", 5.3),
    "r5a.xlarge": ("r7g.xlarge", 5.3),
    # Burstable: t3 → t4g
    "t3.nano": ("t4g.nano", 19.2),
    "t3.micro": ("t4g.micro", 19.2),
    "t3.small": ("t4g.small", 19.2),
    "t3.medium": ("t4g.medium", 19.2),
    "t3.large": ("t4g.large", 19.2),
    "t3.xlarge": ("t4g.xlarge", 19.2),
    "t3.2xlarge": ("t4g.2xlarge", 19.2),
}


# ── Right-sizing map: oversized → smaller ─────────────────────────────

RIGHTSIZE_MAP = {
    "m6i.xlarge": ("m6i.large", 0.50),
    "m6i.2xlarge": ("m6i.xlarge", 0.50),
    "m6i.4xlarge": ("m6i.2xlarge", 0.50),
    "m5.xlarge": ("m5.large", 0.50),
    "m5.2xlarge": ("m5.xlarge", 0.50),
    "m5.4xlarge": ("m5.2xlarge", 0.50),
    "c6i.xlarge": ("c6i.large", 0.50),
    "c6i.2xlarge": ("c6i.xlarge", 0.50),
    "c5.xlarge": ("c5.large", 0.50),
    "c5.2xlarge": ("c5.xlarge", 0.50),
    "c5.4xlarge": ("c5.2xlarge", 0.50),
    "r6i.xlarge": ("r6i.large", 0.50),
    "r6i.2xlarge": ("r6i.xlarge", 0.50),
    "r5.xlarge": ("r5.large", 0.50),
    "r5.2xlarge": ("r5.xlarge", 0.50),
    "r5.4xlarge": ("r5.2xlarge", 0.50),
    "m7g.xlarge": ("m7g.large", 0.50),
    "m7g.2xlarge": ("m7g.xlarge", 0.50),
    "c7g.xlarge": ("c7g.large", 0.50),
    "c7g.2xlarge": ("c7g.xlarge", 0.50),
    "r7g.xlarge": ("r7g.large", 0.50),
    "r7g.2xlarge": ("r7g.xlarge", 0.50),
}


# ── Old generation → latest generation upgrade ───────────────────────

OLD_GEN_UPGRADE = {
    # x86 path
    "m3": "m6i", "m4": "m6i", "m5": "m6i", "m5a": "m6i",
    "c3": "c6i", "c4": "c6i", "c5": "c6i", "c5a": "c6i",
    "r3": "r6i", "r4": "r6i", "r5": "r6i", "r5a": "r6i",
    "t2": "t3",
    # Graviton path (prefer Graviton for even bigger savings)
    "m6g": "m7g", "c6g": "c7g", "r6g": "r7g",
}


class EC2Optimizer:
    """Analyze EC2 instances for cost-saving opportunities.

    Checks: idle instances, right-sizing, Graviton ARM migration,
    old-generation upgrades.
    """

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
        findings.extend(self.find_idle_instances(region))
        findings.extend(self.right_size_recommendations(region))
        findings.extend(self.graviton_recommendations(region))
        findings.extend(self._check_old_generations(region))
        return findings

    # ── Idle instance detection ────────────────────────────────────

    def find_idle_instances(self, region: str | None = None) -> list[dict[str, Any]]:
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

                    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                    env = tags.get("Environment", tags.get("env", ""))

                    if env.lower() in ("dev", "test", "staging", "sandbox"):
                        findings.append({
                            "service": "ec2",
                            "region": r,
                            "resource_id": inst_id,
                            "finding": "dev_instance_always_on",
                            "severity": "medium",
                            "instance_type": inst_type,
                            "detail": f"Dev/test {inst_id} ({inst_type}) running 24/7",
                            "action": "Schedule start/stop (saves ~70%)",
                            "estimated_monthly_savings_usd": round(monthly * 0.7, 2),
                        })

            # Stopped instances that still have EBS attached
            try:
                stopped = ec2.describe_instances(
                    Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
                )
                for res in stopped.get("Reservations", []):
                    for inst in res.get("Instances", []):
                        vols = inst.get("BlockDeviceMappings", [])
                        if vols:
                            ebs_cost = sum(
                                _ebs_cost(v.get("Ebs", {}).get("VolumeId", ""), ec2)
                                for v in vols
                            )
                            if ebs_cost > 10:
                                findings.append({
                                    "service": "ec2",
                                    "region": r,
                                    "resource_id": inst["InstanceId"],
                                    "finding": "stopped_instance_ebs_cost",
                                    "severity": "low",
                                    "detail": f"Stopped {inst['InstanceId']} has ~${ebs_cost:.0f}/mo in EBS",
                                    "action": "Snapshot and delete volumes, or terminate instance",
                                    "estimated_monthly_savings_usd": round(ebs_cost, 2),
                                })
            except Exception:
                pass

        return findings

    # ── Right-sizing ────────────────────────────────────────────────

    def right_size_recommendations(self, region: str | None = None) -> list[dict[str, Any]]:
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
                            "detail": f"{inst_id} ({inst_type}) avg CPU {avg_cpu:.1f}% → {new_type}",
                            "action": f"Change to {new_type}",
                            "estimated_monthly_savings_usd": monthly_saving,
                        })

        return findings

    # ── Graviton (ARM) migration recommendations ────────────────────

    def graviton_recommendations(self, region: str | None = None) -> list[dict[str, Any]]:
        """Recommend migrating x86 instances to Graviton (ARM) for ~20% savings.

        Graviton (AWS-designed ARM chips) offer:
        - Up to 20% lower cost vs comparable x86
        - Up to 40% better price/performance
        - Compatible with most Linux workloads
        - NOT compatible with Windows (must stay on x86)
        """
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
                    inst_type = inst.get("InstanceType", "")
                    inst_id = inst["InstanceId"]
                    platform = inst.get("Platform", "linux")  # 'windows' if Windows

                    if inst_type not in GRAVITON_MIGRATION:
                        continue

                    # Skip Windows — Graviton doesn't support Windows
                    if platform and "windows" in str(platform).lower():
                        continue

                    graviton_type, savings_pct = GRAVITON_MIGRATION[inst_type]
                    hourly = INSTANCE_HOURLY.get(inst_type, 0.10)
                    graviton_hourly = INSTANCE_HOURLY.get(graviton_type, hourly * 0.8)
                    monthly_saving = round((hourly - graviton_hourly) * 730, 2)
                    annual_saving = round(monthly_saving * 12, 2)

                    if monthly_saving > 1:
                        findings.append({
                            "service": "ec2",
                            "region": r,
                            "resource_id": inst_id,
                            "finding": "graviton_migration",
                            "severity": "high" if monthly_saving > 30 else "medium",
                            "instance_type": inst_type,
                            "recommended_type": graviton_type,
                            "chip_architecture": "x86 → ARM (Graviton)",
                            "savings_pct": round(savings_pct, 1),
                            "detail": (
                                f"{inst_id}: {inst_type} (x86) → {graviton_type} (Graviton ARM) "
                                f"– save {savings_pct:.0f}% (${monthly_saving:.2f}/mo, ${annual_saving:.0f}/yr)"
                            ),
                            "action": (
                                f"Migrate to {graviton_type}. Most Linux apps work without changes. "
                                f"Rebuild containers with --platform linux/arm64."
                            ),
                            "estimated_monthly_savings_usd": monthly_saving,
                        })

        return findings

    # ── Old generation upgrades ─────────────────────────────────────

    def _check_old_generations(self, region: str) -> list[dict[str, Any]]:
        findings = []
        ec2 = self._session.client("ec2", region_name=region)

        try:
            instances = ec2.describe_instances(
                Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
            )
        except Exception:
            return []

        for res in instances.get("Reservations", []):
            for inst in res.get("Instances", []):
                inst_type = inst.get("InstanceType", "")
                family = inst_type.split(".")[0] if "." in inst_type else ""

                if family not in OLD_GEN_UPGRADE:
                    continue

                new_family = OLD_GEN_UPGRADE[family]
                size = inst_type.split(".")[1] if "." in inst_type else "large"
                new_type = f"{new_family}.{size}"
                hourly = INSTANCE_HOURLY.get(inst_type, 0.10)
                new_hourly = INSTANCE_HOURLY.get(new_type, hourly * 0.85)

                # Check if there's also a Graviton version of the new family
                graviton_type = None
                graviton_savings = 0
                if new_type in GRAVITON_MIGRATION:
                    graviton_type = GRAVITON_MIGRATION[new_type][0]
                    graviton_hourly = INSTANCE_HOURLY.get(graviton_type, new_hourly)
                    graviton_savings = round((new_hourly - graviton_hourly) * 730, 2)

                monthly_savings = round((hourly - new_hourly) * 730, 2)

                finding = {
                    "service": "ec2",
                    "region": region,
                    "resource_id": inst["InstanceId"],
                    "finding": "old_generation",
                    "severity": "medium",
                    "instance_type": inst_type,
                    "recommended_type": new_type,
                    "detail": f"{inst['InstanceId']}: {family} → {new_family} (newer gen, better perf)",
                    "action": f"Migrate to {new_type}",
                    "estimated_monthly_savings_usd": monthly_savings,
                }

                if graviton_type and graviton_savings > 0:
                    finding["detail"] += f" — or go Graviton: {graviton_type} (extra ${graviton_savings:.0f}/mo)"
                    finding["action"] += f", or {graviton_type} for ARM savings"
                    finding["estimated_monthly_savings_usd"] += graviton_savings

                findings.append(finding)

        return findings


# ── Helpers ────────────────────────────────────────────────────────────


def _ebs_cost(volume_id: str, ec2_client) -> float:
    """Estimate monthly EBS cost for a volume."""
    try:
        vol = ec2_client.describe_volumes(VolumeIds=[volume_id])
        if vol["Volumes"]:
            size = vol["Volumes"][0]["Size"]
            vtype = vol["Volumes"][0].get("VolumeType", "gp3")
            rates = {"gp3": 0.08, "gp2": 0.10, "io1": 0.125, "io2": 0.125, "st1": 0.045, "sc1": 0.015}
            return size * rates.get(vtype, 0.08)
    except Exception:
        pass
    return 0
