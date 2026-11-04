#!/usr/bin/env python3
"""Get into a battle: the naming screen needs DM_KBD, and then CHECK must be confirmed.

Root cause of the earlier dead end (FINDINGS 14c): the character-name entry is a
system software keyboard, and on the Mac with no window the host answers it as
*cancel*:

    swkbd: title '请决定名字…' initial '' limit 8 min 0 → no window, treated as cancel

so the flow can never pass NAME. The host already supports answering it —
DM_KBD=<text> returns that text as OK — which is the switch this run uses.

    work/tobattle2.py [--name Zephyr] [--minutes 10]
"""
import os, re, sys, time, pathlib, subprocess
import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
CTL = ROOT / "work/ctl_bt2.txt"
LOG = ROOT / "work/logs/bt2.log"
SHOTS = ROOT / "work/shots"

PLAN = ["A", "A", "A", "Right", "A", "A", "Down", "A", "A", "A", "Left", "A",
        "A", "Up", "A", "A", "A", "A", "B", "A", "A", "Right", "Right", "A"]


def send(l):
    with open(CTL, "a") as f:
        f.write(l + "\n")


def vis(p):
    return np.asarray(Image.open(p).convert("RGB").crop((0, 0, 2048, 1152)))


def main():
    name = "Zephyr"
    mins = 10.0
    a = sys.argv[1:]
    for i, v in enumerate(a):
        if v == "--name": name = a[i + 1]
        if v == "--minutes": mins = float(a[i + 1])
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
        "DM_KBD": name,              # answer the software keyboard instead of cancelling
    })
    log = open(LOG, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    print(f"host {p.pid}, DM_KBD={name}", flush=True)
    time.sleep(52)

    t0 = time.time()
    i = 0
    seen = []
    # to UnitMake
    while time.time() - t0 < 340:
        send(PLAN[i % len(PLAN)])
        i += 1
        time.sleep(1.05)
        txt = LOG.read_text(errors="ignore")
        if "UnitMake.arc" in txt:
            break
    print(f"UnitMake at press {i}, t={time.time()-t0:.0f}s", flush=True)
    time.sleep(5)

    # walk the creator: BODY SKIN HEAD HAIR CLOTHES -> NAME (keyboard) -> CHECK
    for step in range(60):
        send("A")
        time.sleep(1.05)
        txt = LOG.read_text(errors="ignore")
        for n in re.findall(r"Contents:/Layout/([A-Za-z0-9_]+)\.arc", txt):
            if n not in seen:
                seen.append(n)
                print(f"  + {n}", flush=True)
        if "swkbd: title" in txt and "OK '" not in txt:
            print("  swkbd answered", flush=True)
        if "Battle.arc" in txt:
            print(f"BATTLE.arc at step {step}, t={time.time()-t0:.0f}s", flush=True)
            break

    for k in range(4):
        out = SHOTS / f"bt2_{k}.png"
        out.unlink(missing_ok=True)
        send(f"shot {out}")
        time.sleep(2.0)
        if out.is_file():
            v = vis(out)
            print(f"  bt2_{k}: nonzero {int(np.any(v!=0,axis=2).sum())} colors {len(np.unique(v.reshape(-1,3),axis=0))}", flush=True)
            Image.fromarray(v).resize((640, 360)).save(SHOTS / f"bt2_{k}_t.png")

    end = time.time() + mins * 60
    while time.time() < end and "Battle.arc" not in LOG.read_text(errors="ignore"):
        send("A")
        time.sleep(1.1)
    os.kill(p.pid, 15)
    time.sleep(2)
    txt = LOG.read_text(errors="ignore")
    print("\nlayouts:", " -> ".join(dict.fromkeys(re.findall(r"Contents:/Layout/([A-Za-z0-9_]+)\.arc", txt))))
    print("swkbd lines:", [l[5:120] for l in txt.splitlines() if "swkbd:" in l][:4])
    print("Battle:", "Battle.arc" in txt)
    print("save files:", [q.name for q in (B / "run/save").rglob("*") if q.is_file()][:8])
    print("RED:", txt.count("[RED]"))


main()
