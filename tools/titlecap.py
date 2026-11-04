#!/usr/bin/env python3
"""Stop at the title screen (Layout/Title.arc) and capture it.

FINDINGS 14c has the route: Title.arc opens around t=256 s / press 220 with a
mixed press plan. This runs that plan and, the moment Title.arc is opened, grabs
several frames a second apart so the title is captured even if it animates.

    work/titlecap.py [--keep 6]
"""
import os, re, sys, time, pathlib, subprocess
import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
CTL = ROOT / "work/ctl_title.txt"
LOG = ROOT / "work/logs/titlecap.log"
SHOTS = ROOT / "work/shots"

PLAN = ["A", "A", "A", "Right", "A", "A", "Down", "A", "A", "A", "Left", "A",
        "A", "Up", "A", "A", "A", "A", "B", "A", "A", "Right", "Right", "A"]


def send(l):
    with open(CTL, "a") as f:
        f.write(l + "\n")


def main():
    keep = 6
    a = sys.argv[1:]
    if "--keep" in a:
        keep = int(a[a.index("--keep") + 1])
    CTL.write_text("")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "DM_ROOT": str(B), "DM_ROMFS": str(B / "extract/v0/RomFS.img"),
        "DM_SAVE": str(B / "run/save"), "DM_TEMP": str(B / "run/temp"),
        "DM_MSL_DIR": str(B / "shader/cache"), "DM_FONT_DIR": str(B / "font"),
        "DM_NVN_SHMAP": str(B / "profile/04007EF01F8AE000/shader_map.tsv"),
        "DM_LANG": "zh-Hans", "DM_AUDIO": "0", "DM_CTL": str(CTL),
        "DM_FS": "1",
    })
    log = open(LOG, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    print(f"host {p.pid}", flush=True)
    time.sleep(52)

    t0 = time.time()
    i = 0
    # run to Gmap first, then to Title
    while time.time() - t0 < 420:
        send(PLAN[i % len(PLAN)])
        i += 1
        time.sleep(1.1)
        txt = LOG.read_text(errors="ignore")
        if "Layout/Title.arc" in txt:
            print(f"Title.arc opened at press {i}, t={time.time()-t0:.0f}s — capturing", flush=True)
            break
    else:
        print("Title.arc never opened", flush=True)

    best = None
    for k in range(keep):
        out = SHOTS / f"title_{k}.png"
        out.unlink(missing_ok=True)
        send(f"shot {out}")
        time.sleep(1.6)
        if not out.is_file():
            continue
        v = np.asarray(Image.open(out).convert("RGB").crop((0, 0, 2048, 1152)))
        nz = int(np.any(v != 0, axis=2).sum())
        ncol = len(np.unique(v.reshape(-1, 3), axis=0))
        print(f"  title_{k}: nonzero {nz:>8} colors {ncol:>7}", flush=True)
        Image.fromarray(v).resize((640, 360)).save(SHOTS / f"title_{k}_t.png")
        if best is None or ncol > best[1]:
            best = (out, ncol)

    os.kill(p.pid, 15)
    time.sleep(2)
    if best:
        print(f"\nmost colourful: {best[0].name} ({best[1]} colours)")
    txt = LOG.read_text(errors="ignore")
    print("layouts:", [m for m in dict.fromkeys(re.findall(r"Contents:/Layout/([A-Za-z0-9_]+)\.arc", txt))])
    print("RED:", txt.count("[RED]"))


main()
