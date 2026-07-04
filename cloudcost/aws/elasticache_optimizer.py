"""
AWS ElastiCache Optimizer — Redis & Memcached cost optimization.

Checks: Graviton ARM migration, right-sizing, idle cluster detection,
RI planning, engine-specific optimization.
"""

from __future__ import annotations

import datetime
from typing import Any

import boto3


# ── ElastiCache node pricing (us-east-1, on-demand hourly USD) ─────

CACHE_HOURLY = {
    # T-series (burstable, dev/test)
    "cache.t3.micro": 0.017, "cache.t3.small": 0.034, "cache.t3.medium": 0.068,
    "cache.t4g.micro": 0.016, "cache.t4g.small": 0.032, "cache.t4g.medium": 0.064,
    # M-series (general purpose) — x86
    "cache.m6i.large": 0.182, "cache.m6i.xlarge": 0.364, "cache.m6i.2xlarge": 0.728,
    "cache.m5.large": 0.171, "cache.m5.xlarge": 0.342, "cache.m5.2xlarge": 0.684,
    # M-series (Graviton ARM)
    "cache.m7g.large": 0.155, "cache.m7g.xlarge": 0.309, "cache.m7g.2xlarge": 0.619,
    "cache.m6g.large": 0.146, "cache.m6g.xlarge": 0.291, "cache.m6g.2xlarge": 0.582,
    # R-series (memory optimized) — x86
    "cache.r6i.large": 0.253, "cache.r6i.xlarge": 0.506, "cache.r6i.2xlarge": 1.012,
    "cache.r5.large": 0.237, "cache.r5.xlarge": 0.474, "cache.r5.2xlarge": 0.948,
    # R-series (Graviton ARM)
    "cache.r7g.large": 0.215, "cache.r7g.xlarge": 0.430, "cache.r7g.2xlarge": 0.860,
    "cache.r6g.large": 0.202, "cache.r6g.xlarge": 0.404, "cache.r6g.2xlarge": 0.809,
}


# ── x86 → Graviton migration map ────────────────────────────────────

CACHE_GRAVITON_MAP = {
    "cache.m6i.large": ("cache.m7g.large", 14.8),
    "cache.m6i.xlarge": ("cache.m7g.xlarge", 15.1),
    "cache.m6i.2xlarge": ("cache.m7g.2xlarge", 15.0),
    "cache.m5.large": ("cache.m7g.large", 9.4),
    "cache.m5.xlarge": ("cache.m7g.xlarge", 9.6),
    "cache.r6i.large": ("cache.r7g.large", 15.0),
    "cache.r6i.xlarge": ("cache.r7g.xlarge", 15.0),
    "cache.r6i.2xlarge": ("cache.r7g.2xlarge", 15.0),
    "cache.r5.large": ("cache.r7g.large", 9.3),
    "cache.r5.xlarge": ("cache.r7g.xlarge", 9.3),
    "cache.t3.micro": ("cache.t4g.micro", 5.9),
    "cache.t3.small": ("cache.t4g.small", 5.9),
    "cache.t3.medium": ("cache.t4g.medium", 5.9),
}

# Memory capacity per node type (approx, GB)
NODE_MEMORY_GB = {
    "cache.t3.micro": 0.5, "cache.t3.small": 1.4, "cache.t3.medium": 3.1,
    "cache.t4g.micro": 0.5, "cache.t4g.small": 1.4, "cache.t4g.medium": 3.1,
    "cache.m6i.large": 6.4, "cache.m6i.xlarge": 12.9, "cache.m6i.2xlarge": 25.9,
    "cache.m5.large": 6.4, "cache.m5.xlarge": 12.9, "cache.m5.2xlarge": 25.9,
    "cache.m7g.large": 6.4, "cache.m7g.xlarge": 12.9, "cache.m7g.2xlarge": 25.9,
    "cache.m6g.large": 6.4, "cache.m6g.xlarge": 12.9, "cache.m6g.2xlarge": 25.9,
    "cache.r6i.large": 13.1, "cache.r6i.xlarge": 26.3, "cache.r6i.2xlarge": 52.6,
    "cache.r5.large": 13.1, "cache.r5.xlarge": 26.3, "cache.r5.2xlarge": 52.6,
    "cache.r7g.large": 13.1, "cache.r7g.xlarge": 26.3, "cache.r7g.2xlarge": 52.6,
    "cache.r6g.large": 13.1, "cache.r6g.xlarge": 26.3, "cache.r6g.2xlarge": 52.6,
}


