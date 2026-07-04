"""
CloudCost CLI — unified multi-cloud cost optimization tool.

Usage:
    cloudcost aws scan
    cloudcost aliyun scan
    cloudcost dashboard
    cloudcost report --format html
"""

import sys
from pathlib import Path

import click

from cloudcost import __version__


@click.group()
@click.version_option(version=__version__, prog_name="cloudcost")
@click.pass_context
def main(ctx: click.Context) -> None:
    """CloudCost — Multi-cloud FinOps & Cost Optimization.

    Find waste, right-size resources, and save money on AWS and Alibaba Cloud.
    """
    ctx.ensure_object(dict)


# ── AWS Commands ──────────────────────────────────────────────────


@main.group()
def aws() -> None:
    """AWS cost analysis and optimization."""
    pass


@aws.command()
@click.option("--region", "-r", multiple=True, help="AWS region(s) to scan")
@click.option("--service", "-s", multiple=True, help="Service filter (ec2, rds, s3, etc.)")
@click.option("--days", default=30, help="Look-back period in days")
@click.option("--output", "-o", default="table", type=click.Choice(["table", "json", "csv"]))
@click.option("--profile", help="AWS profile name")
@click.pass_context
def scan(ctx: click.Context, region: tuple, service: tuple, days: int, output: str, profile: str) -> None:
    """Full scan across AWS services for cost-saving opportunities."""
    from cloudcost.aws.scanner import AWSScanner

    scanner = AWSScanner(profile=profile, regions=list(region) if region else None)
    results = scanner.scan(
        services=list(service) if service else None,
        lookback_days=days,
    )
    _output_results(results, output)


@aws.command()
@click.option("--region", "-r", multiple=True, help="AWS region(s)")
@click.option("--right-size", is_flag=True, help="Recommend right-sizing")
@click.option("--stop-idle", is_flag=True, help="Flag idle instances for termination")
@click.option("--profile", help="AWS profile name")
@click.pass_context
def ec2(ctx: click.Context, region: tuple, right_size: bool, stop_idle: bool, profile: str) -> None:
    """EC2 instance optimization."""
    from cloudcost.aws.ec2_optimizer import EC2Optimizer

    opt = EC2Optimizer(profile=profile, regions=list(region) if region else None)
    if right_size:
        recs = opt.right_size_recommendations()
        _output_results(recs, "table")
    elif stop_idle:
        idle = opt.find_idle_instances()
        _output_results(idle, "table")
    else:
        recs = opt.analyze_all()
        _output_results(recs, "table")


@aws.command()
@click.option("--term", default="1year", type=click.Choice(["1year", "3year"]))
@click.option("--payment", default="partial-upfront", type=click.Choice(["no-upfront", "partial-upfront", "all-upfront"]))
@click.option("--profile", help="AWS profile name")
@click.pass_context
def ri_plan(ctx: click.Context, term: str, payment: str, profile: str) -> None:
    """Reserved Instance / Savings Plan purchase planner."""
    from cloudcost.aws.ri_planner import RIPlanner

    planner = RIPlanner(profile=profile)
    plan = planner.calculate(term=term, payment_option=payment)
    _output_results(plan, "table")


@aws.command()
@click.option("--analyze", is_flag=True, help="Analyze S3 storage costs")
@click.option("--lifecycle", is_flag=True, help="Suggest lifecycle policies")
@click.option("--profile", help="AWS profile name")
@click.pass_context
def s3(ctx: click.Context, analyze: bool, lifecycle: bool, profile: str) -> None:
    """S3 storage analysis and lifecycle recommendations."""
    from cloudcost.aws.s3_analyzer import S3Analyzer

    analyzer = S3Analyzer(profile=profile)
    if lifecycle:
        policies = analyzer.lifecycle_recommendations()
        _output_results(policies, "table")
    else:
        results = analyzer.analyze()
        _output_results(results, "table")


@aws.command()
@click.option("--right-size", is_flag=True, help="Recommend RDS right-sizing")
@click.option("--profile", help="AWS profile name")
@click.pass_context
def rds(ctx: click.Context, right_size: bool, profile: str) -> None:
    """RDS database optimization."""
    from cloudcost.aws.rds_optimizer import RDSOptimizer

    opt = RDSOptimizer(profile=profile)
    recs = opt.analyze()
    _output_results(recs, "table")


# ── Alibaba Cloud Commands ────────────────────────────────────────


