#!/usr/bin/env python3
"""Ten-minute memory soak: does `footprint` grow without bound?

Advances the game (so scenes load, which is where a leak would show) and samples
the footprint the graphics layer reports every ~5 s, then fits a line to the
second half so "grows" is a number, not an impression.

    work/mem_soak.py [--minutes 10]
"""
import os, sys, time, pathlib, subprocess, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
CTL = ROOT / "work/ctl_mem.txt"
LOG = ROOT / "work/logs/mem_soak.log"


def send(line):
    with open(CTL, "a") as f:
        f.write(line + "\n")


def footprints(txt):
    """(frame, MiB) from both the on-screen and the memory readouts."""
    out = []
    for m in re.finditer(r"on-screen up to frame (\d+):[^\n]*footprint (\d+) MiB", txt):
        out.append((int(m.group(1)), int(m.group(2))))
    for m in re.finditer(r"memory up to frame (\d+): resident (\d+) MB", txt):
        out.append((int(m.group(1)), int(m.group(2))))
    return sorted(set(out))


def main():
    mins = 10.0
    a = sys.argv[1:]
    if "--minutes" in a:
        mins = float(a[a.index("--minutes") + 1])
    CTL.write_text("")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "DM_ROOT": str(B), "DM_ROMFS": str(B / "extract/v0/RomFS.img"),
        "DM_SAVE": str(B / "run/save"), "DM_TEMP": str(B / "run/temp"),
        "DM_MSL_DIR": str(B / "shader/cache"), "DM_FONT_DIR": str(B / "font"),
        "DM_NVN_SHMAP": str(B / "profile/04007EF01F8AE000/shader_map.tsv"),
        "DM_LANG": "zh-Hans", "DM_AUDIO": "0", "DM_CTL": str(CTL),
    })
    log = open(LOG, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    print(f"host {p.pid}, soak {mins:g} min", flush=True)
    time.sleep(50)                       # boot
    t0 = time.time()
    while time.time() - t0 < mins * 60:
        send("A")                        # keep the game moving: new scenes = new textures
        time.sleep(2.0)
    os.kill(p.pid, 15)
    time.sleep(3)

    txt = LOG.read_text(errors="ignore")
    fp = footprints(txt)
    print(f"\n{len(fp)} samples")
    for f, m in fp:
        print(f"  frame {f:>7}  {m:>5} MiB")
    if len(fp) >= 4:
        half = fp[len(fp) // 2:]
        n = len(half)
        xs = list(range(n))
        ys = [m for _, m in half]
        mx = sum(xs) / n
        my = sum(ys) / n
        den = sum((x - mx) ** 2 for x in xs) or 1
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
        # slope is MiB per sample; samples are ~5 s apart
        frames = [f for f, _ in half]
        dfr = (frames[-1] - frames[0]) / max(1, n - 1)
        per_min = slope * (60.0 * 60.0 / max(1.0, dfr))     # 60 fps
        print(f"\nsecond half: {ys[0]} -> {ys[-1]} MiB over {frames[-1]-frames[0]} frames")
        print(f"slope {slope:+.2f} MiB/sample ~ {per_min:+.1f} MiB/min at 60 fps")
        print("verdict:", "GROWS — look for a leak" if per_min > 5 else "flat (growth under 5 MiB/min)")
    print("\nRED lines:", txt.count("[RED]"))


main()
