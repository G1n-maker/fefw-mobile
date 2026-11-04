# Driving and measuring this title

The scripts behind every number in [`docs/FINDINGS.md`](../docs/FINDINGS.md), kept here rather than in
`work/` so they survive a `rm -rf work/` and can be reused. They write their logs, screenshots and
control files into `work/`, which is git-ignored.

Everything assumes a build exists at `Game/04007EF01F8AE000_build/` (`./run.sh Game --platform mac`).

## Regenerating the app's two hand-supplied files

A dump folder carries neither of these, so they live in the **extraction** directory and are lost if
`Game/` is removed:

| file | what it is |
|---|---|
| `extract/v0/icon.jpg` | the app icon (any square image; `pack_app.py` makes the `.icns`) |
| `extract/v0/control.nacp` | a minimal control-data file, so the build knows the game's name, version and languages |

`control.nacp` needs only a title, a version and the language flag at `0x302C`. The flag is one bit per
language in `dm/tools/nacp.py`'s `LANGUAGES` order, and the languages are readable from the game itself —
`romfs/Msg/` holds one folder per language (`USen`, `EUen`, `JPja`, `EUfr`, `USfr`, `EUde`, `EUes`, `USes`,
`EUit`, `CNzh`, `TWzh`, `KRko`). Regenerate it with:

```python
import struct, pathlib, sys
sys.path.insert(0, 'nxnative/dm/tools'); import nacp
MAP = {'USen':'en-US','EUen':'en-GB','JPja':'ja','EUfr':'fr','EUde':'de','USes':'es-419',
       'EUes':'es','EUit':'it','CNzh':'zh-Hans','TWzh':'zh-Hant','KRko':'ko','USfr':'fr-CA'}
dirs = sorted(p.name for p in pathlib.Path('Game/base/romfs/Msg').iterdir() if p.is_dir())
flags = sum(1 << [c for c, _ in nacp.LANGUAGES].index(MAP[d]) for d in dirs)
b = bytearray(0x4000); n = b"Fire Emblem Fortune's Weave"; b[:len(n)] = n
struct.pack_into('<I', b, 0x302C, flags); b[0x3060:0x3065] = b"1.0.0"
pathlib.Path('Game/04007EF01F8AE000_build/extract/v0/control.nacp').write_bytes(bytes(b))
```

Without `control.nacp` the build still works; it just hides the **Game language** row and names the app
from the profile. Without `icon.jpg` the app icon is blank.

## The one thing to know first

**A screen that will not advance is usually a host answer to a system dialog, not the game.** The
character-name field is a system software keyboard; with no window the host answers it as *cancel*, and
the flow can never leave NAME. Setting `DM_KBD=<text>` fixes it. That single variable cost hours of
five-minute drives before it was spotted, and the log line saying so had been there the whole time:

```
swkbd: title '请决定名字…' initial '' limit 8 min 0 → no window, treated as cancel
```

Grep the log for `swkbd`, `treated as cancel`, `[RED]` and `not found` before assuming the game is stuck.

## Interactive driving: `park.py` + `ctlp.py`

The `DM_CTL` design is "look at a screen, decide, press, look again", so the useful pattern is to park a
session once and then send single keys.

```bash
.venv/bin/python tools/park.py            # start, drive to character creation, LEAVE RUNNING
.venv/bin/python tools/ctlp.py shot a.png # screenshot what is on screen now
.venv/bin/python tools/ctlp.py key Down   # send exactly one press
.venv/bin/python tools/park.py --status   # where is it? (layouts, frame count, RED)
```

The drive to character creation costs about five minutes; every `ctlp.py` step afterwards costs one
second. Do not restart the host to try a different key.

Two traps that make a session look stuck when it is not:

- **`A` alone does not advance the body-type page** — it needs a direction first (`Left` then `A`).
- **Presses sent while dialogue is still playing are eaten by the dialogue.** Arriving at `UnitMake` and
  mashing 60 times leaves the screen on BODY; the same session advanced on the *first* `A` once the intro
  had settled.

`tools/step1.py` is the same loop with the change measured per press (changed pixels, colour count), so
"did it advance?" is a number instead of a guess.

## Unattended runs

| script | does |
|---|---|
| `tools/smoke.py` | **the regression check**: boots, asserts 0 unexplained `[RED]`, reaches `Battle`, checks battle frame time and memory flatness, then a separate audio run. Exits non-zero on failure. `--only flow` for one section. |
| `tools/titlecap.py` | runs to `Layout/Title.arc` and captures it |
| `tools/tobattle2.py` | the full run with `DM_KBD` set, through character creation into a battle |

## Measurements

| script | measures |
|---|---|
| `tools/fps_ab.py` | `fps_target` 30 vs 60 on the same route: frame time, drops, present-interval flips |
| `tools/gputs_ab.py` | `gpu_timestamps` submission vs segment — for titles that read GPU time for dynamic resolution |
| `tools/audio_probe.py` | real audio out with `DM_AUDIO_DUMP`: PCM size, peak, RMS, non-silent share, underruns |
| `tools/mem_soak.py` | 10-minute soak through scene loads: does `footprint` / `resident` grow, and does it stop growing |
| `tools/battle_soak.py` | 20-minute soak **inside a battle** while playing: tests the case an iPhone's ceiling cares about, and separates growth from scene loading |

`tools/battle_soak.py` and `tools/mem_soak.py` take `--minutes`; both sample the host's own counters every
time it prints them (every 300 frames), so a faster sampler sees the same line twice rather than a stall.

`tools/audio_probe.py` writes `work/audio.pcm`; `work/audio_check.py` in the same folder analyses it
(harmonics vs noise vs DC) if it is still around — the spectral-flatness figure in FINDINGS §14f came
from there.

## What a "pass" means

`tools/smoke.py` asserts what must stay true, not a fixed script:

- **flow** = *reaches `Battle`*, because the layout order is one path of several. A run that went
  `Common → CommonMenu → Hub → Title → Battle` — skipping `Gmap` and `UnitMake` entirely — was still a
  good run, and a stricter assertion failed on it.
- **fps** = battle `p50` within 1 ms of 16.67 and `p95` ≤ 19.67, i.e. no stutter.
- **memory** = the last three `resident` samples within 64 MB of each other.
- **audio** = PCM written, non-trivial content, 0 underruns.
- **no unknown RED** — `cb4 has no uniform buffer bound` and `no DeviceSink` are both known and explained
  (`docs/FINDINGS.md` §14g); anything else fails.
