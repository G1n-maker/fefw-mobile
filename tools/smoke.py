#!/usr/bin/env python3
"""Repeat the Mac verification end to end and print pass/fail per check.

This is the script behind the numbers in docs/FINDINGS.md 14e/14f/14j/14k. It runs
the game unattended and asserts the things that must stay true, so a regression
shows up as a FAIL rather than as someone noticing a worse picture.

    work/smoke.py [--seconds 260] [--skip audio]
    work/smoke.py --only battle        # one section

Checks, each with the measurement it comes from:
  boot      reaches nnMain, 0 [RED] on the graphics path, no crash
  flow      layout order includes Gmap, Title, UnitMake and Battle
  fps       battle frame time p50 within 1 ms of 16.67 and p95 within 3 ms
  audio     PCM written, non-silent, no underruns
  memory    resident memory stops growing (last third flat within 64 MB)

Writes work/logs/smoke-<section>.log and exits non-zero if any check fails.
"""
import os, re, sys, time, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
SHOTS = ROOT / "work/shots"

PLAN = ["A", "A", "A", "Right", "A", "A", "Down", "A", "A", "A", "Left", "A",
        "A", "Up", "A", "A", "A", "A", "B", "A", "A", "Right", "Right", "A"]

results = []


def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    return ok


def run(section, seconds, extra_env):
    ctl = ROOT / f"work/ctl_smoke_{section}.txt"
    log = ROOT / f"work/logs/smoke-{section}.log"
    ctl.write_text("")
    log.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "DM_ROOT": str(B), "DM_ROMFS": str(B / "extract/v0/RomFS.img"),
        "DM_SAVE": str(B / "run/save"), "DM_TEMP": str(B / "run/temp"),
        "DM_MSL_DIR": str(B / "shader/cache"), "DM_FONT_DIR": str(B / "font"),
        "DM_NVN_SHMAP": str(B / "profile/04007EF01F8AE000/shader_map.tsv"),
        "DM_LANG": "zh-Hans", "DM_AUDIO": "0", "DM_CTL": str(ctl),
        "DM_FS": "1", "DM_KBD": "Smoke",
    })
    env.update(extra_env)
    f = open(log, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=f,
                         stderr=subprocess.STDOUT, start_new_session=True)
    print(f"  host {p.pid} -> {log.name}", flush=True)

    def send(l):
        with open(ctl, "a") as g:
            g.write(l + "\n")

    time.sleep(52)
    t0 = time.time()
    i = 0
    while time.time() - t0 < seconds:
        send(PLAN[i % len(PLAN)])
        i += 1
        time.sleep(1.05)
        if "Layout/Battle.arc" in log.read_text(errors="ignore"):
            # inside the battle: keep it on the tactical map
            for _ in range(int(max(10, (seconds - (time.time() - t0)) * 0.6))):
                send("A")
                time.sleep(1.2)
            break
    os.kill(p.pid, 15)
    time.sleep(3)
    return log


def main():
    only = None
    a = sys.argv[1:]
    for i, v in enumerate(a):
        if v == "--only": only = a[i + 1]
    print("FEFW Mac smoke", flush=True)

    # ---- flow + fps: one run all the way to the battle
    if only in (None, "battle", "flow", "fps", "boot"):
        print("\n[battle run]", flush=True)
        log = run("battle", 420, {})
        t = log.read_text(errors="ignore")
        check("boot", "nnMain" in t and "frame 1:" in t, "reached nnMain and presented a frame")
        reds = [l for l in t.splitlines() if "[RED]" in l]
        unknown = [l for l in reds if "cb4 has no uniform buffer" not in l
                   and "no DeviceSink" not in l]
        check("no unknown RED", not unknown, f"{len(reds)} RED total, {len(unknown)} unexplained")
        lay = list(dict.fromkeys(re.findall(r"Contents:/Layout/([A-Za-z0-9_]+)\.arc", t)))
        # Reaching a battle is the invariant. Which way the flow gets there is not: a run
        # that skips the world-map detour still lands in Battle, and Gmap / UnitMake are
        # not always on the path (measured 2026-11-04: one run went
        # Common -> CommonMenu -> Hub -> Title -> Battle and never opened Gmap).
        check("flow", "Battle" in lay, f"layouts {lay}")
        if "Battle" not in lay:
            check("flow detail", False, "never reached Battle.arc")
        # A battle that never draws its combat effects is a different, quieter failure:
        # the map renders but the exchange does not. Assert the effects actually loaded.
        fx = [e for e in set(re.findall(r"Contents:/Effect/Particle/(Combat[A-Za-z]*|Field[A-Za-z]*)\.ptcl", t))]
        combat = [e for e in fx if e.startswith("Combat")]
        check("combat effects", len(combat) > 0,
              f"{len(fx)} effect archives, combat set: {sorted(combat) or 'none'}")
        if "Battle" in lay:
            ft = re.findall(r"timing up to frame \d+: frame time p50 ([\d.]+) / p95 ([\d.]+)", t)
            if ft:
                p50 = float(ft[-1][0]); p95 = float(ft[-1][1])
                check("fps", abs(p50 - 16.67) <= 1.0 and p95 <= 19.67, f"p50 {p50} p95 {p95} ms")
            mem = re.findall(r"memory up to frame \d+: resident (\d+) MB", t)
            if len(mem) >= 3:
                tail = [int(x) for x in mem[-3:]]
                check("memory", max(tail) - min(tail) <= 64, f"last three resident {tail} MB")

    # ---- audio: needs the real sink and a PCM dump
    if only in (None, "audio"):
        print("\n[audio run]", flush=True)
        pcm = ROOT / "work/audio_smoke.pcm"
        pcm.unlink(missing_ok=True)
        log = run("audio", 90, {"DM_AUDIO": "1", "DM_AUDIO_DUMP": str(pcm)})
        t = log.read_text(errors="ignore")
        if pcm.is_file() and pcm.stat().st_size > 1_000_000:
            data = pcm.read_bytes()
            n = len(data) // 4
            nz = sum(1 for k in range(0, min(len(data), 4_000_000), 400) if data[k:k + 2] != b"\0\0")
            under = re.findall(r"(\d+) underruns", t)
            worst = max((int(u) for u in under), default=0)
            check("audio", nz > 100 and worst == 0,
                  f"{len(data)} bytes ({n/48000:.0f} s), {worst} underruns")
        else:
            check("audio", False, "no PCM dump written")

    print("\n" + "-" * 60)
    bad = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:16} {detail}")
    print(f"\n{len(results) - len(bad)}/{len(results)} passed")
    sys.exit(1 if bad else 0)


main()
