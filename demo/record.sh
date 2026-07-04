#!/usr/bin/env bash
# CloudCost Demo Script — fast version, no AWS API calls
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CLI="$PROJECT_DIR/.venv/bin/cloudcost"
PLAN="$PROJECT_DIR/tests/fixtures/sample_plan.json"

export TERM=xterm-256color COLUMNS=100 LINES=24
D=0.3  # delay between commands

echo '$ cloudcost --version'
$CLI --version
sleep $D
echo ""

echo '$ cloudcost --help'
$CLI --help
sleep $D
echo ""

echo '$ cloudcost terraform tests/fixtures/sample_plan.json --output summary'
$CLI terraform "$PLAN" --output summary
sleep $D
echo ""

echo '$ cloudcost anomaly --monthly-cost 5000 --output json'
$CLI anomaly --monthly-cost 5000 --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Detected {len(data)} cost anomalies:')
for a in data[:3]:
    print(f'  {a[\"date\"]} | {a[\"service\"]:6s} | \${a[\"cost\"]:>8.2f} (spike {a.get(\"z_score\",a.get(\"ratio\",0)):.1f}x) | {a[\"severity\"]}')
"
sleep $D
echo ""

echo '$ cloudcost aliyun scan'
$CLI aliyun scan 2>/dev/null
sleep $D
echo ""

echo '$ cloudcost aws ec2 --right-size'
echo "(Graviton ARM migration, right-sizing, idle detection — requires AWS credentials)"
echo ""
echo 'Example finding with credentials:'
echo '  i-0abc123def: m5.xlarge (x86) → m7g.xlarge (Graviton ARM) – save 15%'
echo '  i-0def456ghi: c5.2xlarge avg CPU 12.3% → c5.xlarge – save 50%'
echo '  Bucket "logs": No lifecycle policy — save ~$18/mo per TB'
sleep $D
echo ""

echo '$ pytest tests/ -q'
cd "$PROJECT_DIR" && .venv/bin/pytest tests/ -q 2>/dev/null
sleep $D
echo ""

echo ""
echo '  💰 CloudCost — save up to 40% on multi-cloud bills'
echo '  ⭐ github.com/AlexLiu-vibecoding/cloudcost'
