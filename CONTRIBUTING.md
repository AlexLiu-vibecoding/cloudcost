# Contributing to CloudCost

Thanks for your interest in contributing! CloudCost is an open-source multi-cloud FinOps tool, and we welcome contributions of all kinds.

## Getting Started

```bash
git clone https://github.com/AlexLiu-vibecoding/cloudcost.git
cd cloudcost
pip install -e ".[dev]"
pytest tests/ -v
```

## Development Workflow

1. **Fork** the repository
2. **Create a branch** — `git checkout -b feat/your-feature`
3. **Make changes** — follow the style guide below
4. **Test** — `pytest tests/ -v`
5. **Lint** — `ruff check cloudcost/`
6. **Commit** — use conventional commits (`feat:`, `fix:`, `docs:`, etc.)
7. **Push** and open a **Pull Request**

## Style Guide

- Python 3.10+ with type hints
- 100 character line limit (configured in pyproject.toml)
- Use `black` for formatting
- Use `ruff` for linting
- Write tests for new features
- Keep dependencies minimal — the core package should require only `click`, `rich`, `tabulate`, `jinja2`, and `python-dateutil`

## Project Structure

```
cloudcost/
├── cloudcost/
│   ├── aws/          # AWS analyzers
│   │   ├── scanner.py        # Orchestrator
│   │   ├── ec2_optimizer.py  # EC2 right-sizing
│   │   ├── rds_optimizer.py  # RDS analysis
│   │   ├── s3_analyzer.py    # S3 lifecycle
│   │   └── ri_planner.py     # Reserved Instances
│   ├── aliyun/       # Alibaba Cloud analyzers
│   │   ├── scanner.py
│   │   ├── ecs_optimizer.py
│   │   └── oss_analyzer.py
│   ├── core/         # Shared logic
│   │   └── reporter.py      # Report generation
│   ├── dashboard/    # Web UI
│   │   └── app.py           # Plotly Dash
│   └── cli.py        # Click CLI
├── tests/
├── examples/
└── pyproject.toml
```

## Adding a New Cloud Provider

1. Create a package under `cloudcost/<provider>/`
2. Implement a scanner class with `scan()`, `scan_region()` methods
3. Add CLI commands to `cloudcost/cli.py`
4. Return findings as dictionaries with these fields:
   - `service`: service name (e.g., "ec2", "gce")
   - `region`: cloud region
   - `resource_id`: resource identifier
   - `finding`: short label (e.g., "idle_instance", "right_size")
   - `severity`: "high", "medium", "low", or "info"
   - `detail`: human-readable description
   - `action`: what to do about it
   - `estimated_monthly_savings_usd`: estimated $ savings/month

## Adding a New Analyzer

1. Create a new file in the provider's package
2. Implement the analyzer class
3. Register it in the scanner's `_scan_service()` method
4. Add tests in `tests/`

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=cloudcost --cov-report=term

# Specific test
pytest tests/test_aws.py -v
```

## Questions?

Open an issue at https://github.com/AlexLiu-vibecoding/cloudcost/issues

We're especially excited about contributions for:
- GCP and Azure support
- Kubernetes cost allocation
- ML-based anomaly detection
- Additional notification channels (Teams, DingTalk, Email)
- Terraform plan cost estimation
