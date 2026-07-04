"""
Report generator — JSON, CSV, HTML, and Slack output formats.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import urllib.request
from pathlib import Path
from typing import Any

from cloudcost.aws.scanner import AWSScanner
from cloudcost.aliyun.scanner import AliyunScanner


class Reporter:
    """Generate cost optimization reports in multiple formats."""


    def generate(
        self,
        fmt: str = "table",
        output: str | None = None,
        lookback_days: int = 30,
        cloud: str = "all",
        slack_webhook: str | None = None,
    ) -> str | None:
        """Generate a report in the requested format."""
        findings: list[dict[str, Any]] = []

        if cloud in ("aws", "all"):
            try:
                aws = AWSScanner()
                findings.extend(aws.scan(lookback_days=lookback_days))
            except Exception as e:
                findings.append({
                    "service": "aws",
                    "finding": "scan_error",
                    "severity": "error",
                    "detail": f"AWS scan failed: {e}",
                    "estimated_monthly_savings_usd": 0,
                })

        if cloud in ("aliyun", "all"):
            try:
                aliyun = AliyunScanner()
                findings.extend(aliyun.scan(lookback_days=lookback_days))
            except Exception as e:
                findings.append({
                    "service": "aliyun",
                    "finding": "scan_error",
                    "severity": "error",
                    "detail": f"Alibaba Cloud scan failed: {e}",
                    "estimated_monthly_savings_usd": 0,
                })

        # Sort by savings
        findings.sort(key=lambda x: x.get("estimated_monthly_savings_usd", 0), reverse=True)

        # Generate output
        if fmt == "json":
            return self._json_report(findings, output)
        elif fmt == "csv":
            return self._csv_report(findings, output)
        elif fmt == "html":
            return self._html_report(findings, output, lookback_days)
        elif fmt == "slack":
            return self._slack_report(findings, slack_webhook)
        else:
            return self._table_summary(findings)

    def _json_report(self, findings: list[dict], output: str | None = None) -> str:
        """Generate JSON report."""
        report = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_findings": len(findings),
            "total_estimated_monthly_savings_usd": round(
                sum(f.get("estimated_monthly_savings_usd", 0) for f in findings), 2
            ),
            "total_estimated_annual_savings_usd": round(
                sum(f.get("estimated_monthly_savings_usd", 0) for f in findings) * 12, 2
            ),
            "findings": findings,
        }
        content = json.dumps(report, indent=2, default=str)
        if output:
            Path(output).write_text(content)
            return f"Report saved to {output}"
        return content

    def _csv_report(self, findings: list[dict], output: str | None = None) -> str:
        """Generate CSV report."""
        if not findings:
            return "No findings to report."

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=findings[0].keys())
        writer.writeheader()
        writer.writerows(findings)
        content = buf.getvalue()

        if output:
            Path(output).write_text(content)
            return f"Report saved to {output}"
        return content

    def _html_report(self, findings: list[dict], output: str | None, lookback_days: int) -> str:
        """Generate HTML report with embedded styling."""
        total_savings = sum(f.get("estimated_monthly_savings_usd", 0) for f in findings)

        severity_colors = {
            "high": "#dc3545",
            "medium": "#fd7e14",
            "low": "#ffc107",
            "info": "#17a2b8",
            "error": "#dc3545",
        }

        rows_html = ""
        for f in findings:
            sev = f.get("severity", "low")
            color = severity_colors.get(sev, "#6c757d")
            rows_html += f"""
            <tr>
                <td><span class="badge" style="background:{color}">{sev.upper()}</span></td>
                <td>{f.get('service', '')}</td>
                <td>{f.get('region', '')}</td>
                <td>{f.get('resource_id', '')}</td>
                <td>{f.get('finding', '')}</td>
                <td>{f.get('detail', '')}</td>
                <td style="text-align:right">${f.get('estimated_monthly_savings_usd', 0):,.2f}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CloudCost Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f8f9fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #212529; border-bottom: 3px solid #0d6efd; padding-bottom: 10px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .card {{ flex: 1; padding: 20px; border-radius: 8px; color: white; }}
        .card.green {{ background: linear-gradient(135deg, #28a745, #20c997); }}
        .card.blue {{ background: linear-gradient(135deg, #0d6efd, #6610f2); }}
        .card h2 {{ margin: 0; font-size: 14px; opacity: 0.9; }}
        .card .number {{ font-size: 28px; font-weight: bold; margin: 5px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ background: #f1f3f5; padding: 12px; text-align: left; font-weight: 600; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #e9ecef; }}
        tr:hover {{ background: #f8f9fa; }}
        .badge {{ padding: 3px 8px; border-radius: 4px; color: white; font-size: 11px; font-weight: bold; }}
        .footer {{ margin-top: 30px; color: #6c757d; font-size: 12px; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>💰 CloudCost Optimization Report</h1>
        <p>Generated: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Look-back: {lookback_days} days</p>

        <div class="summary">
            <div class="card green">
                <h2>Monthly Savings</h2>
                <div class="number">${total_savings:,.2f}</div>
            </div>
            <div class="card blue">
                <h2>Annual Savings</h2>
                <div class="number">${total_savings * 12:,.2f}</div>
            </div>
            <div class="card" style="background: linear-gradient(135deg, #fd7e14, #e8590c);">
                <h2>Findings</h2>
                <div class="number">{len(findings)}</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Severity</th>
                    <th>Service</th>
                    <th>Region</th>
                    <th>Resource</th>
                    <th>Finding</th>
                    <th>Detail</th>
                    <th style="text-align:right">Monthly Savings</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <div class="footer">CloudCost v0.1.0 — Multi-cloud FinOps</div>
    </div>
</body>
</html>"""
        if output:
            Path(output).write_text(html)
            return f"Report saved to {output}"
        return html

    def _slack_report(self, findings: list[dict], webhook: str | None) -> str:
        """Send report to Slack webhook."""
        if not webhook:
            return "Error: --slack-webhook is required for Slack format"

        total_savings = sum(f.get("estimated_monthly_savings_usd", 0) for f in findings)
        high_severity = [f for f in findings if f.get("severity") == "high"]
        medium_severity = [f for f in findings if f.get("severity") == "medium"]

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "💰 CloudCost Optimization Report", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Monthly Savings:*\n${total_savings:,.2f}"},
                    {"type": "mrkdwn", "text": f"*Annual Savings:*\n${total_savings * 12:,.2f}"},
                    {"type": "mrkdwn", "text": f"*Total Findings:*\n{len(findings)}"},
                    {"type": "mrkdwn", "text": f"*High Severity:*\n{len(high_severity)}"},
                ],
            },
        ]

        if high_severity:
            text = "*🔴 High Priority:*\n" + "\n".join(
                f"• {f.get('service', '')}/{f.get('region', '')}: {f.get('detail', '')} (${f.get('estimated_monthly_savings_usd', 0):.2f}/mo)"
                for f in high_severity[:5]
            )
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})

        if medium_severity:
            text = "*🟡 Medium Priority:*\n" + "\n".join(
                f"• {f.get('service', '')}: {f.get('detail', '')}"
                for f in medium_severity[:3]
            )
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})

        payload = json.dumps({"blocks": blocks}).encode("utf-8")
        try:
            req = urllib.request.Request(
                webhook,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            return f"Slack report sent to webhook ({len(findings)} findings, ${total_savings:,.2f}/mo savings)"
        except Exception as e:
            return f"Failed to send Slack report: {e}"

    def _table_summary(self, findings: list[dict]) -> str:
        """Generate a text summary."""
        if not findings:
            return "🎉 No savings opportunities found — your cloud is in great shape!"

        total = sum(f.get("estimated_monthly_savings_usd", 0) for f in findings)
        high = [f for f in findings if f.get("severity") == "high"]
        medium = [f for f in findings if f.get("severity") == "medium"]

        lines = [
            "=" * 70,
            "  CloudCost Optimization Report",
            "=" * 70,
            f"  Findings: {len(findings)}  |  Monthly savings: ${total:,.2f}  |  Annual: ${total * 12:,.2f}",
            f"  High: {len(high)}  |  Medium: {len(medium)}  |  Low: {len(findings) - len(high) - len(medium)}",
            "-" * 70,
        ]

        for f in findings[:10]:
            sev = f.get("severity", "low")
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "ℹ️"}.get(sev, "⚪")
            lines.append(
                f"  {emoji} [{f.get('service', '?')}] {f.get('detail', 'No details')[:80]}"
            )
            if f.get("estimated_monthly_savings_usd", 0) > 0:
                lines[-1] += f"  → ${f['estimated_monthly_savings_usd']:,.2f}/mo"

        if len(findings) > 10:
            lines.append(f"  ... and {len(findings) - 10} more findings")

        lines.append("-" * 70)
        lines.append("  Run with --output html for a detailed dashboard")
        lines.append("=" * 70)

        return "\n".join(lines)
