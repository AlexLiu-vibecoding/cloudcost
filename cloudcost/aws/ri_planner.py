"""
AWS Reserved Instance & Savings Plan Planner.

Calculates break-even, recommended purchases, and estimated savings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import boto3


@dataclass
class RIPlanner:
    """Analyze on-demand spend and recommend RI/Savings Plan purchases."""


    profile: str | None = None
    regions: list[str] | None = None

    def __post_init__(self):
        kwargs = {"profile_name": self.profile} if self.profile else {}
        self._session = boto3.Session(**kwargs)

        if not self.regions:
            ec2 = self._session.client("ec2", region_name="us-east-1")
            try:
                self.regions = [r["RegionName"] for r in ec2.describe_regions()["Regions"]]
            except Exception:
                self.regions = ["us-east-1", "us-west-2"]

    def calculate(
        self, term: str = "1year", payment_option: str = "partial-upfront"
    ) -> list[dict[str, Any]]:
        """Generate RI purchase recommendations.

        Without Cost Explorer API access, uses heuristics based on running instances.
        """
        recommendations = []

        # Savings factors by term and payment
        savings_factors = {
            ("1year", "no-upfront"): 0.30,
            ("1year", "partial-upfront"): 0.35,
            ("1year", "all-upfront"): 0.38,
            ("3year", "no-upfront"): 0.45,
            ("3year", "partial-upfront"): 0.50,
            ("3year", "all-upfront"): 0.55,
        }
        savings_pct = savings_factors.get((term, payment_option), 0.35)

        for region in self.regions:
            ec2 = self._session.client("ec2", region_name=region)
            try:
                instances = ec2.describe_instances(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                )
            except Exception:
                continue

            # Group by instance type
            counts: dict[str, int] = {}
            for res in instances.get("Reservations", []):
                for inst in res.get("Instances", []):
                    itype = inst.get("InstanceType", "unknown")
                    counts[itype] = counts.get(itype, 0) + 1

            from cloudcost.aws.ec2_optimizer import INSTANCE_HOURLY

            for itype, count in counts.items():
                hourly = INSTANCE_HOURLY.get(itype, 0.10)
                monthly_od = hourly * 730 * count
                monthly_saving = round(monthly_od * savings_pct, 2)

                if monthly_saving < 10:
                    continue  # Too small to matter

                recommendations.append({
                    "region": region,
                    "instance_type": itype,
                    "count": count,
                    "term": term,
                    "payment": payment_option,
                    "monthly_on_demand_usd": round(monthly_od, 2),
                    "monthly_ri_usd": round(monthly_od * (1 - savings_pct), 2),
                    "estimated_monthly_savings_usd": monthly_saving,
                    "estimated_annual_savings_usd": round(monthly_saving * 12, 2),
                    "break_even_months": _break_even(term, payment_option),
                    "recommendation": "BUY" if monthly_saving > 50 else "REVIEW",
                    "detail": (
                        f"Buy {count}x {itype} RI ({term}, {payment_option}): "
                        f"save ${monthly_saving}/month, ${monthly_saving * 12}/year"
                    ),
                })

        return sorted(
            recommendations,
            key=lambda x: x.get("estimated_monthly_savings_usd", 0),
            reverse=True,
        )


def _break_even(term: str, payment: str) -> int:
    """Approximate break-even months for RI purchase."""
    break_evens = {
        ("1year", "no-upfront"): 1,
        ("1year", "partial-upfront"): 3,
        ("1year", "all-upfront"): 5,
        ("3year", "no-upfront"): 1,
        ("3year", "partial-upfront"): 6,
        ("3year", "all-upfront"): 9,
    }
    return break_evens.get((term, payment), 3)
