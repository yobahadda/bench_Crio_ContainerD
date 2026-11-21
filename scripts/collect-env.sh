#!/usr/bin/env bash
# Print the machine and runtime versions as JSON, so every result says where it came from.
set -uo pipefail

v() { "$@" 2>/dev/null | head -1 | tr -d '"' || true; }
# shellcheck source=/dev/null
. /etc/os-release

jq -n \
  --arg os "$PRETTY_NAME" \
  --arg kernel "$(uname -r)" \
  --arg arch "$(uname -m)" \
  --arg cpus "$(nproc)" \
  --arg cpu_model "$(awk -F': ' '/model name|^Model/{print $2; exit}' /proc/cpuinfo)" \
  --arg mem_mb "$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)" \
  --arg cgroup "$(stat -fc %T /sys/fs/cgroup)" \
  --arg virt "$(systemd-detect-virt 2>/dev/null || echo unknown)" \
  --arg docker "$(v docker version --format '{{.Server.Version}}')" \
  --arg containerd "$(containerd --version 2>/dev/null | grep -m1 -oE 'v[0-9]+\.[0-9]+\.[0-9]+')" \
  --arg crio "$(crio --version 2>/dev/null | grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+')" \
  --arg crictl "$(v crictl --version)" \
  --arg conmon "$(v conmon --version)" \
  --arg runc "$(v runc --version)" \
  --arg crun "$(v crun --version)" \
  --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{date: $date, os: $os, kernel: $kernel, arch: $arch, cpus: ($cpus|tonumber), cpu_model: $cpu_model,
    mem_mb: ($mem_mb|tonumber), cgroup_fs: $cgroup, virtualization: $virt,
    versions: {docker: $docker, containerd: $containerd, crio: $crio, crictl: $crictl,
               conmon: $conmon, runc: $runc, crun: $crun}}'
