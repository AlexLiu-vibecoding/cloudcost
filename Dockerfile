# CloudCost Docker image
# Multi-stage build for minimal size

FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml ./
COPY cloudcost/ cloudcost/

RUN pip install --no-cache-dir -e .

# ── Runtime stage ──────────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/cloudcost /usr/local/bin/cloudcost
COPY cloudcost/ cloudcost/
COPY pyproject.toml ./

# Default: show help
ENTRYPOINT ["cloudcost"]
CMD ["--help"]
