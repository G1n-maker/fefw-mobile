# AGENTS.md — working notes for this repository

Read this first. It says what this project is, where things live, and the rules that keep it
workable. The reusable procedure for porting any Switch title is
[`docs/PORTING-WORKFLOW.md`](docs/PORTING-WORKFLOW.md), carried over from the Cross Rays project.

## What this is

**Fire Emblem: Fortune's Weave** — the Switch 2 title — running natively on iPhone, iPad and Apple
silicon Macs. Not an emulator: the game's own arm64 code executes on the Apple chip, only the
instructions Apple's kernel cannot run are rewritten, Horizon's services are replaced by a host, and
NVN is rebuilt on Metal.

Everything here is bring-up work and notes. **No game files, no keys, no dumps** — see the rules below.

## Where things are

```
~/dev/FEFW/                                  the workspace (this repository)
├── FEIYALAIDE/                              the game as it arrived: a Windows emulator bundle
│   └── eglantine-*/room/                       room/exefs (modules) + room/romfs (28 GB of data)
├── Game/                                    what the tools read: symlinks in the layout they expect
│   └── base/{exefs,romfs}                     -> FEIYALAIDE/…/room/*
├── work/                                    build output, extraction, logs (never committed)
├── docs/                                    findings and the plan
└── nxnative/                                the host, a fork of seedds/nxnative, once it is cloned
```

`FEIYALAIDE/` also holds `eglantine.exe` and `eden-cli.exe`, a Windows x86_64 build of the **eden**
emulator with a Qt front end. They are a reference for how the game behaves, not part of the port:
they do not run on macOS, and nothing in this repository depends on them.

## The rules

**Never commit or attach game files, keys or anything extracted from them.** That covers `FEIYALAIDE/`,
`Game/`, `work/`, `*.nsp`, `*.xci`, `prod.keys`, `title.keys`, RomFS contents, code modules and
shaders. `.gitignore` already excludes them; do not work around it. Logs, screenshots, title IDs,
build IDs, offsets and symbol names are fine.

**Work stays in `work/`.** Extraction, patched modules, shader packages, caches and run folders all
live there, so removing `work/` resets the project without touching the game.

**Measure, then change.** Each fix starts from an observation — a crash address and its disassembly,
a log counter, a census over shaders — and the evidence goes into a comment next to the fix, the way
nxnative's own code does it.

**Find the cause; do not paper over it.** A crash, a hang or a wrong picture is finished when the
cause is found and fixed there. A stub, a skip, a clamp or a timeout that only hides the symptom is a
workaround: keep it only when the cause cannot be reached, and record it as open in
`docs/FINDINGS.md`.

**One concern per change.** A host fix, a profile key and a front-end change are separate commits, and
separate pull requests if they go upstream.

**English in code and comments.** Log lines that mark something unimplemented or wrong start with
`[RED] `.

## Read this before writing code

1. [`docs/FINDINGS.md`](docs/FINDINGS.md) — what has been measured so far, and what is still unknown.
2. [`docs/PLAN.md`](docs/PLAN.md) — the order of work, and what would make this title a dead end.
3. [`docs/PORTING-WORKFLOW.md`](docs/PORTING-WORKFLOW.md) — the procedure, with the traps that cost
   hours in the previous project.

**Before re-deriving a graphics or boot behaviour, check upstream's notes.** `nxnative/docs/reference/`
has a per-symptom entry (Symptom / Cause / Fix / Found on) for most things this title can hit, and
`docs/agents/symptoms.md` is the index to search by the log line you are looking at. The closest
neighbours to read first:

- `dm/games/040074A01BF12000/` — **Donkey Kong Bananza**, upstream's one shipped Switch 2 profile, with a
  step-by-step bring-up README. Same generation, same dump-folder packing.
