#!/usr/bin/env bash
# Does running all three daemons side by side change the results?
# Times each runtime with everything running, then alone, then everything again.
#   sudo scripts/isolation.sh results/<run> [rounds]
set -euo pipefail

OUT="${1:?usage: $0 <results-dir> [rounds]}"
ROUNDS="${2:-40}"
BENCH="$(cd "$(dirname "$0")/../bench" && pwd)/latency.py"
mkdir -p "$OUT/isolation"

stop_all()  { systemctl stop docker.socket docker crio containerd; sleep 2; }
start()     { systemctl start "$@"; sleep 3; }
run()       { python3 "$BENCH" --rounds "$ROUNDS" --only "$1" --out "$OUT/isolation/$2.json" | tail -n +2; }

trap 'systemctl start containerd docker crio' EXIT

echo "==> all daemons running (1/2)"; stop_all; start containerd docker crio; run ctr,docker,crio all-1
echo "==> containerd alone";          stop_all; start containerd;              run ctr          ctr-alone
echo "==> Docker alone (+containerd)"; stop_all; start containerd docker;      run docker       docker-alone
echo "==> CRI-O alone";               stop_all; start crio;                    run crio         crio-alone
echo "==> all daemons running (2/2)"; stop_all; start containerd docker crio; run ctr,docker,crio all-2
