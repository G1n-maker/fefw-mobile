#!/usr/bin/env python3
"""Start a session and hold it at character creation, so keys can be sent one at a time.

The expensive part of every previous attempt was the 5-minute drive back to
UnitMake. DM_CTL exists for "look at a screen, decide, press, look again", so this
starts the host detached, drives it to the character creator once, and leaves it
running. Then `work/dmctl.py key X` / `shot` drive it a single step at a time and
the same process is reused.

    work/park.py            start and drive to UnitMake, then leave running
    work/park.py --status   report where it is
"""
import os, re, sys, time, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
CTL = ROOT / "work/ctl_park.txt"
LOG = ROOT / "work/logs/park.log"
PID = ROOT / "work/park.pid"

PLAN = ["A", "A", "A", "Right", "A", "A", "Down", "A", "A", "A", "Left", "A",
        "A", "Up", "A", "A", "A", "A", "B", "A", "A", "Right", "Right", "A"]


def send(l):
    with open(CTL, "a") as f:
        f.write(l + "\n")


def alive():
    try:
        pid = int(PID.read_text())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def status():
    if not LOG.is_file():
        print("no log")
        return
    t = LOG.read_text(errors="ignore")
    lay = [m for m in dict.fromkeys(re.findall(r"Contents:/Layout/([A-Za-z0-9_]+)\.arc", t))]
    print("pid:", alive() or "dead")
    print("layouts:", " -> ".join(lay))
    print("frames:", (re.findall(r"up to frame (\d+)", t) or ["?"])[-1])
    print("RED:", t.count("[RED]"))


def main():
    if "--status" in sys.argv:
        status()
        return
    if alive():
        print(f"already running: {alive()}"); status(); return
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
        "DM_KBD": os.environ.get("DM_KBD", "Zephyr"),   # answer the software keyboard (FINDINGS 14c)
    })
    log = open(LOG, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    PID.write_text(str(p.pid))
    print(f"host {p.pid}, driving to UnitMake (~290 s)", flush=True)
    time.sleep(52)
    t0 = time.time()
    i = 0
    while time.time() - t0 < 330:
        if "UnitMake.arc" in LOG.read_text(errors="ignore"):
            break
        send(PLAN[i % len(PLAN)])
        i += 1
        time.sleep(1.1)
    time.sleep(6)
    print(f"parked at UnitMake after {i} presses — host stays running", flush=True)
    status()


main()
