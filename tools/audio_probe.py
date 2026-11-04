#!/usr/bin/env python3
"""Does the game actually produce sound? Objective measurement, no listening.

Runs the host with a real audio sink (DM_AUDIO=1) and DM_AUDIO_DUMP so every PCM
block the game appends goes to a file, presses A into the opening (which has BGM
and voice), then measures the dump: sample count, how much of it is non-silent,
peak and RMS per channel.

    work/audio_probe.py [--seconds 120]
"""
import os, sys, time, pathlib, subprocess, struct, wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "Game/04007EF01F8AE000_build"
CTL = ROOT / "work/ctl_audio.txt"
LOG = ROOT / "work/logs/audio.log"
DUMP = ROOT / "work/audio.pcm"


def send(line):
    with open(CTL, "a") as f:
        f.write(line + "\n")


def main():
    secs = 120.0
    a = sys.argv[1:]
    if "--seconds" in a:
        secs = float(a[a.index("--seconds") + 1])
    CTL.write_text("")
    DUMP.unlink(missing_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update({
        "DM_ROOT": str(B), "DM_ROMFS": str(B / "extract/v0/RomFS.img"),
        "DM_SAVE": str(B / "run/save"), "DM_TEMP": str(B / "run/temp"),
        "DM_MSL_DIR": str(B / "shader/cache"), "DM_FONT_DIR": str(B / "font"),
        "DM_NVN_SHMAP": str(B / "profile/04007EF01F8AE000/shader_map.tsv"),
        "DM_LANG": "zh-Hans",
        "DM_AUDIO": "1",                      # real output path, not the silent sink
        "DM_AUDIO_DUMP": str(DUMP),
        "DM_CTL": str(CTL),
    })
    log = open(LOG, "w")
    p = subprocess.Popen([str(B / "tools/dmhost"), str(B / "patched_v0")],
                         cwd=str(B / "run"), env=env, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    print(f"host {p.pid}, audio on, PCM -> {DUMP}", flush=True)
    time.sleep(50)
    t0 = time.time()
    while time.time() - t0 < secs:
        send("A")
        time.sleep(1.6)
    os.kill(p.pid, 15)
    time.sleep(3)
    report()


def report():
    txt = LOG.read_text(errors="ignore")
    print("\n--- audio log lines ---")
    for l in txt.splitlines():
        low = l.lower()
        if "audio" in low or "audren" in low or "sink" in low or "underrun" in low:
            print("  " + l[:190])
    print("\n--- RED lines ---")
    reds = [l for l in txt.splitlines() if "[RED]" in l]
    for l in reds:
        print("  " + l[:190])
    print(f"  ({len(reds)} total)")

    if not DUMP.is_file():
        print("\nno PCM dump written")
        return
    data = DUMP.read_bytes()
    print(f"\n--- PCM dump: {len(data)} bytes ---")
    # 16-bit; channel count from the OpenAudioOut line (usually 2 for this sink)
    ch = 2
    for l in txt.splitlines():
        if "OpenAudioOut" in l and "channels" in l:
            try:
                ch = int(l.split("channels")[1].split()[0])
            except Exception:
                pass
    if ch <= 0:
        ch = 2
    n = len(data) // (2 * ch)
    if not n:
        print("  dump is empty")
        return
    samples = struct.unpack_from(f"<{n * ch}h", data)
    nonquiet = 0
    peak = 0
    acc = 0
    for i in range(n):
        frame = samples[i * ch:(i + 1) * ch]
        m = max(abs(v) for v in frame)
        if m > peak:
            peak = m
        if m > 64:            # about -54 dBFS: above dither and DC
            nonquiet += 1
        acc += sum(v * v for v in frame)
    rms = (acc / (n * max(1, ch))) ** 0.5
    print(f"  channels {ch}, {n} frames ({n / 48000.0:.1f} s at 48 kHz)")
    print(f"  peak {peak} of 32767 ({20 * __import__('math').log10(peak / 32767) if peak else -999:.1f} dBFS)")
    print(f"  rms {rms:.0f} ({20 * __import__('math').log10(rms / 32767) if rms else -999:.1f} dBFS)")
    print(f"  non-quiet frames {nonquiet} of {n} ({100.0 * nonquiet / n:.1f}%)")


main()
