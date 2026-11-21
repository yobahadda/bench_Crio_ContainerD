#!/usr/bin/env bash
# Preflight: is everything the benchmark needs installed, running and loaded?
set -uo pipefail

IMAGE="${BENCH_IMAGE:-localhost/bench:1}"
STATE="${BENCH_STATE:-/var/lib/runtime-bench}"
fail=0

check() {  # check "description" command...
  local what="$1"; shift
  if "$@" >/dev/null 2>&1; then printf '  ok    %s\n' "$what"
  else printf '  FAIL  %s\n' "$what"; fail=1; fi
}

[[ $EUID -eq 0 ]] || { echo "run as root (sudo $0)" >&2; exit 1; }

echo "Binaries"
for bin in docker ctr crictl crio runc python3 skopeo; do check "$bin" command -v "$bin"; done

echo "Daemons"
check "containerd responds"   ctr version
check "dockerd responds"      docker info
check "crio responds"         crictl version

echo "Benchmark image ($IMAGE)"
check "in Docker"             docker image inspect "$IMAGE"
check "in containerd (bench)" bash -c "ctr -n bench images ls -q | grep -qx '$IMAGE'"
check "in CRI-O"              crictl inspecti "$IMAGE"
check "runc bundle"           test -f "$STATE/runc-bundle/config.json"

echo "Fairness"
crio_runtime="$(crio status config 2>/dev/null | awk -F'"' '/^ *default_runtime/{print $2; exit}')"
check "CRI-O default runtime is runc (got: ${crio_runtime:-unknown})" test "$crio_runtime" = runc
virt="$(systemd-detect-virt 2>/dev/null || echo unknown)"
echo "  info  virtualization: $virt, CPUs: $(nproc), cgroup: $(stat -fc %T /sys/fs/cgroup)"
[[ "$virt" == qemu ]] && echo "  warn  'qemu' can mean emulation (TCG). In UTM pick Virtualize, not Emulate."

exit $fail
