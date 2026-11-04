#!/usr/bin/env python3
"""Does `gpu_timestamps segment` change what this game decides?

DK Bananza's notes say its dynamic-resolution / frame-rate controller reads the
GPU time between its timestamp reports; with one time per whole submission it
reads ~0 and keeps a too-high resolution. This game reports 60 counters a frame
and flips its present interval 1 <-> 2, the same shape. Compare the two settings
on identical runs and report what the game asked for: present interval changes,
frame step cap changes, resolution, and frame time.

    work/gputs_ab.py [--seconds 90]
"""
import os, re, sys, time, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"


def run(tag, extra):
    ctl = ROOT / f"work/ctl_ts_{tag}.txt"
    log = ROOT / f"work/logs/ts_{tag}.log"
    ctl.write_text("")
    env = dict(os.environ)
    env.update({
        "DM_ROOT": str(B), "DM_ROMFS": str(B / "extract/v0/RomFS.img"),
        "DM_SAVE": str(B / "run/save"), "DM_TEMP": str(B / "run/temp"),
        "DM_MSL_DIR": str(B / "shader/cache"), "DM_FONT_DIR": str(B / "font"),
        "DM_NVN_SHMAP": str(B / "profile/04007EF01F8AE000/shader_map.tsv"),
        "DM_LANG": "zh-Hans", "DM_AUDIO": "0", "DM_CTL": str(ctl),
    })
    env.update(extra)
    f = open(log, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=f,
                         stderr=subprocess.STDOUT, start_new_session=True)
    secs = 90.0
    a = sys.argv[1:]
    if "--seconds" in a:
        secs = float(a[a.index("--seconds") + 1])
    time.sleep(50)
    t0 = time.time()
    while time.time() - t0 < secs:
        with open(ctl, "a") as g:
            g.write("A\n")
        time.sleep(1.6)
    os.kill(p.pid, 15)
    time.sleep(3)
    return log


def summarize(tag, log):
    txt = log.read_text(errors="ignore")
    ts = "segment" if "of their segment" in txt else "submission"
    piv = re.findall(r"present interval (\d) → (\d)", txt)
    caps = re.findall(r"frame step cap (\d+) → (\d+) fps", txt)
    ft = re.findall(r"frame time p50 ([\d.]+) / p95 ([\d.]+) / max ([\d.]+) ms", txt)
    gpu = re.findall(r"GPU p50 ([\d.]+)", txt)
    res = re.findall(r"WindowCrop \d+,\d+ (\d+x\d+)", txt)
    print(f"\n=== {tag}: timestamps {ts} ===")
    print(f"  present interval changes: {piv if piv else 'none'}")
    print(f"  frame step cap changes:   {caps if caps else 'none'}")
    print(f"  crop sizes:               {sorted(set(res))}")
    if ft:
        n = len(ft)
        print(f"  frame time p50: first {ft[0][0]} -> last {ft[-1][0]} ms")
    if gpu:
        print(f"  GPU p50: first {gpu[0]} -> last {gpu[-1]} ms")
    print(f"  RED: {txt.count('[RED]')}")


def main():
    a = run("submission", {})
    summarize("submission", a)
    b = run("segment", {"DM_NVN_GPU_TS": "segment"})
    summarize("segment", b)


main()
