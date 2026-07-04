"""
AWS RDS Optimizer — comprehensive database cost optimization.

Checks: Graviton ARM migration, right-sizing, engine upgrade,
Aurora migration, RI/SP planning, backup optimization, Multi-AZ waste,
storage over-provisioning, public accessibility.
"""

from __future__ import annotations

import datetime
from typing import Any

import boto3


# ── RDS instance pricing (us-east-1, single-AZ, on-demand hourly USD) ──

RDS_HOURLY = {
    # T-series (burstable, dev/test)
    "db.t3.micro": 0.017, "db.t3.small": 0.034, "db.t3.medium": 0.068,
    "db.t3.large": 0.136, "db.t3.xlarge": 0.272, "db.t3.2xlarge": 0.544,
    "db.t4g.micro": 0.016, "db.t4g.small": 0.033, "db.t4g.medium": 0.065,
    "db.t4g.large": 0.129, "db.t4g.xlarge": 0.258, "db.t4g.2xlarge": 0.516,
    # M-series (general purpose) — x86
    "db.m6i.large": 0.182, "db.m6i.xlarge": 0.364, "db.m6i.2xlarge": 0.728,
    "db.m6i.4xlarge": 1.456, "db.m6i.8xlarge": 2.912,
    "db.m5.large": 0.171, "db.m5.xlarge": 0.342, "db.m5.2xlarge": 0.684,
    "db.m5.4xlarge": 1.368, "db.m5a.large": 0.163, "db.m5a.xlarge": 0.326,
    # M-series (Graviton ARM)
    "db.m7g.large": 0.155, "db.m7g.xlarge": 0.309, "db.m7g.2xlarge": 0.619,
    "db.m7g.4xlarge": 1.238, "db.m7g.8xlarge": 2.475,
    "db.m6g.large": 0.146, "db.m6g.xlarge": 0.291, "db.m6g.2xlarge": 0.582,
    # R-series (memory optimized) — x86
    "db.r6i.large": 0.253, "db.r6i.xlarge": 0.506, "db.r6i.2xlarge": 1.012,
    "db.r6i.4xlarge": 2.024, "db.r6i.8xlarge": 4.048,
    "db.r5.large": 0.237, "db.r5.xlarge": 0.474, "db.r5.2xlarge": 0.948,
    "db.r5.4xlarge": 1.896, "db.r5a.large": 0.227, "db.r5a.xlarge": 0.453,
    # R-series (Graviton ARM)
    "db.r7g.large": 0.215, "db.r7g.xlarge": 0.430, "db.r7g.2xlarge": 0.860,
    "db.r7g.4xlarge": 1.720, "db.r7g.8xlarge": 3.441,
    "db.r6g.large": 0.202, "db.r6g.xlarge": 0.404, "db.r6g.2xlarge": 0.809,
    # X-series (memory-heavy, no Graviton equivalent yet)
    "db.x2g.large": 0.334, "db.x2g.xlarge": 0.668, "db.x2g.2xlarge": 1.336,
}


# ── x86 → Graviton migration map for RDS ──────────────────────────────

RDS_GRAVITON_MAP = {
    # General purpose
    "db.m6i.large": ("db.m7g.large", 14.8),
    "db.m6i.xlarge": ("db.m7g.xlarge", 15.1),
    "db.m6i.2xlarge": ("db.m7g.2xlarge", 15.0),
    "db.m6i.4xlarge": ("db.m7g.4xlarge", 15.0),
    "db.m5.large": ("db.m7g.large", 9.4),
    "db.m5.xlarge": ("db.m7g.xlarge", 9.6),
    "db.m5.2xlarge": ("db.m7g.2xlarge", 9.5),
    "db.m5.4xlarge": ("db.m7g.4xlarge", 9.5),
    "db.m5a.large": ("db.m7g.large", 4.9),
    # Memory optimized
    "db.r6i.large": ("db.r7g.large", 15.0),
    "db.r6i.xlarge": ("db.r7g.xlarge", 15.0),
    "db.r6i.2xlarge": ("db.r7g.2xlarge", 15.0),
    "db.r6i.4xlarge": ("db.r7g.4xlarge", 15.0),
    "db.r5.large": ("db.r7g.large", 9.3),
    "db.r5.xlarge": ("db.r7g.xlarge", 9.3),
    "db.r5.2xlarge": ("db.r7g.2xlarge", 9.3),
    "db.r5.4xlarge": ("db.r7g.4xlarge", 9.3),
    "db.r5a.large": ("db.r7g.large", 5.3),
    # Burstable
    "db.t3.micro": ("db.t4g.micro", 5.9),
    "db.t3.small": ("db.t4g.small", 2.9),
    "db.t3.medium": ("db.t4g.medium", 4.4),
    "db.t3.large": ("db.t4g.large", 5.1),
    "db.t3.xlarge": ("db.t4g.xlarge", 5.1),
    "db.t3.2xlarge": ("db.t4g.2xlarge", 5.1),
}


