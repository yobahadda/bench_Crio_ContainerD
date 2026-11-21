#!/usr/bin/env python3
"""
Start latency: time from invoking each runtime's CLI until it returns with the
container RUNNING (a detached `sleep`). Cleanup is outside the timed region, and
variants run in a freshly shuffled order every round so drift hits them equally.

  sudo python3 bench/latency.py --rounds 50 --out results/latency.json
  sudo python3 bench/latency.py --only ctr,docker,crio
"""
import argparse
import json
import os
import random
import tempfile
import time
import uuid

from common import IMAGE, STATE, ms_since, quiet, require_root, sh, summarize, write_json


class Runc:
    key, label = "runc", "runc run -d (no daemon)"

    def run(self):
        name = "r" + uuid.uuid4().hex[:10]
        t0 = time.perf_counter()
        quiet(["runc", "run", "-d", "-b", os.path.join(STATE, "runc-bundle"), name])
        ms = ms_since(t0)
        quiet(["runc", "delete", "-f", name], check=False)
        return ms


class Containerd:
    key, label = "ctr", "ctr run (containerd)"

    def run(self):
        name = "b" + uuid.uuid4().hex[:10]
        t0 = time.perf_counter()
        sh(["ctr", "-n", "bench", "run", "-d", IMAGE, name, "sleep", "3600"])
        ms = ms_since(t0)
        sh(["ctr", "-n", "bench", "task", "rm", "-f", name], check=False)
        sh(["ctr", "-n", "bench", "container", "rm", name], check=False)
        return ms


class Docker:
    def __init__(self, network):
        self.network = network
        self.key = "docker" if network == "none" else "docker-bridge"
        self.label = "docker run --network none" if network == "none" else "docker run (bridge network)"

    def run(self):
        name = "b" + uuid.uuid4().hex[:10]
        cmd = ["docker", "run", "-d", "--name", name]
        if self.network == "none":
            cmd += ["--network", "none"]
        t0 = time.perf_counter()
        sh(cmd + [IMAGE, "sleep", "3600"])
        ms = ms_since(t0)
        sh(["docker", "rm", "-f", name])
        return ms


def _pod_spec(directory, name):
    path = os.path.join(directory, f"pod-{name}.json")
    with open(path, "w") as f:
        json.dump({"metadata": {"name": name, "namespace": "bench", "uid": name, "attempt": 1},
                   "log_directory": "/tmp/runtime-bench-logs", "linux": {}}, f)
    return path


def _container_spec(directory, name):
    path = os.path.join(directory, f"ctr-{name}.json")
    with open(path, "w") as f:
        json.dump({"metadata": {"name": name}, "image": {"image": IMAGE},
                   "command": ["/bin/sleep", "3600"], "log_path": f"{name}.log", "linux": {}}, f)
    return path


class CrioContainer:
    """Container in an existing pod: create + start, what the kubelet does per container."""

    def __init__(self, runtime=None):
        self.runtime = runtime
        self.key = "crio" if runtime is None else f"crio-{runtime}"
        self.label = "crictl create+start, existing pod" + ("" if runtime is None else f" ({runtime})")
        self.dir = tempfile.mkdtemp(prefix="bench-crio-")
        self.pod_json = _pod_spec(self.dir, f"benchpod-{self.key}")
        cmd = ["crictl", "runp"] + (["--runtime", runtime] if runtime else []) + [self.pod_json]
        self.pod = sh(cmd)

    def run(self):
        name = "c" + uuid.uuid4().hex[:10]
        spec = _container_spec(self.dir, name)
        t0 = time.perf_counter()
        cid = sh(["crictl", "create", self.pod, spec, self.pod_json])
        sh(["crictl", "start", cid])
        ms = ms_since(t0)
        sh(["crictl", "rm", "-f", cid])
        return ms

    def close(self):
        sh(["crictl", "rmp", "-f", self.pod], check=False)


class CrioPod:
    """A brand-new Kubernetes-style pod: sandbox (pause) + one container."""
    key, label = "crio-pod", "crictl runp+create+start, new pod"

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="bench-criopod-")

    def run(self):
        name = "p" + uuid.uuid4().hex[:10]
        pod_json = _pod_spec(self.dir, name)
        spec = _container_spec(self.dir, name)
        t0 = time.perf_counter()
        pod = sh(["crictl", "runp", pod_json])
        cid = sh(["crictl", "create", pod, spec, pod_json])
        sh(["crictl", "start", cid])
        ms = ms_since(t0)
        sh(["crictl", "rmp", "-f", pod])
        return ms


FACTORIES = {
    "runc": Runc,
    "ctr": Containerd,
    "docker": lambda: Docker("none"),
    "docker-bridge": lambda: Docker("bridge"),
    "crio": CrioContainer,
    "crio-pod": CrioPod,
    "crio-crun": lambda: CrioContainer(runtime="crun"),
}
DEFAULT = ["runc", "ctr", "docker", "docker-bridge", "crio", "crio-pod", "crio-crun"]


def build(keys):
    variants = []
    for key in keys:
        try:
            variants.append(FACTORIES[key]())
        except KeyError:
            raise SystemExit(f"unknown variant {key!r}; choose from {', '.join(FACTORIES)}")
        except Exception as exc:  # e.g. crun handler not configured
            print(f"skipping {key}: {exc}")
    return variants


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--only", default=",".join(DEFAULT), help="comma list of: " + ", ".join(FACTORIES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="results/latency.json")
    args = ap.parse_args()
    require_root()
    random.seed(args.seed)

    variants = build([k.strip() for k in args.only.split(",") if k.strip()])
    samples = {v.key: [] for v in variants}
    try:
        for _ in range(args.warmup):
            for v in variants:
                v.run()
        for r in range(args.rounds):
            order = variants[:]
            random.shuffle(order)
            for v in order:
                samples[v.key].append(v.run())
            if (r + 1) % 10 == 0:
                print(f"  round {r + 1}/{args.rounds}", flush=True)
    finally:
        for v in variants:
            if hasattr(v, "close"):
                v.close()

    summary = {v.key: {"label": v.label, **summarize(samples[v.key])} for v in variants}
    print(f"\n{'variant':44} {'median':>8} {'p95':>8} {'stdev':>7}   ms, n={args.rounds}")
    for v in variants:
        s = summary[v.key]
        print(f"{v.label:44} {s['median']:8.1f} {s['p95']:8.1f} {s['stdev']:7.1f}")
    write_json(args.out, {"rounds": args.rounds, "warmup": args.warmup, "summary": summary, "samples": samples})


if __name__ == "__main__":
    main()
