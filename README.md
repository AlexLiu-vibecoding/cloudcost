# CloudCost

**Multi-cloud FinOps & cost optimization for AWS and Alibaba Cloud.**

[![CI](https://github.com/AlexLiu-vibecoding/cloudcost/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexLiu-vibecoding/cloudcost/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/cloudcost)](https://pypi.org/project/cloudcost/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Stars](https://img.shields.io/github/stars/AlexLiu-vibecoding/cloudcost?style=social)](https://github.com/AlexLiu-vibecoding/cloudcost)

> 💰 Find waste, right-size resources, plan reserved instances, and save up to **40%** on your cloud bills — across AWS and Alibaba Cloud in one tool.

---

## Why CloudCost?

Cloud bills are complex and growing. AWS Cost Explorer and Alibaba Cloud Billing give you numbers but **not actionable recommendations**. CloudCost bridges that gap:

- 🔍 **Scans both clouds** for idle resources, oversized instances, unattached volumes, old snapshots
- 📊 **Generates savings reports** with specific actions and dollar estimates
- 🎯 **Recommends Reserved Instance / Savings Plan purchases** with break-even analysis
- 📈 **Tracks cost trends** and detects anomalies
- 🖥️ **Built-in web dashboard** visualizes your multi-cloud spend
- ⚡ **Single command** — `pip install cloudcost && cloudcost aws scan`
- 🔌 **Extensible** — plug in your own analyzers and recommenders

### Terraform Cost Estimation

```bash
# Generate plan JSON
terraform plan -out=tfplan
terraform show -json tfplan > plan.json

# Estimate costs
cloudcost terraform plan.json --output summary
# Total monthly: $847.23
#   aws_instance.web:      $60.74/mo
#   aws_instance.worker:   $420.48/mo
#   ...
```

### Anomaly Detection

```bash
# Detect cost spikes with statistical analysis
cloudcost anomaly --monthly-cost 5000
# Flags days where cost deviates 2+ standard deviations from mean
```

```bash
pip install cloudcost
# Or with cloud SDKs:
pip install cloudcost[aws]        # AWS support
pip install cloudcost[aliyun]     # Alibaba Cloud support
pip install cloudcost[dashboard]  # Web dashboard
```

### AWS

```bash
export AWS_ACCESS_KEY_ID=ak_***
export AWS_SECRET_ACCESS_KEY=***# Full cost scan
cloudcost aws scan

# EC2 right-sizing
cloudcost aws ec2 --right-size

# Reserved Instance planner
cloudcost aws ri-plan --term 1year --payment partial-upfront

# S3 storage analysis
cloudcost aws s3 --analyze

# Generate HTML report
cloudcost report --format html --output savings.html
```

### Alibaba Cloud

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID=***
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=***# Full scan
cloudcost aliyun scan

# ECS right-sizing
cloudcost aliyun ecs --right-size

# OSS lifecycle planning
cloudcost aliyun oss
```

### Multi-cloud dashboard

```bash
cloudcost dashboard
# Opens http://localhost:8050 — see all your clouds in one view
```

## What It Finds

| Category | What we check | Typical savings |
|----------|--------------|----------------|
| **Idle Resources** | EC2/ECS <1% CPU for 7+ days, unattached EIPs, unused ALB/NLB | 15-30% |
| **Right-sizing** | Instances with <20% utilization → smaller family | 20-50% |
| **Storage** | S3/OSS without lifecycle policies, old snapshots, unattached EBS | 10-40% |
| **RDS** | Over-provisioned databases, missing read replicas, Multi-AZ waste | 15-35% |
| **Reserved Instances** | RI/SCU coverage gaps, break-even calculator | 30-60% |
| **Networking** | Idle NAT gateways, unused elastic IPs, excessive data transfer | 5-15% |

## Architecture

```
┌─────────────────────────────────────────────┐
│                  CloudCost CLI               │
│            (Click + Rich tables)             │
├─────────────────────────────────────────────┤
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  │
│  │ AWS      │  │ Alibaba   │  │ Dashboard│  │
│  │ Analyzer │  │ Analyzer  │  │ (Plotly) │  │
│  └────┬─────┘  └─────┬─────┘  └────┬─────┘  │
│       │              │             │         │
│  ┌────┴──────────────┴─────────────┴────┐    │
│  │    Recommendation Engine + Reporter  │    │
│  └─────────────────┬────────────────────┘    │
│                    │                         │
│  ┌─────────────────┴────────────────────┐    │
│  │  Reports (JSON / CSV / HTML / Slack) │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## Report Formats

```bash
# JSON (machine-readable)
cloudcost report --format json --output savings.json

# CSV for spreadsheet analysis
cloudcost report --format csv --output savings.csv

# Interactive HTML with charts
cloudcost report --format html --output report.html

# Slack notification
cloudcost report --format slack --slack-webhook https://hooks.slack.com/...
```

## Supported Services

| AWS | Alibaba Cloud |
|-----|---------------|
| EC2, RDS, S3 | ECS, RDS, OSS |
| EBS, Elastic IP, NAT Gateway | EIP, NAT Gateway, SLB |
| ALB/NLB, Lambda | Redis, MongoDB, PolarDB |
| ElastiCache, Redshift, Route53 | CDN |

## Development

```bash
git clone https://github.com/AlexLiu-vibecoding/cloudcost.git
cd cloudcost
pip install -e ".[dev]"
pytest tests/ -v
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas we'd love help with:
- ☁️ GCP / Azure support
- 📊 Kubernetes cost allocation
- 🔔 Email / Teams / DingTalk notifications
- 🧠 ML-based anomaly detection
- 🌐 Terraform cost estimation

## Roadmap

- [x] AWS Scanner (EC2, RDS, S3, EBS, EIP, NAT, ELB, Lambda, ElastiCache)
- [x] Alibaba Cloud Scanner (ECS, RDS, OSS, EIP, NAT, SLB, Redis)
- [x] Reserved Instance / Savings Plan planner
- [x] Multi-format reports (JSON, CSV, HTML, Slack)
- [x] Plotly Dash web dashboard
- [x] Cost anomaly detection (Z-score + moving average)
- [x] Terraform plan cost estimation
- [x] Docker support
- [ ] GCP support
- [ ] Azure support
- [ ] Kubernetes cost allocation
- [ ] Teams / DingTalk notifications
- [ ] Automated RI purchasing
- [ ] GitHub Actions cost tracking

## License

MIT — see [LICENSE](LICENSE)

---

⭐ **Star this repo** if you're tired of surprise cloud bills! Every star helps build better FinOps tooling for everyone.
