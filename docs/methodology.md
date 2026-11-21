# Methodology

## Fairness rules

- **One runc for everyone.** Docker and containerd use the runc shipped in Docker's `containerd.io` package. CRI-O defaults to crun since v1.31, so the playbook sets CRI-O's default runtime to that same runc (`ansible/roles/crio/templates/90-bench.conf.j2`). The `crio-crun` variant measures CRI-O as shipped.
- **One image for everyone.** A ~3 MB image (static busybox plus a static pause binary) is built once and loaded into all three image stores. No registry pulls happen during timing.
- **No pod networking.** Docker variants use `--network none` (plus one bridge variant for comparison). CRI-O pods get a loopback-only CNI network. containerd's `ctr run` creates no network.
- **Same lifecycle.** Each timed call returns once the container is running (a detached `sleep`). Removal happens outside the timed region.

## Statistics

- 5 warm-up rounds, then N rounds (default 50).
- Each round runs every variant once, in a new random order (seeded), so slow periods on the host hit all variants equally.
- Reported: median and 95th percentile. The mean is in the JSON but skews with outliers.

## What the numbers include

- **CLI startup.** Each timing includes launching `docker`, `ctr` or `crictl` as a new process. The kubelet talks gRPC directly and never pays this. `bench/overhead.py` measures it separately, along with Docker's raw Engine API, so the report can split Docker's time into CLI, dockerd, containerd and runc.
- **The CRI-O pod variant** starts two containers (the sandbox and your app), so it's the cost of a Kubernetes pod start, not a like-for-like comparison.

## Memory

PSS (proportional set size) from `/proc/<pid>/smaps_rollup`, which splits shared pages between processes, so summing many shims doesn't double count. Measured idle, then with N idle containers per runtime, one runtime at a time. Under Kubernetes, containerd runs one shim per pod rather than per container, so its per-container cost is closer to a per-pod cost there.

## Known limits

- One machine per run. VM numbers move with host load, so trust the ranking more than the exact milliseconds.
- No image pulls, no real workloads, no concurrency (containers start one at a time).
- `make bench-all` adds an isolation test (all daemons vs each alone). In earlier runs the difference stayed within a few milliseconds.