# ── Engine details ─────────────────────────────────────────────────────

ENGINE_DETAILS = {
    "mysql": {"name": "MySQL", "aurora_compatible": True, "aurora_engine": "aurora-mysql"},
    "postgres": {"name": "PostgreSQL", "aurora_compatible": True, "aurora_engine": "aurora-postgresql"},
    "mariadb": {"name": "MariaDB", "aurora_compatible": False},
    "oracle-se": {"name": "Oracle SE", "aurora_compatible": False},
    "oracle-ee": {"name": "Oracle EE", "aurora_compatible": False},
    "sqlserver-se": {"name": "SQL Server", "aurora_compatible": False},
    "sqlserver-ee": {"name": "SQL Server EE", "aurora_compatible": False},
    "sqlserver-ex": {"name": "SQL Server Express", "aurora_compatible": False},
    "sqlserver-web": {"name": "SQL Server Web", "aurora_compatible": False},
}


class RDSOptimizer:
    """Comprehensive RDS cost optimization analyzer."""

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
        rds = self._session.client("rds", region_name=region)
        cw = self._session.client("cloudwatch", region_name=region)

        try:
            dbs = rds.describe_db_instances()
        except Exception:
            return []

        for db in dbs.get("DBInstances", []):
            findings.extend(self._analyze_instance(db, rds, cw, region))

        return findings

    def _analyze_instance(self, db: dict, rds, cw, region: str) -> list[dict[str, Any]]:
        findings = []
        db_id = db["DBInstanceIdentifier"]
        db_class = db.get("DBInstanceClass", "")
        engine = db.get("Engine", "")
        multi_az = db.get("MultiAZ", False)
        storage_gb = db.get("AllocatedStorage", 20)
        storage_type = db.get("StorageType", "gp2")
        is_public = db.get("PubliclyAccessible", False)
        status = db.get("DBInstanceStatus", "")
        backup_days = db.get("BackupRetentionPeriod", 0)
        tags = {t["Key"]: t["Value"] for t in db.get("TagList", [])}
        env = tags.get("Environment", tags.get("env", "")).lower()

        if status == "stopped":
            findings.append({
                "service": "rds", "region": region, "resource_id": db_id,
                "finding": "stopped_instance", "severity": "low",
                "detail": f"RDS {db_id} is stopped — auto-restarts after 7 days",
                "action": "Snapshot and delete if permanently unused",
                "estimated_monthly_savings_usd": 0,
            })
            return findings

        # ── 1. Graviton ARM migration ─────────────────────────────
        findings.extend(self._check_graviton(db_id, db_class, engine, region))

        # ── 2. Right-sizing (CPU + connection utilization) ────────
        findings.extend(self._check_rightsize(db_id, db_class, engine, region, cw))

        # ── 3. Aurora migration ───────────────────────────────────
        findings.extend(self._check_aurora(db_id, db_class, engine, region, multi_az))

        # ── 4. Multi-AZ review ────────────────────────────────────
        findings.extend(self._check_multiaz(db_id, db_class, engine, region, multi_az, env))

        # ── 5. Storage optimization ───────────────────────────────
        findings.extend(self._check_storage(db_id, storage_gb, storage_type, region))

        # ── 6. Backup optimization ────────────────────────────────
        findings.extend(self._check_backup(db_id, backup_days, region))

        # ── 7. Reserved Instance planning ─────────────────────────
        findings.extend(self._check_ri(db_id, db_class, engine, region))

        # ── 8. Public accessibility ───────────────────────────────
        findings.extend(self._check_public(db_id, is_public, region))

        # ── 9. Engine version ─────────────────────────────────────
        findings.extend(self._check_engine_version(db, engine, region))

        return findings

    # ── Graviton (ARM) migration ──────────────────────────────────────

    def _check_graviton(
        self, db_id: str, db_class: str, engine: str, region: str
    ) -> list[dict[str, Any]]:
        if db_class not in RDS_GRAVITON_MAP:
            return []

        # Some engines don't support Graviton well (SQL Server, Oracle)
        unsupported = {"sqlserver", "oracle"}
        if any(engine.startswith(u) for u in unsupported):
            return []

        graviton_class, savings_pct = RDS_GRAVITON_MAP[db_class]
        hourly = RDS_HOURLY.get(db_class, 0.20)
        grav_hourly = RDS_HOURLY.get(graviton_class, hourly * 0.85)
        monthly_saving = round((hourly - grav_hourly) * 730, 2)

        if monthly_saving < 1:
            return []

        return [{
            "service": "rds", "region": region, "resource_id": db_id,
            "finding": "graviton_migration",
            "severity": "high" if monthly_saving > 30 else "medium",
            "instance_type": db_class,
            "recommended_type": graviton_class,
            "chip_architecture": "x86 → ARM (Graviton)",
            "savings_pct": round(savings_pct, 1),
            "detail": (
                f"RDS {db_id}: {db_class} → {graviton_class} (Graviton ARM) "
                f"– {savings_pct:.0f}% cheaper (${monthly_saving:.2f}/mo)"
            ),
            "action": (
                f"Modify to {graviton_class}. Compatible with MySQL/PostgreSQL/MariaDB. "
                f"Take snapshot, restore to Graviton instance."
            ),
            "estimated_monthly_savings_usd": monthly_saving,
        }]

    # ── Right-sizing ──────────────────────────────────────────────────

    def _check_rightsize(
        self, db_id: str, db_class: str, engine: str, region: str, cw
    ) -> list[dict[str, Any]]:
        """Check if DB is over-provisioned using CloudWatch metrics."""
        # Get CPU utilization (7 days)
        cpu = self._get_metric(cw, "AWS/RDS", "CPUUtilization",
                               "DBInstanceIdentifier", db_id, 7)

        # Get database connections
        conns = self._get_metric(cw, "AWS/RDS", "DatabaseConnections",
                                 "DBInstanceIdentifier", db_id, 7)

        # Only flag if both CPU and connections are low
        if not cpu or cpu > 30:
            return []

        # Determine if downsizing makes sense
        downsizes = {
            "db.m6i.xlarge": ("db.m6i.large", 0.50),
            "db.m6i.2xlarge": ("db.m6i.xlarge", 0.50),
            "db.m6i.4xlarge": ("db.m6i.2xlarge", 0.50),
            "db.m5.xlarge": ("db.m5.large", 0.50),
            "db.m5.2xlarge": ("db.m5.xlarge", 0.50),
            "db.r6i.xlarge": ("db.r6i.large", 0.50),
            "db.r6i.2xlarge": ("db.r6i.xlarge", 0.50),
            "db.r5.xlarge": ("db.r5.large", 0.50),
            "db.r5.2xlarge": ("db.r5.xlarge", 0.50),
            "db.m7g.xlarge": ("db.m7g.large", 0.50),
            "db.m7g.2xlarge": ("db.m7g.xlarge", 0.50),
            "db.r7g.xlarge": ("db.r7g.large", 0.50),
            "db.r7g.2xlarge": ("db.r7g.xlarge", 0.50),
        }

        if db_class not in downsizes:
            return []

        smaller, ratio = downsizes[db_class]
        hourly = RDS_HOURLY.get(db_class, 0.20)
        smaller_hourly = RDS_HOURLY.get(smaller, hourly * ratio)
        monthly_saving = round((hourly - smaller_hourly) * 730, 2)

        conn_info = f", {conns:.0f} avg connections" if conns else ""

        return [{
            "service": "rds", "region": region, "resource_id": db_id,
            "finding": "right_size",
            "severity": "high" if monthly_saving > 100 else "medium",
            "instance_type": db_class,
            "recommended_type": smaller,
            "avg_cpu_pct": round(cpu, 1),
            "detail": (
                f"RDS {db_id} ({db_class}) avg CPU {cpu:.1f}%{conn_info} → {smaller}"
            ),
            "action": f"Modify to {smaller} (maintains {str(int(1/ratio))} vCPU)",
            "estimated_monthly_savings_usd": monthly_saving,
        }]

    # ── Aurora migration ──────────────────────────────────────────────

    def _check_aurora(
        self, db_id: str, db_class: str, engine: str, region: str, multi_az: bool
    ) -> list[dict[str, Any]]:
        """Recommend Aurora for high-availability MySQL/PostgreSQL."""
        eng = ENGINE_DETAILS.get(engine, {})

        if not eng.get("aurora_compatible"):
            return []

        # Aurora is most beneficial when Multi-AZ is already needed or DB is large
        if not multi_az:
            return []

        aurora_engine = eng["aurora_engine"]
        hourly = RDS_HOURLY.get(db_class, 0.20)
        # Aurora typically ~20% more per instance but eliminates Multi-AZ cost
        # Net: usually ~30% cheaper due to storage efficiency + no Multi-AZ doubling
        monthly_saving = round(hourly * 730 * 0.25, 2)

        if monthly_saving < 20:
            return []

        return [{
            "service": "rds", "region": region, "resource_id": db_id,
            "finding": "aurora_migration",
            "severity": "medium",
            "instance_type": db_class,
            "engine": engine,
            "detail": (
                f"RDS {db_id} ({engine}, Multi-AZ) — consider migrating to "
                f"Amazon Aurora {aurora_engine}. Faster, auto-healing storage, "
                f"no Multi-AZ surcharge."
            ),
            "action": (
                f"Use AWS DMS or pg_dump/mysqldump to migrate to Aurora {aurora_engine}. "
                f"Estimated net savings: ${monthly_saving:.0f}/mo"
            ),
            "estimated_monthly_savings_usd": monthly_saving,
        }]

    # ── Multi-AZ ─────────────────────────────────────────────────────

    def _check_multiaz(
        self, db_id: str, db_class: str, engine: str, region: str,
        multi_az: bool, env: str
    ) -> list[dict[str, Any]]:
        if not multi_az:
            return []

        hourly = RDS_HOURLY.get(db_class, 0.20)

        # Dev/test doesn't need Multi-AZ
        if env in ("dev", "test", "staging", "sandbox"):
            monthly_saving = round(hourly * 730, 2)
            return [{
                "service": "rds", "region": region, "resource_id": db_id,
                "finding": "multiaz_in_dev",
                "severity": "high",
                "detail": (
                    f"RDS {db_id} has Multi-AZ in {env} environment — "
                    f"doubles cost unnecessarily"
                ),
                "action": "Disable Multi-AZ for dev/test (saves 50%)",
                "estimated_monthly_savings_usd": monthly_saving,
            }]

        # Prod with Multi-AZ: flag as cost but note it may be justified
        return [{
            "service": "rds", "region": region, "resource_id": db_id,
            "finding": "multiaz_cost",
            "severity": "low",
            "detail": (
                f"RDS {db_id} Multi-AZ enabled: ${hourly * 730:.0f}/mo for standby. "
                f"Ensure it's warranted — Aurora eliminates Multi-AZ surcharge."
            ),
            "action": "Consider Aurora for similar HA at lower cost, or Single-AZ if HA not critical",
            "estimated_monthly_savings_usd": 0,  # Flag only, not definite savings
        }]

    # ── Storage ──────────────────────────────────────────────────────

    def _check_storage(
        self, db_id: str, storage_gb: int, storage_type: str, region: str
    ) -> list[dict[str, Any]]:
        findings = []

        # Storage type upgrade: gp2 → gp3 (20% cheaper + better perf)
        if storage_type == "gp2":
            # gp2: $0.115/GB-mo, gp3: $0.08/GB-mo + baseline 3000 IOPS free
            monthly_saving = round(storage_gb * (0.115 - 0.08), 2)
            if monthly_saving > 5:
                findings.append({
                    "service": "rds", "region": region, "resource_id": db_id,
                    "finding": "gp2_to_gp3",
                    "severity": "medium",
                    "detail": (
                        f"RDS {db_id}: {storage_gb}GB on gp2. gp3 is 30% cheaper "
                        f"+ 3000 free IOPS baseline."
                    ),
                    "action": f"Modify storage to gp3. Saves ~${monthly_saving:.0f}/mo.",
                    "estimated_monthly_savings_usd": monthly_saving,
                })

        # Over-provisioned storage
        if storage_gb >= 1000:
            findings.append({
                "service": "rds", "region": region, "resource_id": db_id,
                "finding": "large_storage",
                "severity": "low",
                "detail": f"RDS {db_id}: {storage_gb}GB allocated. Review actual usage.",
                "action": "Check CloudWatch FreeStorageSpace; reduce allocation if <50% used",
                "estimated_monthly_savings_usd": round(storage_gb * 0.02, 2),
            })

        return findings

    # ── Backup ───────────────────────────────────────────────────────

    def _check_backup(
        self, db_id: str, backup_days: int, region: str
    ) -> list[dict[str, Any]]:
        findings = []

        if backup_days == 0:
            findings.append({
                "service": "rds", "region": region, "resource_id": db_id,
                "finding": "no_backups",
                "severity": "high",
                "detail": f"RDS {db_id} has automated backups DISABLED — data loss risk",
                "action": "Enable automated backups (7-day minimum). Free up to 100% of storage.",
                "estimated_monthly_savings_usd": 0,  # Governance, not cost
            })
        elif backup_days > 14:
            # Long backup retention costs money
            findings.append({
                "service": "rds", "region": region, "resource_id": db_id,
                "finding": "long_backup_retention",
                "severity": "low",
                "detail": f"RDS {db_id}: {backup_days}-day backup retention — each extra day costs",
                "action": "Consider reducing to 7 days if snapshots cover long-term retention",
                "estimated_monthly_savings_usd": round((backup_days - 7) * 2.50, 2),
            })

        return findings

    # ── Reserved Instance ─────────────────────────────────────────────

    def _check_ri(
        self, db_id: str, db_class: str, engine: str, region: str
    ) -> list[dict[str, Any]]:
        hourly = RDS_HOURLY.get(db_class, 0.15)
        monthly = hourly * 730

        if monthly < 50:
            return []

        ri_savings = round(monthly * 0.35, 2)
        return [{
            "service": "rds", "region": region, "resource_id": db_id,
            "finding": "ri_candidate",
            "severity": "medium",
            "instance_type": db_class,
            "detail": (
                f"RDS {db_id} ({db_class}): ~${monthly:.0f}/mo on-demand. "
                f"1-year RI saves ~35% (${ri_savings:.0f}/mo)"
            ),
            "action": f"Purchase 1-year RDS RI for {db_class} in {region}",
            "estimated_monthly_savings_usd": ri_savings,
        }]

    # ── Public accessibility ──────────────────────────────────────────

    def _check_public(
        self, db_id: str, is_public: bool, region: str
    ) -> list[dict[str, Any]]:
        if not is_public:
            return []

        return [{
            "service": "rds", "region": region, "resource_id": db_id,
            "finding": "publicly_accessible",
            "severity": "high",
            "detail": f"RDS {db_id} is publicly accessible — security risk + data transfer cost",
            "action": "Restrict to VPC only unless internet access is absolutely required",
            "estimated_monthly_savings_usd": 0,  # Security, not direct cost
        }]

    # ── Engine version ────────────────────────────────────────────────

    def _check_engine_version(
        self, db: dict, engine: str, region: str
    ) -> list[dict[str, Any]]:
        """Flag old engine versions that may have higher cost or missing features."""
        version = db.get("EngineVersion", "")

        # Old MySQL/MariaDB/PostgreSQL versions
        old_patterns = {
            "mysql": ["5.7", "8.0.2"],
            "postgres": ["9.", "10.", "11.", "12."],
            "mariadb": ["10.3", "10.4", "10.5"],
        }

        eng_base = engine.split("-")[0] if "-" in engine else engine
        patterns = old_patterns.get(eng_base, [])

        if any(version.startswith(p) for p in patterns):
            return [{
                "service": "rds", "region": region, "resource_id": db["DBInstanceIdentifier"],
                "finding": "old_engine_version",
                "severity": "low",
                "detail": f"RDS {db['DBInstanceIdentifier']}: {engine} {version} is old — newer versions are faster and cheaper",
                "action": f"Upgrade to latest {engine} version. Newer engines use resources more efficiently.",
                "estimated_monthly_savings_usd": 5.00,
            }]

        return []

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_metric(
        self, cw, namespace: str, metric: str, dim_name: str, dim_value: str, days: int
    ) -> float | None:
        """Get average of a CloudWatch metric over N days."""
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
