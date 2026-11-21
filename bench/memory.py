#!/usr/bin/env python3
"""
Memory footprint (PSS from /proc/<pid>/smaps_rollup, which splits shared pages fairly):
idle daemons, then each runtime with N idle containers.

  sudo python3 bench/memory.py --n 20 --out results/memory.json
Run it on an otherwise idle machine, not alongside latency.py.
"""
import argparse
import json
import os
import tempfile
import time
import uuid

from common import IMAGE, require_root, sh, write_json

SHIMS = {"containerd-shim", "containerd-shim-runc-v2"}   # comm is truncated to 15 chars


def pss_kb(pid):
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def processes():
    out = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open(f"/proc/{entry}/comm") as f:
                    out[int(entry)] = f.read().strip()
            except OSError:
                pass
    return out


def mb(names):
    procs = processes()
    pids = [pid for pid, comm in procs.items() if comm in names]
    return round(sum(pss_kb(p) for p in pids) / 1024, 1), len(pids)


def settle(seconds=3):
    time.sleep(seconds)


def docker_case(n):
    base_shims = mb(SHIMS)[0]
    names = []
    for _ in range(n):
        name = "m" + uuid.uuid4().hex[:8]
        sh(["docker", "run", "-d", "--network", "none", "--name", name, IMAGE, "sleep", "3600"])
        names.append(name)
    settle()
    shims, count = mb(SHIMS)
    res = {"dockerd_mb": mb({"dockerd"})[0], "containerd_mb": mb({"containerd"})[0],
           "helpers_mb": round(shims - base_shims, 1), "helper_procs": count}
    sh(["docker", "rm", "-f", *names])
    settle()
    return res


def containerd_case(n):
    base_shims = mb(SHIMS)[0]
    names = []
    for _ in range(n):
        name = "m" + uuid.uuid4().hex[:8]
        sh(["ctr", "-n", "bench", "run", "-d", IMAGE, name, "sleep", "3600"])
        names.append(name)
    settle()
    shims, count = mb(SHIMS)
    res = {"containerd_mb": mb({"containerd"})[0], "helpers_mb": round(shims - base_shims, 1), "helper_procs": count}
    for name in names:
        sh(["ctr", "-n", "bench", "task", "rm", "-f", name], check=False)
        sh(["ctr", "-n", "bench", "container", "rm", name], check=False)
    settle()
    return res


def crio_case(n):
    work = tempfile.mkdtemp(prefix="bench-mem-")
    pod_json = os.path.join(work, "pod.json")
    with open(pod_json, "w") as f:
        json.dump({"metadata": {"name": "mempod", "namespace": "bench", "uid": "mempod", "attempt": 1},
                   "log_directory": "/tmp/runtime-bench-logs", "linux": {}}, f)
    base_conmon = mb({"conmon"})[0]
    pod = sh(["crictl", "runp", pod_json])
    infra_conmon = mb({"conmon"})[0] - base_conmon
    for i in range(n):
        spec = os.path.join(work, f"c{i}.json")
        with open(spec, "w") as f:
            json.dump({"metadata": {"name": f"c{i}"}, "image": {"image": IMAGE},
                       "command": ["/bin/sleep", "3600"], "log_path": f"c{i}.log", "linux": {}}, f)
        sh(["crictl", "start", sh(["crictl", "create", pod, spec, pod_json])])
    settle()
    conmon, count = mb({"conmon"})
    res = {"crio_mb": mb({"crio"})[0], "helpers_mb": round(conmon - base_conmon - infra_conmon, 1),
           "helper_procs": count, "infra_conmon_mb": round(infra_conmon, 1)}
    sh(["crictl", "rmp", "-f", pod])
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=20, help="containers per runtime")
    ap.add_argument("--out", default="results/memory.json")
    args = ap.parse_args()
    require_root()

    settle()
    res = {"n": args.n, "idle": {"dockerd_mb": mb({"dockerd"})[0], "containerd_mb": mb({"containerd"})[0],
                                 "crio_mb": mb({"crio"})[0]}}
    res["docker"] = docker_case(args.n)
    res["containerd"] = containerd_case(args.n)
    res["crio"] = crio_case(args.n)
    print(json.dumps(res, indent=1))
    write_json(args.out, res)


if __name__ == "__main__":
    main()
