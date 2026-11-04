#!/usr/bin/env python3
"""Step the parked session one key at a time, reporting what changed each time.

Sends one key, waits, screenshots, and prints the changed-pixel count and the
title text region so the caller can see whether the screen advanced. Stops when
the screen has advanced (a big change) or a Battle layout appears.

    work/step1.py [--key A] [--steps 40]
"""
import sys, time, pathlib, re
import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTL = ROOT / "work/ctl_park.txt"
LOG = ROOT / "work/logs/park.log"
SHOTS = ROOT / "work/shots"


def send(l):
    with open(CTL, "a") as f:
        f.write(l + "\n")


def grab(tag):
    out = SHOTS / f"{tag}.png"
    out.unlink(missing_ok=True)
    send(f"shot {out}")
    time.sleep(1.9)
    if not out.is_file():
        return None
    return np.asarray(Image.open(out).convert("RGB").crop((0, 0, 2048, 1152)))


def main():
    key, steps = "A", 40
    a = sys.argv[1:]
    for i, v in enumerate(a):
        if v == "--key": key = a[i + 1]
        if v == "--steps": steps = int(a[i + 1])
    prev = grab("step_base")
    if prev is None:
        print("no baseline"); return
    for s in range(steps):
        send(key)
        time.sleep(1.3)
        cur = grab("step_cur")
        if cur is None:
            continue
        ch = int((cur != prev).any(axis=2).sum())
        nz = int(np.any(cur != 0, axis=2).sum())
        ncol = len(np.unique(cur.reshape(-1, 3), axis=0))
        txt = LOG.read_text(errors="ignore")
        swk = "swkbd:OK" if "OK '" in txt else ("swkbd:cancel" if "treated as cancel" in txt else "")
        print(f"{s:02d} {key:5} changed {ch:>8}  nonzero {nz:>8}  colors {ncol:>7}  {swk}", flush=True)
        Image.fromarray(cur).resize((600, 338)).save(SHOTS / f"step_{s:02d}_t.png")
        if "Battle.arc" in txt:
            print("BATTLE reached", flush=True); return
        prev = cur


main()
