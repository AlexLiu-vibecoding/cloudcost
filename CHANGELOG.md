# Changelog

All notable changes to CloudCost will be documented in this file.

## [0.1.0] — 2026-07-04

### Added

**AWS**
- EC2 optimizer: right-sizing, Graviton ARM migration (30+ types), idle detection, old-gen upgrades
- RDS optimizer: Graviton migration, right-sizing via CloudWatch, Aurora migration, gp2→gp3, backup optimization, RI planning, public access check, engine version check
- S3 analyzer: 7-tier storage lifecycle (Standard→IA→Glacier IR→Glacier FR→Deep Archive), Intelligent-Tiering, versioning cleanup, multipart cleanup
- ElastiCache optimizer: Graviton, right-sizing via memory/CPU, idle cluster detection, RI planning, Redis/Memcached specific
- RI/Savings Plan planner with break-even analysis
- EBS, EIP, NAT Gateway, ALB/NLB, Lambda scanners

**Alibaba Cloud**
- ECS optimizer: Yitian ARM (倚天710) migration, generation upgrades (g5/g6/g7 + c/r families)
- OSS analyzer: storage lifecycle, versioning, multipart cleanup
- RDS, EIP, NAT, SLB, Redis scanners

**Core**
- Unified Click CLI with Rich table output
- Cost anomaly detection (Z-score + moving average)
- Terraform plan JSON cost estimation (AWS + Alibaba)
- Multi-format reports: table, JSON, CSV, HTML, Slack
- Plotly Dash interactive web dashboard
- Docker multi-stage build
- 30 tests covering all modules
