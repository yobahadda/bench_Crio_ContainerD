CLAUDE.md

Context for Claude Code sessions working in this repo.

What this is

Benchmark suite comparing Docker, containerd and CRI-O on one Ubuntu machine (start latency, memory, where Docker's extra time goes). It backs the Medium article "Is Docker Really Slower? Benchmarking Docker vs containerd vs CRI-O" by Ayoub Bahadda. Target machine: an Ubuntu 26.04/26.10 VM in UTM on a Mac (likely arm64).

Commands
make provision: Ansible provisions the machine it runs on (scripts/bootstrap.sh installs ansible-core first)
make doctor: preflight checks; fix every FAIL before benchmarking
make bench / make quick / make bench-all: full suite, smoke run, suite plus isolation test
make report DIR=results/<run>: re-render charts and summary.md
make lint: ansible-lint (production profile), shellcheck, py_compile. Keep this passing.

All benchmark scripts need root; the Makefile adds sudo.

Design decisions (keep them)
One runc for everyone. Docker and containerd use /usr/bin/runc from Docker's containerd.io package. CRI-O has defaulted to crun since v1.31, so ansible/roles/crio/templates/90-bench.conf.j2 sets its default runtime to that same runc. The crio-crun variant measures CRI-O as shipped, and is skipped automatically if the crun handler is missing.
CRI-O's apt repo moved to download.opensuse.org/repositories/isv:/cri-o:/stable:/<version>/deb/ (not pkgs.k8s.io). crictl comes from pkgs.k8s.io cri-tools only if the cri-o package doesn't ship it.
No registry. image/build.sh builds a ~3 MB image (static busybox plus image/pause.c) and loads it into Docker, containerd (namespace bench) and CRI-O (via skopeo). CRI-O also uses it as the pod sandbox image (pause_command = "/pause").
No pod networking. Docker uses --network none (plus one bridge variant), CRI-O pods get a loopback-only CNI config, and ctr run has no network.
Timing. Detached sleep containers, timed until the CLI returns; cleanup untimed; variants shuffled every round; median and p95 reported.
Stdlib-only Python in bench/ and report/. Charts are hand-written SVG rendered with rsvg-convert, in the article's editorial style (paper background, Lora/Inter, one red accent for Docker).
All versions in ansible/group_vars/all.yml. Use only ansible.builtin modules, and prefix role-registered variables with the role name (ansible-lint).
Status
Scripts tested end to end on Ubuntu 24.04 x86_64 (image build, doctor, latency, overhead, memory, report).
First real run (2026-11-21): Lima VM (vz backend), Ubuntu 26.04.1 arm64, 4 vCPU, 6 GB. make provision, doctor, quick and bench-all (incl. isolation.sh) all pass. Findings from that run:
the cri-o 1.37 deb ships conmon, conmonrs, crun and its own runc in /usr/libexec/crio, but not crictl (installed from pkgs.k8s.io) and no files in /usr/bin besides crio and pinns
a crio.conf.d drop-in replaces the whole runtime handler table, so 90-bench.conf.j2 must restate monitor_path (crio refused to start without it)
crio status config output still matches doctor.sh's parser; pods start fine with the systemd cgroup manager
Ubuntu 26.04 ships sudo-rs: `sudo -E` prints a warning and is ignored, but VAR=value arguments still reach the scripts
Findings so far (from the article runs)
Medians on a 2 vCPU cloud VM: containerd 100 ms, CRI-O 129 ms, Docker 153 ms (167 ms with bridge), new CRI-O pod 243 ms, runc alone 27 ms.
Docker's extra ~50 ms over containerd: about 20 ms from its heavier CLI and about 30 ms from dockerd.
Memory with 20 containers: Docker 240 MB, containerd 140 MB, CRI-O 87 MB. The Go shim is ~4.2 MB per container; the C conmon is ~0.4 MB.
Running all daemons side by side changed medians by at most ~5 ms. Run-to-run drift on the same VM was ~20%, so compare the ranking, not absolute numbers.
Conventions
No co-author or AI attribution lines in commits.
Short, plain docs. Results stay out of git (results/ is ignored).