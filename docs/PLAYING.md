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

## Controllers

**A Bluetooth controller needs no setup.** Pair it with macOS, launch the app, and it takes a player slot.
Xbox, PlayStation, Switch Pro and MFi pads go through Apple's `GameController` framework, which the host
reads for buttons, sticks, motion and rumble; pads that macOS does not list there — an 8BitDo in its own
mode, some third-party Bluetooth pads — are read as raw HID alongside.

Buttons are mapped **by position**: the pad's right face button is the game's A, bottom is B, top is X,
left is Y. So Xbox's A behaves as the game's A, not as its B. The host also disables the system gesture on
Home and Share so the game receives them.

Rumble is on by default; **Controls** in the settings window has Game rumble, Rumble strength, and a
**Rumble cutoff** for games whose quiet HD-rumble texture keeps the motors spinning.

Each controller becomes its own player. To make them all play player 1 instead, set `DM_PAD_MERGE=1`.

### If the buttons are in the wrong places

Only raw-HID pads on a non-8BitDo vendor can hit this, because HID has no standard button numbering and the
default map follows 8BitDo's. The log says so on connect:

```
controller 'XxxPad' (HID, 1234:5678): buttons use 8BitDo's numbering; if they are
in the wrong places, DM_HID_LOG=1 logs each button's number for a DM_HID_MAP
```

Follow that: run with `DM_HID_LOG=1`, press each button, read the usage numbers off the log, then write
`DM_HID_MAP=A=1,B=2,X=4,Y=5,…` into `~/Library/Application Support/nxnative/04007EF01F8AE000/env.txt`.
GameController pads never need this.

### Confirming a pad was seen

```bash
tail -f ~/Library/Logs/nxnative/04007EF01F8AE000.log | grep -i controller
```

A connected pad logs one line immediately:

```
controller 'Switch Pro Controller' connected: player 1 (npad 0)
controller 'DualSense' connected: player 2 (npad 1), with motion (gyro)
controller '8BitDo Pro 2' (HID) connected: player 1 (npad 0)
```

Nothing logged means the host never saw it, and no setting will help — check the pairing in System Settings
first.

**Not yet verified with a physical pad on this title.** The support described here is the host's, read from
`dm/host/front_mac.m` and `dm/host/pad_hid_mac.h`, and the app sets no controller environment variables. What
has not been done is pairing a pad and pressing its buttons in *this* game, so the button positions above are
the host's documented mapping rather than something measured here. If a button is wrong on a GameController
pad — not just a raw-HID one — that is a real finding worth recording.

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
