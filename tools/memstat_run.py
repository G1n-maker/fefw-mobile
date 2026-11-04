#!/usr/bin/env python3
"""Where does the memory actually go? Read-only, changes nothing.

Runs the game to its worst memory point (the prologue, which peaked at 6.06 GB
resident) with DM_MEMSTAT, then reports the breakdown by region class so the
question "what could be freed" has an answer with numbers.

    tools/memstat_run.py [--seconds 300]
"""
import os, sys, time, pathlib, subprocess, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
OUT = ROOT / "work/memstat.tsv"
LOG = ROOT / "work/logs/memstat.log"
CTL = ROOT / "work/ctl_memstat.txt"

PLAN = ["A", "A", "A", "Right", "A", "A", "Down", "A", "A", "A", "Left", "A",
        "A", "Up", "A", "A", "A", "A", "B", "A", "A", "Right", "Right", "A"]


def send(l):
    with open(CTL, "a") as f:
        f.write(l + "\n")


def main():
    secs = 300.0
    a = sys.argv[1:]
    if "--seconds" in a:
        secs = float(a[a.index("--seconds") + 1])
    CTL.write_text("")
    OUT.unlink(missing_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "DM_ROOT": str(B), "DM_ROMFS": str(B / "extract/v0/RomFS.img"),
        "DM_SAVE": str(B / "run/save"), "DM_TEMP": str(B / "run/temp"),
        "DM_MSL_DIR": str(B / "shader/cache"), "DM_FONT_DIR": str(B / "font"),
        "DM_NVN_SHMAP": str(B / "profile/04007EF01F8AE000/shader_map.tsv"),
        "DM_LANG": "zh-Hans", "DM_AUDIO": "0", "DM_CTL": str(CTL),
        "DM_MEMSTAT": str(OUT),
        "DM_MEMSTAT_DUMP": "240",
    })
    log = open(LOG, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    print(f"host {p.pid}, memstat -> {OUT}", flush=True)
    time.sleep(50)
    t0 = time.time()
    i = 0
    while time.time() - t0 < secs:
        send(PLAN[i % len(PLAN)])
        i += 1
        time.sleep(1.05)
    os.kill(p.pid, 15)
    time.sleep(3)
    report()


def report():
    if not OUT.is_file():
        print("no memstat written"); return
    lines = [l for l in OUT.read_text(errors="ignore").splitlines() if l.strip()]
    if not lines:
        print("memstat empty"); return
    header = lines[0].split("\t")
    print("\ncolumns:", header)
    rows = [dict(zip(header, l.split("\t"))) for l in lines[1:]]

    def num(r, k):
        try: return float(r.get(k, 0) or 0)
        except ValueError: return 0.0

    peak = max(rows, key=lambda r: num(r, "footprint_mib") or num(r, "footprint") or 0)
    print("\n--- peak sample ---")
    for k, v in peak.items():
        if v not in ("", None): print(f"  {k:26} {v}")


main()