@main.group()
def aliyun() -> None:
    """Alibaba Cloud (Aliyun) cost analysis and optimization."""
    pass


@aliyun.command()
@click.option("--region", "-r", multiple=True, help="Alibaba Cloud region(s)")
@click.option("--service", "-s", multiple=True, help="Service filter (ecs, rds, oss, etc.)")
@click.option("--days", default=30, help="Look-back period in days")
@click.option("--output", "-o", default="table", type=click.Choice(["table", "json", "csv"]))
@click.pass_context
def scan(ctx: click.Context, region: tuple, service: tuple, days: int, output: str) -> None:
    """Full scan across Alibaba Cloud services for cost-saving opportunities."""
    from cloudcost.aliyun.scanner import AliyunScanner

    scanner = AliyunScanner(regions=list(region) if region else None)
    results = scanner.scan(
        services=list(service) if service else None,
        lookback_days=days,
    )
    _output_results(results, output)


@aliyun.command()
@click.option("--region", "-r", multiple=True, help="Alibaba Cloud region(s)")
@click.option("--right-size", is_flag=True, help="Recommend right-sizing")
@click.option("--stop-idle", is_flag=True, help="Flag idle instances")
@click.pass_context
def ecs(ctx: click.Context, region: tuple, right_size: bool, stop_idle: bool) -> None:
    """ECS instance optimization."""
    from cloudcost.aliyun.ecs_optimizer import ECSOptimizer

    opt = ECSOptimizer(regions=list(region) if region else None)
    if right_size:
        recs = opt.right_size_recommendations()
        _output_results(recs, "table")
    elif stop_idle:
        idle = opt.find_idle_instances()
        _output_results(idle, "table")
    else:
        recs = opt.analyze_all()
        _output_results(recs, "table")


@aliyun.command()
@click.pass_context
def oss(ctx: click.Context) -> None:
    """OSS storage analysis and lifecycle recommendations."""
    from cloudcost.aliyun.oss_analyzer import OSSAnalyzer

    analyzer = OSSAnalyzer()
    results = analyzer.analyze()
    _output_results(results, "table")


# ── Dashboard ─────────────────────────────────────────────────────


@main.command()
@click.option("--host", default="127.0.0.1", help="Bind address")
@click.option("--port", default=8050, help="Bind port")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def dashboard(ctx: click.Context, host: str, port: int, debug: bool) -> None:
    """Launch the interactive web dashboard."""
    try:
        from cloudcost.dashboard.app import create_app

        app = create_app()
        click.echo(f"\n  Dashboard: http://{host}:{port}\n")
        app.run(host=host, port=port, debug=debug)
    except ImportError:
        click.echo("Dashboard requires: pip install cloudcost[dashboard]")


# ── Report ───────────────────────────────────────────────────────


@main.command()
@click.option("--format", "-f", "fmt", default="table",
              type=click.Choice(["table", "json", "csv", "html", "slack"]))
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--days", default=30, help="Look-back period in days")
@click.option("--cloud", default="all", type=click.Choice(["aws", "aliyun", "all"]))
@click.option("--slack-webhook", help="Slack webhook URL (for --format slack)")
@click.pass_context
def report(ctx: click.Context, fmt: str, output: str, days: int, cloud: str, slack_webhook: str) -> None:
    """Generate cost optimization reports."""
    from cloudcost.core.reporter import Reporter

    reporter = Reporter()
    result = reporter.generate(
        fmt=fmt,
        output=output,
        lookback_days=days,
        cloud=cloud,
        slack_webhook=slack_webhook,
    )
    if result:
        click.echo(result)


# ── Helpers ──────────────────────────────────────────────────────


def _output_results(data: list, fmt: str = "table") -> None:
    """Display results in the chosen format."""
    if not data:
        click.echo("No savings opportunities found — your cloud is in good shape! 🎉")
        return

    if fmt == "json":
        import json
        click.echo(json.dumps(data, indent=2, default=str))
    elif fmt == "csv":
        import io, csv as csv_module
        buf = io.StringIO()
        if data:
            w = csv_module.DictWriter(buf, fieldnames=data[0].keys())
            w.writeheader()
            w.writerows(data)
            click.echo(buf.getvalue())
        else:
            click.echo("")
    else:
        # Rich table
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="💰 Cost Savings Opportunities", show_header=True, header_style="bold green")
        for key in data[0]:
            table.add_column(key.replace("_", " ").title())
        for row in data:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)


if __name__ == "__main__":
    main()
