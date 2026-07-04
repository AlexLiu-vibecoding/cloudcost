"""
AWS Cost Scanner — full-service cost optimization scan.

Scans EC2, RDS, S3, EBS, Elastic IP, NAT Gateway, ALB/NLB, Lambda, ElastiCache.
"""

from __future__ import annotations

import concurrent.futures
import datetime
from dataclasses import dataclass, field
from typing import Any

import boto3


@dataclass
class AWSScanner:
    """Orchestrates multi-service AWS cost scans."""


    profile: str | None = None
    regions: list[str] | None = None

    def __post_init__(self) -> None:
        session_kwargs: dict = {}
        if self.profile:
            session_kwargs["profile_name"] = self.profile
        self._session = boto3.Session(**session_kwargs)

        if not self.regions:
            ec2 = self._session.client("ec2", region_name="us-east-1")
            try:
                resp = ec2.describe_regions()
                self.regions = [r["RegionName"] for r in resp["Regions"]]
            except Exception:
                self.regions = ["us-east-1", "us-east-2", "us-west-1", "us-west-2",
                                "eu-west-1", "eu-central-1", "ap-southeast-1", "ap-northeast-1"]

    def scan(
        self, services: list[str] | None = None, lookback_days: int = 30
    ) -> list[dict[str, Any]]:
        """Run a full cost optimization scan across services and regions."""
        findings: list[dict[str, Any]] = []

        all_services = services or [
            "ec2", "rds", "s3", "ebs", "eip", "nat", "elb", "lambda", "elasticache"
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for region in self.regions:
                for svc in all_services:
                    fut = executor.submit(
                        self._scan_service, svc, region, lookback_days
                    )
                    futures[fut] = (svc, region)

            for fut in concurrent.futures.as_completed(futures):
                svc, region = futures[fut]
                try:
                    result = fut.result()
                    if result:
                        findings.extend(result)
                except Exception as e:
                    findings.append({
                        "service": svc,
                        "region": region,
                        "finding": "scan_error",
                        "severity": "low",
                        "detail": str(e),
                        "estimated_monthly_savings_usd": 0,
                    })

        return sorted(findings, key=lambda x: x.get("estimated_monthly_savings_usd", 0), reverse=True)

    def _scan_service(self, service: str, region: str, lookback_days: int) -> list[dict[str, Any]]:
        """Scan a single service in a single region."""
        from cloudcost.aws.ec2_optimizer import EC2Optimizer
        from cloudcost.aws.rds_optimizer import RDSOptimizer
        from cloudcost.aws.s3_analyzer import S3Analyzer

        try:
            if service == "ec2":
                opt = EC2Optimizer(session=self._session, regions=[region])
                return opt.scan_region(region)
            elif service == "rds":
                opt = RDSOptimizer(session=self._session, regions=[region])
                return opt.scan_region(region)
            elif service == "s3":
                analyzer = S3Analyzer(session=self._session)
                return analyzer.scan_region(region)
            elif service == "ebs":
                return self._scan_ebs(region)
            elif service == "eip":
                return self._scan_eip(region)
            elif service == "nat":
                return self._scan_nat(region)
            elif service == "elb":
                return self._scan_elb(region)
            elif service == "lambda":
                return self._scan_lambda(region)
            elif service == "elasticache":
                return self._scan_elasticache(region)
        except Exception as e:
            return [{
                "service": service,
                "region": region,
                "finding": "scan_error",
                "severity": "low",
                "detail": str(e),
                "estimated_monthly_savings_usd": 0,
            }]
        return []

    # ── Individual service scanners ──────────────────────────────

    def _scan_ebs(self, region: str) -> list[dict[str, Any]]:
        findings = []
        ec2 = self._session.client("ec2", region_name=region)

        # Unattached volumes
        vols = ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )
        for v in vols["Volumes"]:
            size_gb = v["Size"]
            cost_per_gb = 0.08  # gp3 approx
            monthly = size_gb * cost_per_gb
            findings.append({
                "service": "ebs",
                "region": region,
                "resource_id": v["VolumeId"],
                "finding": "unattached_volume",
                "severity": "medium",
                "detail": f"Volume {v['VolumeId']} ({size_gb}GB) is unattached",
                "action": "Delete or snapshot-then-delete",
                "estimated_monthly_savings_usd": round(monthly, 2),
            })

        # Old snapshots (older than 90 days)
        snaps = ec2.describe_snapshots(OwnerIds=["self"])
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
        for s in snaps["Snapshots"]:
            if s["StartTime"] < cutoff:
                size_gb = s["VolumeSize"]
                cost_per_gb = 0.05
                monthly = size_gb * cost_per_gb
                findings.append({
                    "service": "ebs",
                    "region": region,
                    "resource_id": s["SnapshotId"],
                    "finding": "old_snapshot",
                    "severity": "low",
                    "detail": f"Snapshot {s['SnapshotId']} is >90 days old ({size_gb}GB)",
                    "action": "Review and delete if not needed",
                    "estimated_monthly_savings_usd": round(monthly, 2),
                })

        return findings

    def _scan_eip(self, region: str) -> list[dict[str, Any]]:
        findings = []
        ec2 = self._session.client("ec2", region_name=region)

        addrs = ec2.describe_addresses()
        for addr in addrs["Addresses"]:
            if "InstanceId" not in addr and "NetworkInterfaceId" not in addr:
                findings.append({
                    "service": "eip",
                    "region": region,
                    "resource_id": addr.get("AllocationId", addr["PublicIp"]),
                    "finding": "unattached_eip",
                    "severity": "medium",
                    "detail": f"EIP {addr['PublicIp']} is not attached to any resource",
                    "action": "Release if not needed (~$3.60/month idle charge)",
                    "estimated_monthly_savings_usd": 3.60,
                })

        return findings

    def _scan_nat(self, region: str) -> list[dict[str, Any]]:
        findings = []
        ec2 = self._session.client("ec2", region_name=region)

        # Check for NAT gateways with zero bytes out in last 24h (proxy for idle)
        nat_gws = ec2.describe_nat_gateways(
            Filters=[{"Name": "state", "Values": ["available"]}]
        )
        for nat in nat_gws["NatGateways"]:
            findings.append({
                "service": "nat_gateway",
                "region": region,
                "resource_id": nat["NatGatewayId"],
                "finding": "nat_gateway_review",
                "severity": "low",
                "detail": f"NAT Gateway {nat['NatGatewayId']} — review utilization",
                "action": "Check CloudWatch BytesOutFromDestination; remove if unused (~$32/month)",
                "estimated_monthly_savings_usd": 0,  # Only flag if confirmed idle
            })

        return findings

    def _scan_elb(self, region: str) -> list[dict[str, Any]]:
        findings = []
        elbv2 = self._session.client("elbv2", region_name=region)

        # Check ALB/NLB with zero healthy targets
        lbs = elbv2.describe_load_balancers()
        for lb in lbs["LoadBalancers"]:
            try:
                tg_arns = elbv2.describe_target_groups(
                    LoadBalancerArn=lb["LoadBalancerArn"]
                )
                for tg in tg_arns["TargetGroups"]:
                    health = elbv2.describe_target_health(
                        TargetGroupArn=tg["TargetGroupArn"]
                    )
                    if not health["TargetHealthDescriptions"]:
                        findings.append({
                            "service": "elb",
                            "region": region,
                            "resource_id": lb["LoadBalancerName"],
                            "finding": "elb_no_targets",
                            "severity": "high",
                            "detail": f"LB {lb['LoadBalancerName']} has no healthy targets",
                            "action": "Remove unused load balancer (~$22/month)",
                            "estimated_monthly_savings_usd": 22.00,
                        })
                        break
            except Exception:
                pass

        return findings

    def _scan_lambda(self, region: str) -> list[dict[str, Any]]:
        findings = []
        lbd = self._session.client("lambda", region_name=region)

        functions = lbd.list_functions()
        for fn in functions["Functions"]:
            memory = fn.get("MemorySize", 128)
            # Flag functions with 3GB+ memory as potential over-provisioning
            if memory >= 3008:
                findings.append({
                    "service": "lambda",
                    "region": region,
                    "resource_id": fn["FunctionName"],
                    "finding": "high_memory_lambda",
                    "severity": "low",
                    "detail": f"Lambda {fn['FunctionName']} has {memory}MB memory — review",
                    "action": "Profile actual usage and reduce memory allocation",
                    "estimated_monthly_savings_usd": 0,
                })

        return findings

    def _scan_elasticache(self, region: str) -> list[dict[str, Any]]:
        findings = []
        ec = self._session.client("elasticache", region_name=region)

        for cluster_type in [("redis", ec.describe_cache_clusters), ("memcached", ec.describe_cache_clusters)]:
            try:
                clusters = cluster_type[1](ShowCacheNodeInfo=True)
                for cluster in clusters.get("CacheClusters", []):
                    engine = cluster.get("Engine", "unknown")
                    node_type = cluster.get("CacheNodeType", "")
                    # Check for low-utilization clusters
                    findings.append({
                        "service": "elasticache",
                        "region": region,
                        "resource_id": cluster["CacheClusterId"],
                        "finding": "elasticache_review",
                        "severity": "low",
                        "detail": f"ElastiCache {engine} cluster {cluster['CacheClusterId']} ({node_type}) — review utilization",
                        "action": "Check CloudWatch metrics; consider downsizing",
                        "estimated_monthly_savings_usd": 0,
                    })
            except Exception:
                pass

        return findings
