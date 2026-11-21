#!/usr/bin/env python3
"""
Splits Docker's extra time into CLI cost and daemon cost:
  - Docker via its raw Engine API (create + start over the Unix socket, no CLI process)
  - Each CLI's own startup time, doing no container work

  sudo python3 bench/overhead.py --rounds 50 --out results/overhead.json
"""
import argparse
import http.client
import json
import socket
import subprocess
import time

from common import IMAGE, ms_since, require_root, summarize, write_json

API = "/v1.44"


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost")
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(self.unix_path)


def docker_call(method, url, body=None):
    conn = UnixHTTP("/var/run/docker.sock")
    conn.request(method, API + url, body=json.dumps(body) if body else None,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    if resp.status >= 400:
        raise RuntimeError(f"{method} {url}: {resp.status} {data[:200]!r}")
    return data


def api_start(network):
    t0 = time.perf_counter()
    created = docker_call("POST", "/containers/create",
                          {"Image": IMAGE, "Cmd": ["sleep", "3600"], "HostConfig": {"NetworkMode": network}})
    cid = json.loads(created)["Id"]
    docker_call("POST", f"/containers/{cid}/start")
    ms = ms_since(t0)
    docker_call("DELETE", f"/containers/{cid}?force=1")
    return ms


def cli_start(cmd):
    t0 = time.perf_counter()
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return ms_since(t0)


CLI_PROBES = {
    "docker": ["docker", "context", "show"],   # no daemon call
    "ctr": ["ctr", "--help"],
    "crictl": ["crictl", "--help"],
}


def measure(fn, rounds, warmup):
    for _ in range(warmup):
        fn()
    return [fn() for _ in range(rounds)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--out", default="results/overhead.json")
    args = ap.parse_args()
    require_root()

    out = {"docker_api": {}, "cli_startup": {}}
    for net in ("none", "bridge"):
        out["docker_api"][net] = summarize(measure(lambda n=net: api_start(n), args.rounds, args.warmup))
        print(f"Engine API create+start ({net:6}): median {out['docker_api'][net]['median']:6.1f} ms")
    for name, cmd in CLI_PROBES.items():
        out["cli_startup"][name] = summarize(measure(lambda c=cmd: cli_start(c), args.rounds, args.warmup))
        print(f"{name:7} CLI startup: median {out['cli_startup'][name]['median']:6.1f} ms")
    write_json(args.out, out)


if __name__ == "__main__":
    main()
