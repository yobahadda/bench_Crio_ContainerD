# Setting up the VM in UTM

These steps target UTM on macOS, but any hypervisor works if you follow the same settings.

## 1. Get Ubuntu Server

Download **Ubuntu Server 26.04 LTS** (or 26.10) from <https://ubuntu.com/download/server>:

- Apple Silicon Mac: the **ARM64** image
- Intel Mac or PC: the **AMD64** image

Server is enough. A desktop session only adds background noise to the benchmark.

## 2. Create the VM

In UTM: **Create a New Virtual Machine → Virtualize → Linux**.

| Setting | Value | Why |
| --- | --- | --- |
| Mode | **Virtualize**, never Emulate | Emulation is 10–50× slower and makes every number meaningless |
| CPU cores | 4 (at least 2) | Leaves headroom for the daemons |
| Memory | 4–8 GB | Memory tests start 20 containers per runtime |
| Disk | 20 GB | Three image stores plus packages |
| Network | Shared Network | Gives the VM internet access and an IP your Mac can reach |

If UTM offers it, use the Apple Virtualization backend. It's usually faster than QEMU with hardware acceleration.

## 3. Install Ubuntu

Accept the defaults, and tick **Install OpenSSH server**. After the first boot:

```bash
sudo apt update && sudo apt full-upgrade -y && sudo reboot
ip -4 addr show | grep inet    # note the VM's IP if you want to SSH in from your Mac
```

## 4. Provision and run

```bash
sudo apt install -y git make
git clone https://github.com/yobahadda/bench_Crio_ContainerD.git
cd bench_Crio_ContainerD
make provision
make doctor
make bench
```

## Tips for clean numbers

- Close heavy apps on the host while the benchmark runs. The VM shares the host's CPUs.
- Keep the Mac plugged in: battery mode slows the CPU down.
- Run the suite twice. If the two runs disagree a lot, the host was busy.
- Compare runs from the same machine only. Absolute numbers between machines are not comparable; the ranking usually is.
