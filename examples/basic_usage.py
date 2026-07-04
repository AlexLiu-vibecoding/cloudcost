"""CloudCost usage examples."""

# ── AWS Examples ────────────────────────────────────────────────

def aws_scan_example():
    """Basic AWS cost scan."""
    from cloudcost.aws.scanner import AWSScanner

    scanner = AWSScanner()
    findings = scanner.scan(services=["ec2", "s3", "ebs"])
    print(f"Found {len(findings)} savings opportunities")
    for f in findings[:5]:
        print(f"  {f['severity']:8s} | {f['service']:5s} | {f['detail'][:60]}")


def ec2_rightsize_example():
    """EC2 right-sizing."""
    from cloudcost.aws.ec2_optimizer import EC2Optimizer

    opt = EC2Optimizer()
    recs = opt.right_size_recommendations()
    for r in recs:
        print(f"  {r['resource_id']}: {r['instance_type']} → {r['recommended_type']} "
              f"(save ${r['estimated_monthly_savings_usd']:.2f}/mo)")


def ri_planning_example():
    """Reserved Instance purchase planning."""
    from cloudcost.aws.ri_planner import RIPlanner

    planner = RIPlanner()
    plan = planner.calculate(term="1year", payment_option="partial-upfront")
    for p in plan[:5]:
        print(f"  {p['region']}: {p['instance_type']} x{p['count']} — "
              f"save ${p['estimated_monthly_savings_usd']:.2f}/mo "
              f"({p['recommendation']})")


# ── Alibaba Cloud Examples ──────────────────────────────────────

def aliyun_scan_example():
    """Alibaba Cloud cost scan."""
    from cloudcost.aliyun.scanner import AliyunScanner

    scanner = AliyunScanner(regions=["cn-hangzhou", "cn-shanghai"])
    findings = scanner.scan()
    print(f"Found {len(findings)} savings opportunities")
    for f in findings:
        print(f"  {f['severity']:8s} | {f['service']:5s} | {f['detail'][:60]}")


def oss_lifecycle_example():
    """OSS lifecycle policy recommendations."""
    from cloudcost.aliyun.oss_analyzer import OSSAnalyzer

    analyzer = OSSAnalyzer()
    findings = analyzer.analyze()
    for f in findings:
        print(f"  {f['finding']}: {f['detail'][:80]}")


def ecs_upgrade_example():
    """ECS generation upgrade recommendations."""
    from cloudcost.aliyun.ecs_optimizer import ECSOptimizer

    opt = ECSOptimizer()
    findings = opt.analyze_all()
    for f in findings:
        if f.get("estimated_monthly_savings_usd", 0) > 0:
            print(f"  {f['detail'][:80]}")


# ── Report Generation ───────────────────────────────────────────

def html_report_example():
    """Generate an HTML report."""
    from cloudcost.core.reporter import Reporter

    reporter = Reporter()
    html = reporter.generate(fmt="html", cloud="all")
    with open("/tmp/cloudcost_report.html", "w") as f:
        f.write(html)
    print("HTML report saved to /tmp/cloudcost_report.html")


def slack_report_example():
    """Send report to Slack."""
    from cloudcost.core.reporter import Reporter

    reporter = Reporter()
    # Uncomment and add your webhook:
    # result = reporter.generate(
    #     fmt="slack",
    #     slack_webhook="https://hooks.slack.com/services/...",
    # )
    # print(result)
    print("Slack report: set --slack-webhook to your webhook URL")


# ── Run examples ────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== AWS EC2 Right-sizing ===")
    ec2_rightsize_example()

    print("\n=== AWS RI Planning ===")
    ri_planning_example()

    print("\n=== Alibaba Cloud OSS Lifecycle ===")
    oss_lifecycle_example()

    print("\n=== HTML Report ===")
    html_report_example()
