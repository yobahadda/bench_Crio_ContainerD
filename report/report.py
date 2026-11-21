#!/usr/bin/env python3
"""
Turn a results directory into charts (SVG + PNG) and a markdown summary.

  python3 report/report.py results/<run>

Reads latency.json, overhead.json, memory.json, env.json (any may be missing).
PNG rendering uses rsvg-convert if present; SVGs are always written.
"""
import json
import os
import shutil
import subprocess
import sys

PAPER, INK, INK2, INK3, RULE, RED, GREY = "#f5f1e8", "#1c1b19", "#5b5750", "#8f897d", "#d9d2c3", "#d1402a", "#9a9384"
SERIF = "Lora, Noto Serif, DejaVu Serif, serif"
SANS = "Inter, DejaVu Sans, sans-serif"
MONO = "DejaVu Sans Mono, monospace"
DOCKER_KEYS = {"docker", "docker-bridge"}
RUNTIME = {"runc": "runc", "ctr": "containerd", "docker": "Docker", "docker-bridge": "Docker",
           "crio": "CRI-O", "crio-pod": "CRI-O", "crio-crun": "CRI-O with crun"}


def load(run, name):
    path = os.path.join(run, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []
        self.add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">')
        self.add('<defs><pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                 f'<rect width="8" height="8" fill="{PAPER}"/><rect width="2.2" height="8" fill="{INK}"/></pattern></defs>')
        self.add(f'<rect width="{w}" height="{h}" fill="{PAPER}"/>')

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, t, size=18, fill=INK, font=SANS, weight=400, anchor="start", style="normal"):
        t = str(t).replace("&", "&amp;").replace("<", "&lt;")
        self.add(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
                 f'font-style="{style}" fill="{fill}" text-anchor="{anchor}">{t}</text>')

    def rule(self, y, color=INK, width=2):
        self.add(f'<line x1="80" y1="{y}" x2="{self.w - 80}" y2="{y}" stroke="{color}" stroke-width="{width}"/>')

    def header(self, title, *lines):
        self.text(80, 104, title, 44, font=SERIF, weight=700)
        for i, line in enumerate(lines):
            self.text(80, 150 + 30 * i, line, 20, INK2)
        self.rule(232)

    def footer(self, *lines):
        self.rule(self.h - 92, RULE, 1.5)
        for i, line in enumerate(lines):
            self.text(80, self.h - 60 + 24 * i, line, 15, INK3)

    def save(self, base):
        self.add("</svg>")
        with open(base + ".svg", "w") as f:
            f.write("\n".join(self.parts))
        if shutil.which("rsvg-convert"):
            subprocess.run(["rsvg-convert", "-z", "1.375", "-o", base + ".png", base + ".svg"], check=True)


def env_line(env):
    if not env:
        return ""
    v = env.get("versions", {})
    return (f"{env.get('os', '')}, {env.get('arch', '')}, {env.get('cpus', '?')} vCPU, {env.get('virtualization', '')} · "
            f"Docker {v.get('docker', '?')} · CRI-O {v.get('crio', '?')} · {v.get('runc', '')}")


def latency_chart(run, lat, env):
    s = lat["summary"]
    keys = list(s)
    hi = max(v["p95"] for v in s.values())
    top = max(50, int(hi / 50 + 1) * 50)
    fastest = min((k for k in keys if k != "runc"), key=lambda k: s[k]["median"], default=keys[0])
    slowest_docker = max((k for k in keys if k in DOCKER_KEYS), key=lambda k: s[k]["median"], default=None)
    title = f"{RUNTIME.get(fastest, fastest)} starts fastest"
    if slowest_docker and slowest_docker == max((k for k in keys if k != "crio-pod"), key=lambda k: s[k]["median"]):
        title += ". Docker is last."
    rh, ty = 80, 290
    svg = Svg(1600, ty + rh * len(keys) + 150)
    runc_note = "the same runc binary (except the crun row)" if "crio-crun" in s else "the same runc binary"
    svg.header(title, f"Time until the container is running, {lat['rounds']} runs each. Dot = median, line = 95th percentile.",
               f"Docker variants in red. Every variant uses {runc_note} and the same image.")
    lx, rx = 620, 1480
    xs = lambda v: lx + v / top * (rx - lx)
    step = 50 if top <= 400 else 100
    for v in range(0, top + 1, step):
        svg.add(f'<line x1="{xs(v)}" y1="{ty - 30}" x2="{xs(v)}" y2="{ty + rh * len(keys) - 40}" stroke="{RULE}" stroke-width="1.5"/>')
        svg.text(xs(v), ty + rh * len(keys) - 10, f"{v} ms" if v == top else v, 16, INK3, MONO, anchor="middle")
    for i, k in enumerate(keys):
        y, st = ty + i * rh, s[k]
        col = RED if k in DOCKER_KEYS else INK
        svg.text(80, y + 7, st["label"], 19, INK, SANS, 600)
        svg.add(f'<line x1="{xs(st["median"])}" y1="{y}" x2="{xs(st["p95"])}" y2="{y}" stroke="{col}" stroke-width="4" stroke-linecap="round"/>')
        svg.add(f'<circle cx="{xs(st["median"])}" cy="{y}" r="11" fill="{col}" stroke="{PAPER}" stroke-width="3"/>')
        svg.text(xs(st["median"]) - 20, y + 8, f'{st["median"]:.0f}', 22, col, SERIF, 700, anchor="end")
    svg.footer("Includes each CLI's own startup time.", env_line(env))
    svg.save(os.path.join(run, "chart-latency"))
    return slowest_docker


def anatomy_chart(run, lat, over, env):
    s = lat["summary"]
    if not over or not {"runc", "ctr", "docker", "crio"} <= set(s):
        return False
    runc = s["runc"]["median"]
    cli = {k: v["median"] for k, v in over["cli_startup"].items()}
    api = over["docker_api"]["none"]["median"]
    ctrd = max(s["ctr"]["median"] - cli["ctr"] - runc, 0)
    rows = [
        ("containerd", "ctr run", s["ctr"]["median"], [("runc", runc), ("containerd + shim", ctrd), ("CLI", cli["ctr"])]),
        ("CRI-O", "crictl create + start, in a pod", s["crio"]["median"],
         [("runc", runc), ("crio + conmon", max(s["crio"]["median"] - 2 * cli["crictl"] - runc, 0)), ("CLI", 2 * cli["crictl"])]),
        ("Docker", "docker run --network none", s["docker"]["median"],
         [("runc", runc), ("containerd + shim", ctrd), ("dockerd", max(api - runc - ctrd, 0)),
          ("CLI", max(s["docker"]["median"] - api, 0))]),
    ]
    fill = {"runc": INK, "containerd + shim": GREY, "crio + conmon": GREY, "dockerd": RED, "CLI": "url(#hatch)"}
    longest = max(r[2] for r in rows)
    px = 1100 / longest
    svg = Svg(1600, 900)
    svg.header("Where the milliseconds go",
               f"Median start time split by layer. runc does the same {runc:.0f} ms of work every time;",
               "everything else is the cost of the layers stacked in front of it.")
    for i, (name, how, total, segs) in enumerate(rows):
        y = 300 + i * 168
        svg.text(80, y - 22, name, 26, font=SERIF, weight=700)
        svg.text(80 + len(name) * 16 + 16, y - 23, how, 17, INK3, MONO)
        x = 80
        for label, ms in segs:
            w = ms * px
            stroke = f' stroke="{INK}" stroke-width="2"' if label == "CLI" else ""
            svg.add(f'<rect x="{x:.1f}" y="{y}" width="{max(w - 3, 1):.1f}" height="64" fill="{fill[label]}"{stroke}/>')
            if label != "CLI" and w > 110:
                svg.text(x + 14, y + 28, label, 16, PAPER, SANS, 600)
                svg.text(x + 14, y + 51, f"{ms:.0f} ms", 16, PAPER, MONO)
            if label == "dockerd":
                svg.text(x + w / 2, y + 92, f"Docker's extra layer: +{ms:.0f} ms", 17, RED, SANS, 600, anchor="middle")
            x += w
        svg.text(x - segs[-1][1] * px / 2, y + 88 if name != "Docker" else y + 118, f"CLI {segs[-1][1]:.0f} ms", 15, INK2, MONO, anchor="middle")
        svg.text(x + 18, y + 46, f"{total:.0f} ms", 36, font=SERIF, weight=700)
    svg.footer("Estimated split. CLI cost: each CLI timed alone and Docker's Engine API called directly. runc: timed alone. Daemons: the remainder.",
               env_line(env))
    svg.save(os.path.join(run, "chart-anatomy"))
    return True


def memory_chart(run, mem, env):
    n = mem["n"]
    blocks = [
        ("Docker", [("dockerd", round(mem["docker"]["dockerd_mb"]), RED, True),
                    ("containerd", round(mem["docker"]["containerd_mb"]), GREY, True),
                    (f"{n} shims", round(mem["docker"]["helpers_mb"]), INK, False)]),
        ("containerd", [("containerd", round(mem["containerd"]["containerd_mb"]), GREY, True),
                        (f"{n} shims", round(mem["containerd"]["helpers_mb"]), INK, False)]),
        ("CRI-O", [("crio", round(mem["crio"]["crio_mb"]), GREY, True),
                   (f"{n} conmons", round(mem["crio"]["helpers_mb"]), INK, False)]),
    ]
    cols, sq, gap = 20, 18, 4
    rows_needed = max(-(-sum(p[1] for p in parts) // cols) for _, parts in blocks)
    unit = 1 if rows_needed <= 16 else -(-rows_needed // 16)          # MB per square, keeps the grid on the page
    bw, top = cols * (sq + gap), 300
    grid_rows = max(-(-sum(-(-p[1] // unit) for p in parts) // cols) for _, parts in blocks)
    svg = Svg(1600, top + grid_rows * (sq + gap) + 220)
    svg.header(f"Every square is {'one megabyte' if unit == 1 else f'{unit} MB'}",
               f"Memory (PSS) with {n} idle containers. Filled squares are daemons; outlined squares are the",
               "helper process each container gets: a Go shim for containerd, a C conmon for CRI-O.")
    for b, (name, parts) in enumerate(blocks):
        bx = 80 + b * (bw + 60)
        total = sum(p[1] for p in parts)
        svg.text(bx, top - 22, name, 26, font=SERIF, weight=700)
        svg.text(bx + bw, top - 20, f"{total} MB", 30, font=SERIF, weight=700, anchor="end")
        i = 0
        for _, count, col, filled in parts:
            for _ in range(-(-count // unit)):
                r, c = divmod(i, cols)
                x, y = bx + c * (sq + gap), top + r * (sq + gap)
                if filled:
                    svg.add(f'<rect x="{x}" y="{y}" width="{sq}" height="{sq}" fill="{col}"/>')
                else:
                    svg.add(f'<rect x="{x + 1}" y="{y + 1}" width="{sq - 2}" height="{sq - 2}" fill="none" stroke="{INK}" stroke-width="2"/>')
                i += 1
        lx, ly = bx, top + grid_rows * (sq + gap) + 34
        for label, count, col, filled in parts:
            if filled:
                svg.add(f'<rect x="{lx}" y="{ly - 13}" width="14" height="14" fill="{col}"/>')
            else:
                svg.add(f'<rect x="{lx + 1}" y="{ly - 12}" width="12" height="12" fill="none" stroke="{INK}" stroke-width="2"/>')
            t = f"{label} {count}"
            svg.text(lx + 22, ly, t, 16, INK2, MONO)
            lx += 22 + len(t) * 9.7 + 18
    svg.footer("Under Kubernetes, containerd runs one shim per pod, not per container. CRI-O's pod sandbox conmon is excluded.",
               env_line(env))
    svg.save(os.path.join(run, "chart-memory"))


def summary_md(run, env, lat, over, mem):
    out = ["# Benchmark results", ""]
    if env:
        v = env["versions"]
        out += [f"- **Machine:** {env['os']}, {env['arch']}, {env['cpus']} vCPU ({env.get('cpu_model', '')}), "
                f"{env['mem_mb']} MB RAM, {env['virtualization']}, cgroup fs `{env['cgroup_fs']}`",
                f"- **Versions:** Docker {v['docker']} · {v['containerd']} · CRI-O {v['crio']} · {v['runc']}",
                f"- **Date:** {env['date']}", ""]
    if lat:
        out += ["## Start latency", "", "| Variant | Median | p95 | Stdev |", "| --- | ---: | ---: | ---: |"]
        out += [f"| {s['label']} | {s['median']:.1f} ms | {s['p95']:.1f} ms | {s['stdev']:.1f} ms |" for s in lat["summary"].values()]
        out.append("")
    if over:
        out += ["## Docker overhead split", "",
                f"- Engine API create+start: {over['docker_api']['none']['median']:.1f} ms (no network), "
                f"{over['docker_api']['bridge']['median']:.1f} ms (bridge)"]
        out += [f"- `{k}` CLI startup: {v['median']:.1f} ms" for k, v in over["cli_startup"].items()]
        out.append("")
    if mem:
        n = mem["n"]
        out += [f"## Memory with {n} containers (PSS)", "", "| Runtime | Daemon(s) | Helpers | Total |", "| --- | ---: | ---: | ---: |"]
        d = mem["docker"]
        out.append(f"| Docker | {d['dockerd_mb'] + d['containerd_mb']:.1f} MB | {d['helpers_mb']:.1f} MB | {d['dockerd_mb'] + d['containerd_mb'] + d['helpers_mb']:.1f} MB |")
        c = mem["containerd"]
        out.append(f"| containerd | {c['containerd_mb']:.1f} MB | {c['helpers_mb']:.1f} MB | {c['containerd_mb'] + c['helpers_mb']:.1f} MB |")
        o = mem["crio"]
        out.append(f"| CRI-O | {o['crio_mb']:.1f} MB | {o['helpers_mb']:.1f} MB | {o['crio_mb'] + o['helpers_mb']:.1f} MB |")
        out.append("")
    iso_dir = os.path.join(run, "isolation")
    if os.path.isdir(iso_dir):
        out += ["## Isolation (all daemons vs alone), medians", "", "| Variant | All (1) | Alone | All (2) |", "| --- | ---: | ---: | ---: |"]
        a1, a2 = load(iso_dir, "all-1.json"), load(iso_dir, "all-2.json")
        for key, alone in (("ctr", "ctr-alone.json"), ("docker", "docker-alone.json"), ("crio", "crio-alone.json")):
            al = load(iso_dir, alone)
            if a1 and a2 and al:
                out.append(f"| {a1['summary'][key]['label']} | {a1['summary'][key]['median']:.1f} | "
                           f"{al['summary'][key]['median']:.1f} | {a2['summary'][key]['median']:.1f} |")
        out.append("")
    charts = [f for f in ("chart-latency", "chart-anatomy", "chart-memory") if os.path.exists(os.path.join(run, f + ".svg"))]
    if charts:
        ext = ".png" if os.path.exists(os.path.join(run, charts[0] + ".png")) else ".svg"
        out += ["## Charts", ""] + [f"![{c}]({c}{ext})" for c in charts]
    with open(os.path.join(run, "summary.md"), "w") as f:
        f.write("\n".join(out) + "\n")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    run = sys.argv[1]
    env, lat, over, mem = (load(run, n) for n in ("env.json", "latency.json", "overhead.json", "memory.json"))
    if lat:
        latency_chart(run, lat, env)
        anatomy_chart(run, lat, over, env)
    if mem:
        memory_chart(run, mem, env)
    summary_md(run, env, lat, over, mem)
    print(f"report written to {run}/summary.md")


if __name__ == "__main__":
    main()
