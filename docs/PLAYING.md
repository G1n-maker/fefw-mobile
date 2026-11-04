# Playing it on the Mac

There are two ways to run this title, and they differ in more than convenience.

## The app (recommended): double-click, with a settings window

```
Game/Fire Emblem Fortune's Weave.app
```

Built with `./run.sh Game --platform mac-app` (about 4 minutes once the shaders are cached). Double-click
it in Finder, or:

```bash
open "/Users/g1n/dev/FEFW/Game/Fire Emblem Fortune's Weave.app"
```

**What it does differently from the development command:**

| | app | `--platform mac` |
|---|---|---|
| Audio | **real output by default** | **silent sink by default** — mixes correctly and throws the samples away |
| Settings | a macOS settings window before the game starts | environment variables by hand |
| Save | `~/Library/Application Support/nxnative/04007EF01F8AE000/` | `Game/…_build/run/save/` |
| Log | `~/Library/Logs/nxnative/04007EF01F8AE000.log` (+ `.prev.log`) | whatever you redirect it to |
| Disk | 29.1 GB (APFS clones, so almost free) | 27 GB extraction |

The silent-sink difference is the one that matters: a `--platform mac` run with no `DM_AUDIO` looks mute for
a reason that has nothing to do with audio support. The app gets this right without being told.

### The settings window

Shown at launch (turn off "Show this window at launch" to skip it; then hold Option at launch to get it
back). Written in SwiftUI and driven by the host's own `dm/games/settings.tsv`, so it only offers settings
that apply to this game.

**Basic:** Frame rate (30 / 60), Render scale, Console mode (Docked / Handheld), Game language, Display mode
(Window / Fullscreen).

**Advanced:**
- **Game** — Upscaling (Standard / MetalFX), the game's own upscaler, Dynamic resolution
- **Controls** — Game rumble, rumble strength and cutoff
- **Performance** — Frame buffering, Metal 4 pipelines, Pipeline prebuild, Encode thread, *Hold frames when
  late*, **Performance HUD**

"Reset to tested defaults" puts back the values the game was brought up with.

Two worth knowing:

- **Performance HUD** overlays live frame timing — the quickest way to see whether a scene is holding 60.
- **Hold frames when late** is what lets a frame take longer than its vsync rather than dropping it. It is on
  by default; turning it off is the honest way to see the real frame budget.

Environment variables still win over the window. To force something, put `KEY=VALUE` lines in
`~/Library/Application Support/nxnative/04007EF01F8AE000/env.txt`.

## The development command

For measuring, not for playing:

```bash
./run.sh Game --platform mac        # prints the exact command
cd Game/04007EF01F8AE000_build/run && DM_ROOT=... DM_AUDIO=1 dmhost patched_v0
```

Add `DM_AUDIO=1` unless you want silence, and `DM_KBD=<name>` if you will start a new game (without it the
character-name screen can never be completed — see `docs/FINDINGS.md` §14k).

## What to look at

The parts a screenshot cannot judge:

1. **Sound.** It is a correct 48 kHz stereo mix with 0 underruns and real harmonic structure — but whether the
   music and voice sound right, and the levels are balanced, only ears decide.
2. **Input feel.** The keyboard maps to a virtual pad; cursor speed and confirm/cancel placement are a
   preference.
3. **The picture in motion.** Every still frame checked is clean, but the render is 1024x576 upscaled to
   2048x1152 by MetalFX, and temporal reconstruction can smear in motion in a way a still cannot show. If it
   bothers you, try **Upscaling → MetalFX** in the settings window, or turn Dynamic resolution off.

## Known and not going to be fixed

- **Cutscenes run at 21 ms a frame** instead of 16.67. About 20 of those 21 ms is the game's own per-frame
  code, not the host or the video decoder — at the 30 fps the game itself asks for it fits in 33.3 ms easily.
  Menus, dialogue and combat are all flat at 60.
- **Two `[RED]` lines** are expected: `cb4 has no uniform buffer bound` (upstream: the game draws with nothing
  bound, the host substitutes the zero bank by design) and `no DeviceSink … will have no sound` (a false
  alarm — the sound works; see §14g).

## If the app will not start

The log is the first thing to read: `~/Library/Logs/nxnative/04007EF01F8AE000.log`. Two states it can be in
that look like trouble and are not:

- **The log is only two lines** (`launcher: … host …`, `launcher: 13 settings shown`) and no game appears:
  the settings window is open and waiting for **Play**. It does not steal focus, so an app launched from a
  terminal or `open -g` can sit behind other windows.
- **Nothing at all in the log**: the launcher never reached the host. Run it directly, which prints the reason:

```bash
"/Users/g1n/dev/FEFW/Game/Fire Emblem Fortune's Weave.app/Contents/MacOS/nxnative" --no-launcher
```

`--no-launcher` skips the settings window and uses the saved choices, which is also the fastest way to test
whether a launch problem is the window or the game.
