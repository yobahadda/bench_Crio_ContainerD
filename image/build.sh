#!/usr/bin/env bash
# Build the benchmark image once and load it into Docker, containerd and CRI-O,
# plus a plain runc bundle for the no-daemon baseline.
# Re-running is a no-op unless FORCE=1.
set -euo pipefail

IMAGE="${BENCH_IMAGE:-localhost/bench:1}"
STATE="${BENCH_STATE:-/var/lib/runtime-bench}"
HERE="$(cd "$(dirname "$0")" && pwd)"

[[ $EUID -eq 0 ]] || { echo "run as root (sudo $0)" >&2; exit 1; }

loaded() {
  docker image inspect "$IMAGE" >/dev/null 2>&1 &&
    ctr -n bench images ls -q | grep -qx "$IMAGE" &&
    crictl inspecti "$IMAGE" >/dev/null 2>&1 &&
    [[ -f "$STATE/runc-bundle/config.json" ]]
}

if [[ "${FORCE:-0}" != 1 ]] && loaded; then
  echo "image $IMAGE already loaded in all runtimes"
  exit 0
fi

BUSYBOX="$(command -v busybox || true)"
[[ -n "$BUSYBOX" ]] || { echo "busybox not found (apt install busybox-static)" >&2; exit 1; }
if ldd "$BUSYBOX" >/dev/null 2>&1; then
  echo "$BUSYBOX is dynamically linked; install busybox-static" >&2; exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/rootfs/bin"
cp "$BUSYBOX" "$work/rootfs/bin/busybox"
for applet in sh echo sleep true cat; do ln -sf busybox "$work/rootfs/bin/$applet"; done
gcc -static -O2 -o "$work/rootfs/pause" "$HERE/pause.c"
cp "$HERE/Dockerfile" "$work/"

echo "==> building $IMAGE"
docker build -q -t "$IMAGE" "$work" >/dev/null
docker save "$IMAGE" -o "$work/image.tar"

echo "==> loading into containerd (namespace: bench)"
ctr -n bench images import "$work/image.tar" >/dev/null

echo "==> loading into CRI-O (containers-storage)"
skopeo copy -q "docker-archive:$work/image.tar" "containers-storage:$IMAGE"

echo "==> preparing the runc bundle in $STATE/runc-bundle"
rm -rf "$STATE/runc-bundle"
mkdir -p "$STATE/runc-bundle"
cp -a "$work/rootfs" "$STATE/runc-bundle/rootfs"
( cd "$STATE/runc-bundle" && runc spec )
python3 - "$STATE/runc-bundle/config.json" <<'PY'
import json, sys
path = sys.argv[1]
cfg = json.load(open(path))
cfg["process"]["terminal"] = False
cfg["process"]["args"] = ["/bin/sleep", "3600"]
cfg["root"]["readonly"] = False
json.dump(cfg, open(path, "w"), indent=2)
PY

echo "image $IMAGE built and loaded"
