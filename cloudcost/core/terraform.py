"""
Terraform Cost Estimator — estimate cloud costs from Terraform plans.

Parses terraform plan JSON and estimates monthly costs for AWS and Alibaba Cloud
resources before they're deployed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# AWS resource cost estimates (monthly, us-east-1, on-demand, simplified)
AWS_COSTS = {
    "aws_instance": {
        "t3.micro": 7.59, "t3.small": 15.18, "t3.medium": 30.37,
        "t3.large": 60.74, "t3.xlarge": 121.47, "t3.2xlarge": 242.94,
        "m6i.large": 70.08, "m6i.xlarge": 140.16, "m6i.2xlarge": 280.32,
        "c6i.large": 62.05, "c6i.xlarge": 124.10,
        "r6i.large": 91.98, "r6i.xlarge": 183.96,
    },
    "aws_db_instance": {
        "db.t3.micro": 12.41, "db.t3.small": 24.82, "db.t3.medium": 49.64,
        "db.t3.large": 99.28, "db.r6i.large": 184.69, "db.r6i.xlarge": 369.38,
    },
    "aws_s3_bucket": 0.023,  # per GB (estimate 100GB)
    "aws_lb": 22.27,
    "aws_nat_gateway": 32.85,
    "aws_eip": 3.65,  # idle EIP
    "aws_ebs_volume": 0.08,  # per GB
    "aws_elasticache_cluster": {
        "cache.t3.micro": 12.41, "cache.t3.medium": 49.64, "cache.m6g.large": 96.36,
    },
    "aws_lambda_function": 0.00,  # pay-per-use, hard to estimate
}

# Alibaba Cloud costs (monthly, CNY, pay-as-you-go)
ALIYUN_COSTS_CNY = {
    "alicloud_instance": {
        "ecs.g7.large": 350, "ecs.g7.xlarge": 701, "ecs.g7.2xlarge": 1402,
        "ecs.c7.large": 307, "ecs.c7.xlarge": 620,
        "ecs.r7.large": 460, "ecs.r7.xlarge": 920,
    },
    "alicloud_db_instance": {
        "mysql.n4.large": 440, "mysql.n4.xlarge": 880,
    },
    "alicloud_oss_bucket": 0.12,  # per GB (CNY)
    "alicloud_slb": 11.7,  # CNY
    "alicloud_nat_gateway": 200,  # CNY
    "alicloud_eip": 14.4,  # CNY per idle EIP
    "alicloud_disk": 0.35,  # per GB (CNY)
}

CNY_TO_USD = 0.14


class TerraformEstimator:
    """Estimate monthly cloud costs from Terraform plan JSON."""


    def estimate_plan(self, plan_path: str | Path) -> list[dict[str, Any]]:
        """Parse a Terraform plan JSON and estimate monthly costs.

        Args:
            plan_path: Path to terraform plan JSON file.
                       Generate with: terraform show -json tfplan > plan.json

        Returns:
            List of resource cost estimates.
        """
        plan = json.loads(Path(plan_path).read_text())

        resources = []
        # Handle different plan formats
        if "resource_changes" in plan:
            changes = plan["resource_changes"]
        elif "planned_values" in plan:
            changes = []
            for res in plan["planned_values"].get("root_module", {}).get("resources", []):
                changes.append({"type": res["type"], "name": res["name"],
                               "change": {"actions": ["create"],
                                         "after": res.get("values", {})}})
        else:
            return [{"error": "Unsupported plan format. Use 'terraform show -json'"}]

        for change in changes:
            res_type = change.get("type", "")
            res_name = change.get("name", "")
            actions = change.get("change", {}).get("actions", [])
            after = change.get("change", {}).get("after", {}) or {}

            if "create" not in actions and "update" not in actions:
                continue

            cost_info = self._estimate_resource(res_type, res_name, after)
            if cost_info:
                resources.append(cost_info)

        return resources

    def _estimate_resource(
        self, res_type: str, name: str, attrs: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Estimate cost for a single Terraform resource."""
        monthly_usd = 0.0

        if res_type == "aws_instance":
            itype = attrs.get("instance_type", "t3.micro")
            count = self._get_count(attrs)
            monthly_usd = AWS_COSTS.get("aws_instance", {}).get(itype, 70.0) * count

        elif res_type == "aws_db_instance":
            itype = attrs.get("instance_class", "db.t3.micro")
            monthly_usd = AWS_COSTS.get("aws_db_instance", {}).get(itype, 50.0)

        elif res_type == "aws_s3_bucket":
            monthly_usd = AWS_COSTS["aws_s3_bucket"] * 100  # assume 100GB

        elif res_type in ("aws_lb", "aws_alb", "aws_nlb"):
            monthly_usd = AWS_COSTS["aws_lb"]

        elif res_type == "aws_nat_gateway":
            monthly_usd = AWS_COSTS["aws_nat_gateway"]

        elif res_type == "aws_eip":
            monthly_usd = AWS_COSTS["aws_eip"]

        elif res_type == "aws_ebs_volume":
            size_gb = attrs.get("size", 20)
            monthly_usd = size_gb * AWS_COSTS["aws_ebs_volume"]

        elif res_type == "aws_elasticache_cluster":
            ntype = attrs.get("node_type", "cache.t3.micro")
            monthly_usd = AWS_COSTS.get("aws_elasticache_cluster", {}).get(ntype, 50.0)

        elif res_type == "aws_lambda_function":
            # Hard to estimate without invocation count, flag for review
            return {
                "resource_type": res_type,
                "resource_name": name,
                "estimated_monthly_cost_usd": 0.0,
                "cost_model": "pay_per_use",
                "detail": f"Lambda '{name}' uses pay-per-use pricing — estimate based on expected invocations",
                "recommendation": "Set up budget alerts for Lambda costs",
            }

        # ── Alibaba Cloud ──────────────────────────────────────
        elif res_type == "alicloud_instance":
            itype = attrs.get("instance_type", "ecs.g7.large")
            count = self._get_count(attrs)
            monthly_cny = ALIYUN_COSTS_CNY.get("alicloud_instance", {}).get(itype, 350) * count
            monthly_usd = monthly_cny * CNY_TO_USD

        elif res_type == "alicloud_db_instance":
            itype = attrs.get("instance_type", "mysql.n4.large")
            monthly_cny = ALIYUN_COSTS_CNY.get("alicloud_db_instance", {}).get(itype, 440)
            monthly_usd = monthly_cny * CNY_TO_USD

        elif res_type == "alicloud_oss_bucket":
            monthly_cny = ALIYUN_COSTS_CNY["alicloud_oss_bucket"] * 100
            monthly_usd = monthly_cny * CNY_TO_USD

        elif res_type == "alicloud_slb":
            monthly_usd = ALIYUN_COSTS_CNY["alicloud_slb"] * CNY_TO_USD

        elif res_type == "alicloud_nat_gateway":
            monthly_usd = ALIYUN_COSTS_CNY["alicloud_nat_gateway"] * CNY_TO_USD

        elif res_type == "alicloud_eip":
            monthly_usd = ALIYUN_COSTS_CNY["alicloud_eip"] * CNY_TO_USD

        elif res_type == "alicloud_disk":
            size_gb = attrs.get("size", 20)
            monthly_usd = size_gb * ALIYUN_COSTS_CNY["alicloud_disk"] * CNY_TO_USD

        else:
            return None

        return {
            "resource_type": res_type,
            "resource_name": name,
            "estimated_monthly_cost_usd": round(monthly_usd, 2),
            "estimated_annual_cost_usd": round(monthly_usd * 12, 2),
            "detail": f"{res_type}.{name}: ~${monthly_usd:.2f}/month",
        }

    @staticmethod
    def _get_count(attrs: dict) -> int:
        """Get resource count from Terraform attributes."""
        count = attrs.get("count", 1)
        if isinstance(count, dict):
            count = 1  # dynamic count, can't determine
        return int(count)

    def summarize(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate a summary from estimated resources."""
        total = sum(r.get("estimated_monthly_cost_usd", 0) for r in resources)
        by_type: dict[str, float] = {}
        for r in resources:
            rtype = r.get("resource_type", "unknown")
            by_type[rtype] = by_type.get(rtype, 0) + r.get("estimated_monthly_cost_usd", 0)

        return {
            "total_monthly_usd": round(total, 2),
            "total_annual_usd": round(total * 12, 2),
            "resource_count": len(resources),
            "by_type": by_type,
            "resources": resources,
        }
