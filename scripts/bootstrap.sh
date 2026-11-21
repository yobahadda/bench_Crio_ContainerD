#!/usr/bin/env bash
# One command to provision a fresh Ubuntu VM from inside it:
#   git clone <repo> && cd runtime-bench && sudo ./scripts/bootstrap.sh
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run with sudo: sudo $0" >&2; exit 1; }
cd "$(dirname "$0")/../ansible"

echo "==> installing Ansible"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ansible-core python3-debian >/dev/null

echo "==> running the playbook"
ansible-playbook site.yml "$@"

echo
echo "Done. Next: make doctor && make bench"
