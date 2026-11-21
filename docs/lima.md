# Setting up the VM with Lima (macOS)

[Lima](https://lima-vm.io) runs a Linux VM from the command line, with SSH set up for you. On Apple Silicon it uses Apple's Virtualization framework, so there is no emulation.

## 1. Create the VM

```bash
brew install lima
limactl create --name=bench --vm-type=vz --cpus=4 --memory=6 --disk=20 \
  --containerd=none --mount-none --tty=false template:ubuntu-26.04
limactl start bench
```

`--containerd=none` stops Lima from starting its own containerd, and `--mount-none` skips the shared folders. Both would add noise to the benchmark.

## 2. Provision and run

```bash
limactl shell bench
# now inside the VM:
sudo apt-get update && sudo apt-get install -y git make
git clone https://github.com/yobahadda/bench_Crio_ContainerD.git
cd bench_Crio_ContainerD
make provision
make doctor
make bench
```

## 3. Get the results

Inside the VM your home is `/home/<you>.guest`, not your Mac's home. `~` on the Mac side expands to the Mac path, so spell the VM path out:

```bash
limactl copy -r bench:/home/$USER.guest/bench_Crio_ContainerD/results/<run> results/
```

## Stop or remove the VM

```bash
limactl stop bench
limactl start bench
limactl delete bench
```

If you interrupt a run with Ctrl+C, remove the leftover containers before the next one:

```bash
sudo crictl rmp -fa
sudo docker rm -f $(sudo docker ps -aq) 2>/dev/null
sudo ctr -n bench c ls -q | xargs -r sudo ctr -n bench c rm
```
