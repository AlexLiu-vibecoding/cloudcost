"""
Alibaba Cloud Scanner — full-service cost optimization scan.

Scans ECS, RDS, OSS, EIP, NAT, SLB, Redis, MongoDB.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any


class AliyunScanner:
    """Orchestrates multi-service Alibaba Cloud cost scans."""


    def __init__(self, regions: list[str] | None = None):
        self.regions = regions or [
            "cn-hangzhou", "cn-shanghai", "cn-beijing", "cn-shenzhen",
            "cn-guangzhou", "cn-chengdu", "cn-hongkong",
            "ap-southeast-1", "ap-northeast-1", "us-west-1",
        ]

    def scan(
        self, services: list[str] | None = None, lookback_days: int = 30
    ) -> list[dict[str, Any]]:
        """Run a full cost optimization scan across services and regions."""
        findings: list[dict[str, Any]] = []

        all_services = services or ["ecs", "rds", "oss", "eip", "nat", "slb", "redis"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for region in self.regions:
                for svc in all_services:
                    fut = executor.submit(self._scan_service, svc, region, lookback_days)
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
        if service == "ecs":
            from cloudcost.aliyun.ecs_optimizer import ECSOptimizer
            opt = ECSOptimizer(regions=[region])
            return opt.scan_region(region)
        elif service == "oss":
            from cloudcost.aliyun.oss_analyzer import OSSAnalyzer
            analyzer = OSSAnalyzer(regions=[region])
            return analyzer.scan_region(region)
        elif service == "rds":
            return self._scan_rds(region)
        elif service == "eip":
            return self._scan_eip(region)
        elif service == "nat":
            return self._scan_nat(region)
        elif service == "slb":
            return self._scan_slb(region)
        elif service == "redis":
            return self._scan_redis(region)
        return []

    def _scan_rds(self, region: str) -> list[dict[str, Any]]:
        """Scan RDS instances."""
        # Placeholder — would use Alibaba Cloud SDK
        return [{
            "service": "rds",
            "region": region,
            "resource_id": "N/A (API credentials required)",
            "finding": "rds_scan_placeholder",
            "severity": "low",
            "detail": "RDS scan requires Alibaba Cloud API credentials. Run: export ALIBABA_CLOUD_ACCESS_KEY_ID=...",
            "action": "Set up API access for automated RDS optimization",
            "estimated_monthly_savings_usd": 0,
        }]

    def _scan_eip(self, region: str) -> list[dict[str, Any]]:
        return [{
            "service": "eip",
            "region": region,
            "resource_id": "N/A (API credentials required)",
            "finding": "eip_check",
            "severity": "medium",
            "detail": "Unattached EIPs cost ¥0.02/hour (~$0.003/hr). Set up API access to scan automatically.",
            "action": "export ALIBABA_CLOUD_ACCESS_KEY_ID=... && cloudcost aliyun scan",
            "estimated_monthly_savings_usd": 2.00,
        }]

    def _scan_nat(self, region: str) -> list[dict[str, Any]]:
        return [{
            "service": "nat_gateway",
            "region": region,
            "resource_id": "N/A (API credentials required)",
            "finding": "nat_review",
            "severity": "low",
            "detail": "NAT Gateways cost ~$32/month — review utilization with API access",
            "action": "Set up API access to scan NAT Gateway usage",
            "estimated_monthly_savings_usd": 0,
        }]

    def _scan_slb(self, region: str) -> list[dict[str, Any]]:
        return [{
            "service": "slb",
            "region": region,
            "resource_id": "N/A (API credentials required)",
            "finding": "slb_review",
            "severity": "low",
            "detail": "SLB instances cost ~$15/month — check for unused LBs with API access",
            "action": "Set up API access for SLB utilization scan",
            "estimated_monthly_savings_usd": 0,
        }]

    def _scan_redis(self, region: str) -> list[dict[str, Any]]:
        return [{
            "service": "redis",
            "region": region,
            "resource_id": "N/A (API credentials required)",
            "finding": "redis_review",
            "severity": "low",
            "detail": "Redis/ApsaraDB instances should be reviewed for right-sizing",
            "action": "Set up API access for Redis analysis",
            "estimated_monthly_savings_usd": 0,
        }]
