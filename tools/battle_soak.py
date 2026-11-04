#!/usr/bin/env python3
"""Long gameplay soak: does memory stay flat while units move and effects fire?

The 10-minute soak in FINDINGS 14e sat on a *menu*, and the battle reading was
lower than the prologue's (4.8 GB vs 6.6 GB). That inversion is worth explaining
before the iPhone target, whose memory ceiling is far tighter than a Mac's.

This parks a session, gets into the battle, then plays for --minutes while
sampling `resident`, the residency set, serial objects and pool count, so growth
is separable from scene loading.

    tools/battle_soak.py [--minutes 20] [--presses 300]
"""
import os, re, sys, time, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
CTL = ROOT / "work/ctl_soak.txt"
LOG = ROOT / "work/logs/battle_soak.log"

DRIVE = ["A", "A", "A", "Right", "A", "A", "Down", "A", "A", "A", "Left", "A",
         "A", "Up", "A", "A", "A", "A", "B", "A", "A", "Right", "Right", "A"]
# In battle: commit moves, confirm, and nudge the cursor so new tiles and units
# come into view. Directions matter, as on every earlier screen.
PLAY = ["A", "A", "Right", "A", "Down", "A", "A", "Left", "A", "Up", "A", "A",
        "Right", "Right", "A", "Down", "A", "A", "A", "Left", "A"]


def send(l):
    with open(CTL, "a") as f:
        f.write(l + "\n")


def mem_samples(txt):
    out = []
    for m in re.finditer(r"memory up to frame (\d+): resident (\d+) MB, GPU allocated (\d+) MB, "
                         r"deferred-release queue (\d+), residency set (\d+), serial objects (\d+), "
                         r"memory pools (\d+)", txt):
        out.append(tuple(int(g) for g in m.groups()))
    return out


def fit(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs) or 1
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def main():
    mins, _ = 20.0, 0
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
        "DM_FS": "1", "DM_KBD": "Soak",
    })
    log = open(LOG, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    print(f"host {p.pid}", flush=True)
    time.sleep(52)

    # 1. get into a battle
    t0 = time.time()
    i = 0
    while time.time() - t0 < 420:
        send(DRIVE[i % len(DRIVE)])
        i += 1
        time.sleep(1.05)
        if "Layout/Battle.arc" in LOG.read_text(errors="ignore"):
            break
    inbattle = "Layout/Battle.arc" in LOG.read_text(errors="ignore")
    print(f"battle at press {i}, t={time.time()-t0:.0f}s: {inbattle}", flush=True)
    if not inbattle:
        print("never reached Battle; soaking wherever it is anyway", flush=True)
    time.sleep(8)

    # 2. play in the battle, sampling memory as we go
    t1 = time.time()
    j = 0
    while time.time() - t1 < mins * 60:
        send(PLAY[j % len(PLAY)])
        j += 1
        time.sleep(1.5)
        if j % 20 == 0:
            s = mem_samples(LOG.read_text(errors="ignore"))
            if s:
                f, res, gpu, drq, rs, so, pools = s[-1]
                print(f"  t={time.time()-t1:6.0f}s frame {f:>6} resident {res:>5} MB "
                      f"GPU {gpu:>5} MB  res_set {rs:>5} serial {so:>5} pools {pools:>4}", flush=True)
    os.kill(p.pid, 15)
    time.sleep(3)

    txt = LOG.read_text(errors="ignore")
    s = mem_samples(txt)
    print(f"\n{len(s)} memory samples")
    if len(s) >= 6:
        # measure the second half: the first half is scene loading
        half = s[len(s) // 2:]
        fr = [x[0] for x in half]
        for label, idx in (("resident", 1), ("GPU allocated", 2), ("residency set", 4),
                           ("serial objects", 5), ("pools", 6)):
            ys = [x[idx] for x in half]
            per_1k = fit(fr, ys) * 1000
            print(f"  {label:14} {ys[0]:>6} -> {ys[-1]:>6}   slope {per_1k:+8.2f} per 1000 frames")
    ft = re.findall(r"timing up to frame \d+: frame time p50 ([\d.]+) / p95 ([\d.]+)", txt)
    if ft:
        print(f"\nframe time p50 {ft[-1][0]} p95 {ft[-1][1]} ms")
    dr = re.findall(r"(\d+) draws per frame", txt)
    if dr:
        print(f"draws per frame {min(map(int,dr))} .. {max(map(int,dr))}")
    print("effect archives:", len(set(re.findall(r"Contents:/Effect/", txt))))
    reds = [l for l in txt.splitlines() if "[RED]" in l]
    print(f"RED {len(reds)}")
    for l in reds:
        print("  " + l[5:150])


main()
