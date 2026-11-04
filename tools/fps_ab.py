#!/usr/bin/env python3
"""Compare fps_target 30 against 60 on the same route.

The host raises this game's own target (30) to the profile's 60. Both are legal:
the game's gxc object holds the rate, its present asks for 60/target. What
differs is what the player gets, so measure both: frame time, presents served,
dropped frames, GPU time, and any change in what the game asks for.

    work/fps_ab.py [--seconds 70]
"""
import os, re, sys, time, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"


def run(tag, target):
    ctl = ROOT / f"work/ctl_fps_{tag}.txt"
    log = ROOT / f"work/logs/fps_{tag}.log"
    ctl.write_text("")
    env = dict(os.environ)
    env.update({
        "DM_ROOT": str(B), "DM_ROMFS": str(B / "extract/v0/RomFS.img"),
        "DM_SAVE": str(B / "run/save"), "DM_TEMP": str(B / "run/temp"),
        "DM_MSL_DIR": str(B / "shader/cache"), "DM_FONT_DIR": str(B / "font"),
        "DM_NVN_SHMAP": str(B / "profile/04007EF01F8AE000/shader_map.tsv"),
        "DM_LANG": "zh-Hans", "DM_AUDIO": "0", "DM_CTL": str(ctl),
        "DM_FPS_TARGET": str(target),
    })
    f = open(log, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=f,
                         stderr=subprocess.STDOUT, start_new_session=True)
    secs = 70.0
    a = sys.argv[1:]
    if "--seconds" in a:
        secs = float(a[a.index("--seconds") + 1])
    time.sleep(48)
    t0 = time.time()
    while time.time() - t0 < secs:
        with open(ctl, "a") as g:
            g.write("A\n")
        time.sleep(1.6)
    os.kill(p.pid, 15)
    time.sleep(3)
    return log


def stats(log):
    t = log.read_text(errors="ignore")
    out = {}
    out["target line"] = (re.findall(r"target frame rate (\d+) → (\d+) fps", t) or [("?", "?")])[0]
    ft = re.findall(r"frame time p50 ([\d.]+) / p95 ([\d.]+) / max ([\d.]+) ms", t)
    if ft:
        out["frame time p50 (first/last)"] = f"{ft[0][0]} / {ft[-1][0]} ms"
        out["frame time p95 (last)"] = f"{ft[-1][1]} ms"
    gp = re.findall(r"GPU p50 ([\d.]+)", t)
    if gp:
        out["GPU p50 (first/last)"] = f"{gp[0]} / {gp[-1]} ms"
    dr = re.findall(r"on-screen up to frame \d+: 300 frames, dropped (\d+)", t)
    if dr:
        out["dropped per 300 (mean)"] = f"{sum(map(int, dr))/len(dr):.1f}"
    fps = re.findall(r"\(([\d.]+) fps\)", t)
    if fps:
        out["measured fps (first/last)"] = f"{fps[0]} / {fps[-1]}"
    piv = re.findall(r"present interval (\d) → (\d)", t)
    out["present interval changes"] = str(piv) if piv else "none"
    out["RED"] = t.count("[RED]")
    return out


def main():
    for target in (30, 60):
        log = run(str(target), target)
        print(f"\n=== fps_target {target} ===")
        for k, v in stats(log).items():
            print(f"  {k:32} {v}")


main()