class ElastiCacheOptimizer:
    """Comprehensive ElastiCache cost optimization analyzer."""

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
        self.regions = regions or ["us-east-1", "us-east-2", "us-west-2"]

    def analyze(self) -> list[dict[str, Any]]:
        findings = []
        for region in self.regions:
            findings.extend(self.scan_region(region))
        return sorted(findings, key=lambda x: x.get("estimated_monthly_savings_usd", 0), reverse=True)

    def scan_region(self, region: str) -> list[dict[str, Any]]:
        findings = []
        ec = self._session.client("elasticache", region_name=region)
        cw = self._session.client("cloudwatch", region_name=region)

        # Scan Redis clusters
        try:
            redis_clusters = ec.describe_cache_clusters(
                ShowCacheNodeInfo=True,
                MaxRecords=100,
            )
            for cluster in redis_clusters.get("CacheClusters", []):
                findings.extend(
                    self._analyze_cluster(cluster, "redis", ec, cw, region)
                )
        except Exception:
            pass

        return findings

    def _analyze_cluster(
        self, cluster: dict, engine_type: str, ec, cw, region: str
    ) -> list[dict[str, Any]]:
        findings = []
        cluster_id = cluster["CacheClusterId"]
        node_type = cluster.get("CacheNodeType", "")
        engine = cluster.get("Engine", engine_type)
        num_nodes = cluster.get("NumCacheNodes", 1)
        status = cluster.get("CacheClusterStatus", "")

        if status in ("deleting", "deleted"):
            return []

        # ── Graviton migration ────────────────────────────────────
        findings.extend(self._check_graviton_cache(
            cluster_id, node_type, engine, num_nodes, region
        ))

        # ── Right-sizing ──────────────────────────────────────────
        findings.extend(self._check_rightsize_cache(
            cluster_id, node_type, engine, num_nodes, region, cw
        ))

        # ── Idle cluster detection ────────────────────────────────
        findings.extend(self._check_idle_cache(
            cluster_id, node_type, num_nodes, region, cw
        ))

        # ── RI planning ───────────────────────────────────────────
        findings.extend(self._check_ri_cache(
            cluster_id, node_type, engine, num_nodes, region
        ))

        # ── Engine-specific ───────────────────────────────────────
        findings.extend(self._check_engine_specific(
            cluster, engine, region
        ))

        return findings

    # ── Graviton ──────────────────────────────────────────────────────

    def _check_graviton_cache(
        self, cluster_id: str, node_type: str, engine: str,
        num_nodes: int, region: str
    ) -> list[dict[str, Any]]:
        if node_type not in CACHE_GRAVITON_MAP:
            return []

        graviton_type, savings_pct = CACHE_GRAVITON_MAP[node_type]
        hourly = CACHE_HOURLY.get(node_type, 0.15)
        grav_hourly = CACHE_HOURLY.get(graviton_type, hourly * 0.85)
        monthly_saving = round((hourly - grav_hourly) * 730 * num_nodes, 2)

        if monthly_saving < 2:
            return []

        return [{
            "service": "elasticache",
            "region": region,
            "resource_id": cluster_id,
            "finding": "graviton_migration",
            "severity": "high" if monthly_saving > 30 else "medium",
            "node_type": node_type,
            "recommended_type": graviton_type,
            "chip_architecture": "x86 → ARM (Graviton)",
            "savings_pct": round(savings_pct, 1),
            "detail": (
                f"{engine} {cluster_id}: {node_type} × {num_nodes} → {graviton_type} "
                f"(Graviton ARM) — save {savings_pct:.0f}% (${monthly_saving:.2f}/mo)"
            ),
            "action": (
                f"Upgrade to {graviton_type}. ElastiCache fully supports Graviton. "
                f"Take snapshot, restore to new Graviton cluster."
            ),
            "estimated_monthly_savings_usd": monthly_saving,
        }]

    # ── Right-sizing ──────────────────────────────────────────────────

    def _check_rightsize_cache(
        self, cluster_id: str, node_type: str, engine: str,
        num_nodes: int, region: str, cw
    ) -> list[dict[str, Any]]:
        """Check if cluster has low memory/CPU usage and can be downsized."""
        cpu = self._get_metric(cw, "AWS/ElastiCache", "CPUUtilization",
                               "CacheClusterId", cluster_id, 7)

        # Only recommend if CPU is available and very low
        if not cpu or cpu > 25:
            return []

        # Memory usage check
        mem_used = self._get_metric(cw, "AWS/ElastiCache", "BytesUsedForCache",
                                    "CacheClusterId", cluster_id, 7)
        total_mem = NODE_MEMORY_GB.get(node_type, 6) * 1024 ** 3  # GB → bytes

        if not mem_used:
            return []

        mem_pct = mem_used / total_mem * 100 if total_mem > 0 else 0

        if mem_pct > 40 or cpu > 20:
            return []  # Actually being used

        # Find a smaller node
        downsizes = {
            "cache.m6i.xlarge": "cache.m6i.large",
            "cache.m6i.2xlarge": "cache.m6i.xlarge",
            "cache.r6i.xlarge": "cache.r6i.large",
            "cache.r6i.2xlarge": "cache.r6i.xlarge",
            "cache.m5.xlarge": "cache.m5.large",
            "cache.m5.2xlarge": "cache.m5.xlarge",
            "cache.r5.xlarge": "cache.r5.large",
            "cache.r5.2xlarge": "cache.r5.xlarge",
            "cache.m7g.xlarge": "cache.m7g.large",
            "cache.m7g.2xlarge": "cache.m7g.xlarge",
            "cache.r7g.xlarge": "cache.r7g.large",
            "cache.r7g.2xlarge": "cache.r7g.xlarge",
        }

        if node_type not in downsizes:
            return []

        smaller = downsizes[node_type]
        hourly = CACHE_HOURLY.get(node_type, 0.15)
        smaller_hourly = CACHE_HOURLY.get(smaller, hourly * 0.5)
        monthly_saving = round((hourly - smaller_hourly) * 730 * num_nodes, 2)

        if monthly_saving < 5:
            return []

        return [{
            "service": "elasticache",
            "region": region,
            "resource_id": cluster_id,
            "finding": "right_size",
            "severity": "high" if monthly_saving > 50 else "medium",
            "node_type": node_type,
            "recommended_type": smaller,
            "avg_cpu_pct": round(cpu, 1),
            "avg_memory_pct": round(mem_pct, 1),
            "detail": (
                f"{engine} {cluster_id}: {node_type}, {mem_pct:.0f}% memory, "
                f"{cpu:.0f}% CPU → downsize to {smaller}"
            ),
            "action": f"Modify to {smaller}. Save ${monthly_saving:.0f}/mo.",
            "estimated_monthly_savings_usd": monthly_saving,
        }]

    # ── Idle cluster detection ────────────────────────────────────────

    def _check_idle_cache(
        self, cluster_id: str, node_type: str, num_nodes: int,
        region: str, cw
    ) -> list[dict[str, Any]]:
        """Detect clusters with negligible usage."""
        # Check multiple metrics to determine if truly idle
        cpu = self._get_metric(cw, "AWS/ElastiCache", "CPUUtilization",
                               "CacheClusterId", cluster_id, 7)
        cmds = self._get_metric(cw, "AWS/ElastiCache", "CacheHitRate",
                                "CacheClusterId", cluster_id, 7)
        conns = self._get_metric(cw, "AWS/ElastiCache", "CurrConnections",
                                 "CacheClusterId", cluster_id, 7)

        is_idle = (
            (cpu is not None and cpu < 1.0) and
            (conns is not None and conns < 2) and
            (cmds is not None and cmds < 5)
        )

        if not is_idle:
            return []

        hourly = CACHE_HOURLY.get(node_type, 0.15)
        monthly = round(hourly * 730 * num_nodes, 2)

        return [{
            "service": "elasticache",
            "region": region,
            "resource_id": cluster_id,
            "finding": "idle_cluster",
            "severity": "high",
            "node_type": node_type,
            "avg_cpu_pct": round(cpu or 0, 1),
            "avg_connections": round(conns or 0, 1),
            "detail": (
                f"{cluster_id} ({node_type} × {num_nodes}): "
                f"CPU {cpu or 0:.1f}%, {conns or 0:.0f} connections — appears idle"
            ),
            "action": "Snapshot and delete if unused. Costs ${:.0f}/mo.".format(monthly),
            "estimated_monthly_savings_usd": monthly,
        }]

    # ── RI planning ───────────────────────────────────────────────────

    def _check_ri_cache(
        self, cluster_id: str, node_type: str, engine: str,
        num_nodes: int, region: str
    ) -> list[dict[str, Any]]:
        hourly = CACHE_HOURLY.get(node_type, 0.10)
        monthly = hourly * 730 * num_nodes

        if monthly < 50:
            return []

        ri_savings = round(monthly * 0.35, 2)
        return [{
            "service": "elasticache",
            "region": region,
            "resource_id": cluster_id,
            "finding": "ri_candidate",
            "severity": "medium",
            "node_type": node_type,
            "num_nodes": num_nodes,
            "detail": (
                f"{engine} {cluster_id}: {node_type} × {num_nodes} ~${monthly:.0f}/mo. "
                f"1-year RI saves 35% (${ri_savings:.0f}/mo)"
            ),
            "action": f"Purchase ElastiCache RI for {node_type} in {region}",
            "estimated_monthly_savings_usd": ri_savings,
        }]

    # ── Engine-specific optimization ──────────────────────────────────

    def _check_engine_specific(
        self, cluster: dict, engine: str, region: str
    ) -> list[dict[str, Any]]:
        findings = []
        cluster_id = cluster["CacheClusterId"]

        if "redis" in engine.lower():
            # Redis: check if cluster mode could save money (scale out with smaller nodes)
            num_nodes = cluster.get("NumCacheNodes", 1)
            node_type = cluster.get("CacheNodeType", "")

            if num_nodes >= 2:
                findings.append({
                    "service": "elasticache",
                    "region": region,
                    "resource_id": cluster_id,
                    "finding": "redis_cluster_mode",
                    "severity": "low",
                    "detail": (
                        f"Redis {cluster_id}: {num_nodes} nodes. "
                        f"Consider Redis Cluster Mode Enabled — scale out with smaller, cheaper shards."
                    ),
                    "action": "Evaluate Cluster Mode for horizontal scaling with smaller nodes",
                    "estimated_monthly_savings_usd": 0,
                })

        elif "memcached" in engine.lower():
            # Memcached: check if node count is balanced
            num_nodes = cluster.get("NumCacheNodes", 1)
            if num_nodes == 1:
                findings.append({
                    "service": "elasticache",
                    "region": region,
                    "resource_id": cluster_id,
                    "finding": "memcached_single_node",
                    "severity": "low",
                    "detail": f"Memcached {cluster_id}: single node — no HA. Consider >=2 nodes.",
                    "action": "Add at least 1 more node for failover",
                    "estimated_monthly_savings_usd": 0,
                })

        return findings

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_metric(
        self, cw, namespace: str, metric: str, dim_name: str, dim_value: str, days: int
    ) -> float | None:
        try:
            resp = cw.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric,
                Dimensions=[{"Name": dim_name, "Value": dim_value}],
                StartTime=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days),
                EndTime=datetime.datetime.now(datetime.timezone.utc),
                Period=3600,
                Statistics=["Average"],
            )
            if resp["Datapoints"]:
                return sum(p["Average"] for p in resp["Datapoints"]) / len(resp["Datapoints"])
        except Exception:
            pass
        return None
