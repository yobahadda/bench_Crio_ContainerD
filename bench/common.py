"""Shared helpers for the benchmark scripts. Standard library only."""
import json
import os
import statistics
import subprocess
import time

IMAGE = os.environ.get("BENCH_IMAGE", "localhost/bench:1")
STATE = os.environ.get("BENCH_STATE", "/var/lib/runtime-bench")


def sh(cmd, check=True):
    """Run a command, return stdout. stdin and stderr are closed so nothing can hang on a pipe."""
    return subprocess.run(cmd, check=check, text=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()


def quiet(cmd, check=True):
    """Run a command with no pipes at all (for detached containers that inherit stdio)."""
    subprocess.run(cmd, check=check, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ms_since(t0):
    return (time.perf_counter() - t0) * 1000.0


def percentile(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarize(xs):
    return {
        "n": len(xs),
        "median": statistics.median(xs),
        "p95": percentile(xs, 95),
        "mean": statistics.mean(xs),
        "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0,
        "min": min(xs),
        "max": max(xs),
    }


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def require_root():
    if os.geteuid() != 0:
        raise SystemExit("run as root (sudo)")
