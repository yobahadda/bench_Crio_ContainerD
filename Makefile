SHELL := /bin/bash
.DEFAULT_GOAL := help

RUN      ?= results/$(shell hostname)-$(shell date +%Y%m%d-%H%M%S)
ROUNDS   ?= 50
WARMUP   ?= 5
MEM_N    ?= 20
VARIANTS ?= runc,ctr,docker,docker-bridge,crio,crio-pod,crio-crun
SUDO     := $(if $(filter 0,$(shell id -u)),,sudo -E)
LAST     := $(shell ls -1dt results/*/ 2>/dev/null | head -1)

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

## ---- setup -------------------------------------------------------------
provision: ## Provision THIS machine (run inside the VM)
	$(SUDO) ./scripts/bootstrap.sh

provision-remote: ## Provision the VM over SSH from your host (needs ansible/inventory/remote.ini)
	cd ansible && ansible-playbook -i inventory/remote.ini site.yml --ask-become-pass

image: ## Rebuild the benchmark image and reload it into all runtimes
	$(SUDO) FORCE=1 ./image/build.sh

doctor: ## Check everything is installed, running and loaded
	$(SUDO) ./scripts/doctor.sh

## ---- benchmarks --------------------------------------------------------
bench: ## Run the full suite (latency, overhead, memory, report)
	$(SUDO) ROUNDS=$(ROUNDS) WARMUP=$(WARMUP) MEM_N=$(MEM_N) VARIANTS=$(VARIANTS) ./scripts/run-all.sh $(RUN)

bench-all: ## Full suite plus the all-daemons-vs-alone isolation test
	$(SUDO) ROUNDS=$(ROUNDS) WARMUP=$(WARMUP) MEM_N=$(MEM_N) VARIANTS=$(VARIANTS) ISOLATION=1 ./scripts/run-all.sh $(RUN)

latency: ## Start latency only
	$(SUDO) python3 bench/latency.py --rounds $(ROUNDS) --warmup $(WARMUP) --only $(VARIANTS) --out $(RUN)/latency.json

memory: ## Memory footprint only
	$(SUDO) python3 bench/memory.py --n $(MEM_N) --out $(RUN)/memory.json

quick: ## A 2-minute smoke run (10 rounds)
	$(MAKE) bench ROUNDS=10 WARMUP=2 MEM_N=5

report: ## Rebuild charts + summary for the latest run (or DIR=results/<run>)
	python3 report/report.py $(or $(DIR),$(LAST))

## ---- repo --------------------------------------------------------------
lint: ## Lint Ansible, YAML, shell and Python
	ansible-lint ansible/site.yml
	shellcheck scripts/*.sh image/build.sh
	python3 -m py_compile bench/*.py report/*.py

clean: ## Remove local results (keeps results/.gitkeep)
	find results -mindepth 1 -not -name .gitkeep -prune -exec rm -rf {} +

.PHONY: help provision provision-remote image doctor bench bench-all latency memory quick report lint clean
