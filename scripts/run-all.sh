#!/usr/bin/env bash
# The full suite: environment, start latency, Docker overhead split, memory, report.
#   sudo scripts/run-all.sh [results-dir]
# Tunables (env): ROUNDS=50 WARMUP=5 MEM_N=20 ISOLATION=0 VARIANTS=<comma list>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/results/$(hostname)-$(date +%Y%m%d-%H%M%S)}"
ROUNDS="${ROUNDS:-50}"; WARMUP="${WARMUP:-5}"; MEM_N="${MEM_N:-20}"
mkdir -p "$OUT"

[[ $EUID -eq 0 ]] || { echo "run as root (sudo $0)" >&2; exit 1; }
"$ROOT/scripts/doctor.sh" || { echo "preflight failed; fix the FAIL lines above" >&2; exit 1; }

echo "==> environment";    "$ROOT/scripts/collect-env.sh" > "$OUT/env.json"
echo "==> start latency";  python3 "$ROOT/bench/latency.py"  --rounds "$ROUNDS" --warmup "$WARMUP" \
                             ${VARIANTS:+--only "$VARIANTS"} --out "$OUT/latency.json"
echo "==> Docker overhead"; python3 "$ROOT/bench/overhead.py" --rounds "$ROUNDS" --warmup "$WARMUP" --out "$OUT/overhead.json"
echo "==> memory";         python3 "$ROOT/bench/memory.py"   --n "$MEM_N" --out "$OUT/memory.json"
if [[ "${ISOLATION:-0}" == 1 ]]; then
  echo "==> isolation";    "$ROOT/scripts/isolation.sh" "$OUT" 40
fi
echo "==> report";         python3 "$ROOT/report/report.py" "$OUT"

# hand the results back to the user who ran sudo
[[ -n "${SUDO_USER:-}" ]] && chown -R "$SUDO_USER": "$OUT"
echo; echo "Results: $OUT"