- `dm/games/0100C49025D3E000/` — **EA SPORTS FC 27**, the real **SDK 22.2.0** neighbour (and
  `0100217023F6C000` Well Dweller shares its `sdk` hash). Nearest reference for SDK 22 object layouts.
  Note: `nxnative-fc26-120fps` is *not* this generation — it builds on FC 26, SDK 19.3.3.
- `robldctrl/nxnative-pokopia` — the other Switch 2 fork; its Ampere translator fixes are the subsystem
  this title's 16,888 shaders go through.
- `ltomo2/nxnative-tv-builder` — BC texture fallback and per-game memory adapters, which matter for the
  iPhone target before packaging.

[FINDINGS §14k](docs/FINDINGS.md) records which of DKB's and FC 27's settings this title does and does not
need, each with the measurement.

## Facts established before any code was written

All from the modules as they arrived, no guessing:

| | |
|---|---|
| Title ID | `04007EF01F8AE000` — Switch 2 range (`04` prefix), read from `base/exefs/main.npdm` |
| SDK | **22.2.0** (`SDK MW+Nintendo+NintendoSDK_nnSdk-22_2_0-Release` in `sdk`) |
| Graphics | **NVN** (`nvnBootstrapLoader` in `main` and `sdk`; no Vulkan, no EGL, no Unity) |
| Modules | `main`, `rtld`, `sdk`, `subsdk0` (**DLSS 22.2.0**), `subsdk1`, `subsdk2` (**movie 22.2.0**) |
| `main` | text 26.3 MB, ro 5.5 MB, data 2.2 MB, bss 1.1 MB — 6,886,586 instructions |
| `main` rewrite sites | **0 `svc`**, 0 `msr/mrs tpidr*`, 0 exclusives, 20,609 `x18` uses |
| Imports | 898, of which the host's 1,041 hooks cover **835** (80%) |
| RomFS | 28 GB: Sound 8.5, Map 6.6, Movie 6.1, Character 3.1, Effect 1.3, Layout 1.2, Animation 0.5, UI 0.15, Msg 85 MB, Font 47 MB, **Shaders 3 MB** (its own folder, not embedded) |
| `main` links against | `dlss.nss`, `cuda.nss`, `movie.nss`, `nnSdk.nss` |

Two of those decide the shape of the work: **DLSS**, and **SDK 22.2.0**. Both are now settled in the
game's favour — DLSS arrives through NVN and is served by MetalFX, and 22.2.0 has needed no object-model
change so far. The measured answers live in [FINDINGS §8a](docs/FINDINGS.md) and [§14](docs/FINDINGS.md).

## Open questions, in the order they must be answered

1. **Is DLSS on the path the game needs to draw?** — **Answered: yes, it is, and it is fine.** The game
   upscales every presented frame (1024x576 → 2048x1152) through **NVN's own `nvnDlss*`**, never through
   NGX, so `subsdk0`/`cuda.nss` are never called and the host replays the calls on MetalFX's temporal
   scaler. See [`docs/FINDINGS.md`](docs/FINDINGS.md) §8a. This was the one question that could have
   ended the project; it is closed.
2. **Does anything else need `cuda.nss`?** Still open in principle, but the game has now run through its
   opening without it — including cinematics, dialogue, the world map and character creation — so nothing
   on that path does.
3. **What does SDK 22.2.0 change** in NVN objects and service layouts, against the 22.2.0 support that
   exists (EA SPORTS FC 27, Well Dweller)?
4. **Where are the shaders**, and in what container? — **Answered**: `Shaders/*.bfsha.zst` (zstd-wrapped
   FSHA); 16,888 shaders split from 252,686 files and all compiled.
5. **Is 26 MB of `main` text a problem?** Only for reverse engineering time, not for the host.
6. **Why is the title screen never opened?** `Layout/Title.arc` is in RomFS but has never loaded; the
   prologue before it is long and not yet driven to the end. See §14c.

`docs/FINDINGS.md` keeps the running answer to each.
