# CloudCost

**Multi-cloud FinOps & cost optimization for AWS and Alibaba Cloud.**

[![PyPI](https://img.shields.io/pypi/v/cloudcost)](https://pypi.org/project/cloudcost/)
[![Python](https://img.shields.io/pypi/pyversions/cloudcost)](https://pypi.org/project/cloudcost/)
[![License](https://img.shields.io/github/license/AlexLiu-vibecoding/cloudcost)](LICENSE)

> 💰 Find waste, right-size resources, plan reserved instances, and save up to **40%** on your cloud bills — across AWS and Alibaba Cloud in one tool.

## Why CloudCost?

Cloud bills are complex. AWS Cost Explorer and Alibaba Cloud Billing give you numbers but not *actionable* recommendations. CloudCost:

- 🔍 **Scans both clouds** for idle resources, oversized instances, unattached volumes, old snapshots
- 📊 **Generates savings reports** with specific actions and dollar estimates
- 🎯 **Recommends Reserved Instance / Savings Plan purchases** with break-even analysis
- 📈 **Tracks cost trends** and detects anomalies (spikes, new services, region drift)
- 🖥️ **Built-in web dashboard** to visualize your multi-cloud spend
- ⚡ **Single binary** — `pip install cloudcost` and run

## Quick Start

```bash
pip install cloudcost
```

### AWS

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# Full scan
cloudcost aws scan

# EC2 right-sizing recommendations
cloudcost aws ec2 --right-size

# Reserved Instance planner
cloudcost aws ri-plan --term 1year --payment partial-upfront

# S3 storage analysis
cloudcost aws s3 --analyze
```

### Alibaba Cloud

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID=...
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=...

# Full scan
cloudcost aliyun scan

# ECS optimization
cloudcost aliyun ecs --right-size

# OSS storage tiering
cloudcost aliyun oss --lifecycle-policy
```

### Multi-cloud dashboard

```bash
cloudcost dashboard
# Opens http://localhost:8050 — see all clouds in one view
```

## What It Finds

| Category | What we check | Typical savings |
|----------|--------------|----------------|
| **Idle Resources** | EC2/ECS <1% CPU for 7+ days, unattached EIPs, unused ALB/NLB | 15-30% |
| **Right-sizing** | Instances with <20% utilization → smaller family | 20-50% |
| **Storage** | S3/OSS without lifecycle policies, old snapshots, unattached EBS | 10-40% |
| **RDS** | Over-provisioned databases, missing read replicas | 15-35% |
| **Reserved/Package** | RI/SCU coverage gaps, break-even calculator | 30-60% |
| **Networking** | Idle NAT gateways, unused elastic IPs, excessive data transfer | 5-15% |

## Architecture

```
┌─────────────────────────────────────────────┐
│                  CloudCost CLI               │
├─────────────────────────────────────────────┤
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  │
│  │ AWS      │  │ Alibaba   │  │ Dashboard│  │
│  │ Analyzer │  │ Analyzer  │  │ (Plotly) │  │
│  └────┬─────┘  └─────┬─────┘  └────┬─────┘  │
│       │              │             │         │
│  ┌────┴──────────────┴─────────────┴────┐    │
│  │         Recommendation Engine        │    │
│  └─────────────────┬────────────────────┘    │
│                    │                         │
│  ┌─────────────────┴────────────────────┐    │
│  │  Reports (JSON / CSV / HTML / Slack) │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## Reports

```bash
# JSON (machine-readable)
cloudcost report --format json --output savings.json

# CSV for Excel
cloudcost report --format csv --output savings.csv

# HTML with charts
cloudcost report --format html --output report.html

# Slack notification
cloudcost report --format slack --webhook https://hooks.slack.com/...
```

## Supported Services

### AWS
EC2, RDS, S3, EBS, Elastic IP, NAT Gateway, ALB/NLB, Lambda, ElastiCache, Redshift, Route53

### Alibaba Cloud
ECS, RDS, OSS, EIP, NAT Gateway, SLB, Redis, MongoDB, PolarDB, CDN

## License

MIT — see [LICENSE](LICENSE)

---

⭐ **Star this repo** if you're tired of surprise cloud bills!
