"""
Cost Anomaly Detection — detect unusual spikes in cloud spending.

Uses simple statistical methods (Z-score, moving average) to flag anomalies
without requiring ML dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnomalyDetector:
    """Detect cost anomalies using statistical methods.

    Works with daily cost data to identify unusual spending patterns.
    """

    zscore_threshold: float = 2.0
    """Z-score threshold for flagging anomalies. Default 2.0 (95th percentile)."""

    moving_avg_window: int = 7
    """Window size for moving average comparison."""

    min_daily_cost: float = 10.0
    """Minimum daily cost to consider — filters noise."""

    def detect(self, daily_costs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect anomalies in a time series of daily costs.

        Args:
            daily_costs: List of {"date": "2025-01-01", "cost": 123.45, "service": "ec2"} dicts.

        Returns:
            List of anomaly findings with severity and detail.
        """
        if len(daily_costs) < self.moving_avg_window:
            return []

        costs = [d["cost"] for d in daily_costs]
        anomalies = []

        # Z-score detection
        mean_cost = sum(costs) / len(costs)
        std_cost = self._stddev(costs, mean_cost)

        if std_cost > 0:
            for i, d in enumerate(daily_costs):
                z_score = (d["cost"] - mean_cost) / std_cost
                if abs(z_score) > self.zscore_threshold and d["cost"] > self.min_daily_cost:
                    anomalies.append({
                        "date": d["date"],
                        "service": d.get("service", "unknown"),
                        "cost": d["cost"],
                        "expected_cost": round(mean_cost, 2),
                        "z_score": round(z_score, 2),
                        "method": "zscore",
                        "direction": "spike" if z_score > 0 else "drop",
                        "detail": (
                            f"Cost {d['service']} on {d['date']}: "
                            f"${d['cost']:.2f} vs avg ${mean_cost:.2f} "
                            f"(z={z_score:.1f})"
                        ),
                    })

        # Moving average detection (for the tail end)
        for i in range(self.moving_avg_window, len(daily_costs)):
            window = costs[i - self.moving_avg_window:i]
            ma = sum(window) / len(window)
            current = costs[i]

            if ma > 0 and current > self.min_daily_cost:
                ratio = current / ma
                if ratio > 1.5:  # 50% above moving average
                    already_flagged = any(
                        a["date"] == daily_costs[i]["date"]
                        and a["service"] == daily_costs[i].get("service", "")
                        for a in anomalies
                    )
                    if not already_flagged:
                        anomalies.append({
                            "date": daily_costs[i]["date"],
                            "service": daily_costs[i].get("service", "unknown"),
                            "cost": current,
                            "expected_cost": round(ma, 2),
                            "ratio": round(ratio, 2),
                            "method": "moving_avg",
                            "direction": "spike",
                            "detail": (
                                f"Cost {daily_costs[i].get('service','')} on {daily_costs[i]['date']}: "
                                f"${current:.2f} is {ratio:.1f}x the {self.moving_avg_window}-day avg (${ma:.2f})"
                            ),
                        })

        # Add estimated monthly savings (cost of anomaly — should investigate)
        for a in anomalies:
            if a["direction"] == "spike":
                a["estimated_monthly_savings_usd"] = round(
                    (a["cost"] - a["expected_cost"]), 2
                )
            else:
                a["estimated_monthly_savings_usd"] = 0
            a["severity"] = "high" if a.get("z_score", 0) > 3 or a.get("ratio", 0) > 3 else "medium"
            a["finding"] = f"cost_{a['direction']}"

        return sorted(anomalies, key=lambda x: x.get("estimated_monthly_savings_usd", 0), reverse=True)

    def generate_daily_costs(
        self,
        monthly_cost: float,
        services: list[str] | None = None,
        days: int = 30,
        anomaly_days: list[int] | None = None,
        anomaly_multiplier: float = 3.0,
    ) -> list[dict[str, Any]]:
        """Generate synthetic daily cost data for testing.

        Args:
            monthly_cost: Total monthly cost to distribute.
            services: List of service names.
            days: Number of days.
            anomaly_days: Day indices (0-based) to inject anomalies.
            anomaly_multiplier: Multiplier for anomaly days.
        """
        from datetime import datetime, timedelta
        import random

        services = services or ["ec2", "rds", "s3", "lambda", "elasticache"]
        daily_avg = monthly_cost / days
        anomaly_days = anomaly_days or []

        data = []
        base = datetime.now() - timedelta(days=days)

        for i in range(days):
            date = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            for svc in services:
                cost = daily_avg / len(services) * random.uniform(0.7, 1.3)
                if i in anomaly_days and svc == services[0]:
                    cost *= anomaly_multiplier
                data.append({
                    "date": date,
                    "service": svc,
                    "cost": round(cost, 2),
                })

        return data

    @staticmethod
    def _stddev(values: list[float], mean: float) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return variance ** 0.5
