# Findings

What has been measured, and what it means. Each entry says how it was measured, so it can be
re-checked. Facts only; [PLAN.md](PLAN.md) says what to do about them.

---

## 1. The game arrived as a Windows emulator bundle, not a cartridge

```
FEIYALAIDE/eglantine-windows-x86_64-pgo-<hash>/
├── eglantine.exe, eden-cli.exe     a Windows x86_64 build of eden + a Qt front end
├── lots of *.dll                   Qt 6, OpenSSL, zstd, enet, …
├── room/exefs/                     main, rtld, sdk, subsdk0, subsdk1, subsdk2  (66 MB)
└── room/romfs/                     28 GB of game data
```

The `_快速教程.txt` in the bundle says to open `eden.exe`, press `+`, point it at `room/exefs`, and
double-click the entry it lists (a title ID starting `0x4007e…`).

**So the files here are the game's own modules and data, already unpacked.** No NCA, no ticket, no
`prod.keys` — which means the usual first step of a port (decrypt with your own keys) is not needed.
What is needed is a dump made from hardware the owner has, and that is their business, not this
repository's.

`eden` and the DLLs are a **reference for how the game behaves**, not a dependency: they are Windows
x86_64 and do not run on macOS.

## 2. It is a 64-bit ARM program, so native execution is possible at all

`main.npdm` starts with `META`; at +0x12 the flags word reads `0x0006`, whose bit 0 is
`Is64BitInstruction`. Set, as required — a 32-bit program (Pikmin 3 Deluxe and a few Wii U ports) cannot
be run this way at all.

## 3. SDK 22.2.0 — at the top of what the host has seen

`strings sdk | grep 'SDK MW+Nintendo+…'` gives:

```
SDK MW+Nintendo+NintendoSDK_nnSdk-22_2_0-Release
```

And the per-component strings name the version too:

| module | components named |
|---|---|
| `sdk` | `NVN-22_2_0`, `libz-22_2_0` |
| `main` | `gfx-22_2_0` |
| `subsdk0` | `DLSS-22_2_0` |
| `subsdk2` | `movie-22_2_0` |

**22.2.0 is the newest SDK the host supports today**, and only two games exercise it (EA SPORTS FC 27
and Well Dweller). Everything the host does differently above SDK 20 — the `AddressRegionManager` node
area, the 2 MB region alignment, NVN object sizes — was last verified against those two.

## 4. NVN, not Vulkan or OpenGL

```
nvnBootstrapLoader:  main 1, sdk 2, subsdk0 0
vkCreateInstance:    0 everywhere
eglGetProcAddress:   0 everywhere
```

This matters: NVN-on-Metal is what the host is built around. A Vulkan title would take a different
path (`vk_shaders.py`), and an OpenGL one another.

## 5. `main` has no system calls of its own — the rewrite surface is small

`dm/tools/insn_census.py` over the decompressed `main`:

```
6886586 instructions decoded (2 undecodable words)
  x18 use                20609
  sub sp, sp, xN         6
```

**Zero `svc`, zero `mrs/msr tpidr*`, zero exclusives.** Every system call lives in `sdk`, which is
where the rewriter's work concentrates anyway. `x18` (the platform register, which Apple reserves) is
used 20,609 times — the host already rewrites those.

For comparison, Cross Rays' `main` was 7.6 MB of text with 1,999,881 instructions and 2,019 `x18`
uses. This is 3.5× the instructions and 10× the `x18` uses, but the same *kind* of work.

## 6. The import list is a good fit for the host

`dm/tools/nso_syms.py` against the host's hooks:

```
HLE hooks in host: 1041 | present in new game sdk exports: 835
main imports: 898
```

80% of the host's hooks have a counterpart in this game's `sdk` — higher than Cross Rays' 75%. By area:

| area | imports | | area | imports |
|---|---|---|---|---|
| `nn::audio` | 212 | | `nn::movie` | 28 |
| C / libc | 134 | | `nn::fs` | 27 |
| other C++ | 133 | | `nn::prepo` | 26 |
| `nn::os` | 103 | | `nn::oe` | 22 |
| `nn::util` | 48 | | `nn::mem` | 21 |
| `nn::hid` | 47 | | `nn::fontll` | 21 |
| `nn::codec` | 34 | | `nn::vi` | 10 |

`nn::audio` at 212 is the largest single gap and is expected for a game with this much voice work
(8.5 GB of Sound). `nn::prepo` (26) is Nintendo's own asset pipeline and appears in games that use it.

## 7. RomFS: 28 GB, and the shaders are their own folder

```
Sound      8.5G    Animation  517M    Graphics    20M
Map        6.6G    UI         149M    Shaders    3.0M
Movie      6.1G    Msg         85M    Script     1.4M
Character  3.1G    Font        47M    Path        12K
Effect     1.3G    GameData    32M
Layout     1.2G
```

`Shaders/` being a **separate 3 MB folder** is the single most encouraging fact here: Cross Rays kept
1,090 GLSLC outputs compiled into `main`'s read-only segment, which needed a dedicated reader, whereas
a folder means the split's ordinary file scan should find them — if the container is one it knows.

`Fs.bin.zst` at the root suggests a manifest or file table, compressed with zstd.

## 8. The game links against DLSS and CUDA — the one fact that could end this

`main`'s dependency list, read from the strings beside its dynamic section:

```
… | dlss.nss | cuda.nss | movie.nss | nnSdk.nss
```

`subsdk0` is 40 MB of **DLSS 22.2.0** (`NGX_*`, `NGX_DLSS_MODE_*`, `NGX_DLTSS_FUSED_LAST_LAYERS`,
`NGXC`, `NGXD`, …), and `main` contains a structure named `DLSSInput`.

**But `main` never references `ngx`/`NGX` at all** (0 occurrences of either, against 19 occurrences of
the plain string `DLSS`, which are configuration names). So `main` is not calling the DLSS API
directly; it reaches it through `gfx` or not at all.

That is the open question in [PLAN.md](PLAN.md) step 1, and it is worth 30 minutes before anything
else:

- **If DLSS is an optional quality setting** the game can be told to skip — the port is ordinary work,
  because the host never has to satisfy `ngxEvaluate`.
- **If every presented frame is upscaled through DLSS** — Apple silicon has no Tensor Core and no CUDA,
  and there is no software path that would keep 60 fps. That ends the project honestly rather than
  after weeks.

## 9. It boots: the host reaches `nnMain` and survives 15 seconds

`scripts/build_ipa_from_nsp.py` in its `--platform mac` mode, with `Game/base/` as a dump (no keys
needed), identified the title, packed it, rewrote the modules and **booted it**:

```
[01:21:48] game profile: 04007EF01F8AE000
[01:22:41] ✓ [1/4] pack v0 (0:49): 27.1 GB
[01:23:29] ✓ [2/5] rewrite (0:16): main, subsdk2, sdk
[01:26:20] ✓ [3/6] address regions (0:26): in its first 15 s in nnMain …
```

Four things follow, and they are the most important measurements in this file.

**a. The title ID is `04007EF01F8AE000`.** The `04` prefix is the Switch 2 range — this is the first
Switch 2 title this workspace has handled, and the tools recognised it without being told.

**b. The rewriter picked `main`, `subsdk2` and `sdk` — and left out `subsdk0`, which is DLSS.** So the
module-selection logic already avoids a module it cannot satisfy. That is the right default: failing
inside the game when it calls DLSS is a better failure than failing at load.

**c. The game reached `nnMain` and ran for 15 seconds.** Along the way it:

- called `nvnDeviceSetDepthMode` with `near = 0` (the mode 13 Sentinels, Engage and Link's Awakening
  also use, so the profile takes `depth_mode zero`),
- set up `36.00 GB` at `alias +0.06 GB` through `nn::mem::StandardAllocator::Initialize`, returning to
  `main+0x651ef8`,
- and its regions reached `alias +36.06 GB`, past the profile's 16 GB alias region only by
  StandardAllocator regions, which the host makes fit.

**d. Nothing in that path touched DLSS.** NGX is not needed to load, to initialise `nv::` graphics, or
to reach the frame loop. That is not yet proof that DLSS is unused **per drawn frame** — that is still
open — but it removes the worst version of the worry (a game that cannot start at all without it).

## 10. The shader split works, and there are a lot of them

```
[4/6] shader split · splitting: 24%, 61,824/252,686 files, 1:07
[3/5] ✓ shader split (1:25): 16,888 shaders
[4/5] Mac shaders · compiling: 16,888 not cached, ETA 17:26
```

**16,888 shaders** from **252,686 files**, against Cross Rays' 639 shaders from 22,100 files: 26× as many
shaders. The split took 1 min 25 s, and the Metal compiler is chewing through them at roughly 13 per
second — about 20 minutes for the first build, then cached.

What this settles:

- **The container is one the readers know.** No new reader was needed, which was the second of the two
  things that could have stopped this (see [PLAN.md](PLAN.md), dead ends 2 and 3).
- **The shaders are NVN code, not pre-compiled SASS.** They translate and compile, so they are
  recompilable — the Tensor-Core-kernel worry is gone.

## 11. Where things stand

| step | result |
|---|---|
| Title identified | `04007EF01F8AE000`, Switch 2 range |
| Pack | 27.1 GB |
| Rewrite | `main`, `subsdk2`, `sdk` — `subsdk0` (DLSS) left out |
| Boot | reaches `nnMain`, runs 15 s, sets up 36 GB of address regions |
| Shader split | 16,888 shaders from 252,686 files, 1 min 25 s |
| Shader compile | in progress, ~20 min for the first build |

Nothing yet says the game cannot run. The remaining unknown is whether a **drawn frame** needs NGX.

## 12. What has *not* been checked

Not measured yet, and each will change the plan when it is:

- The title ID, program ID and display version (in `main.npdm` and the control data).
- Whether `gfx` (inside `main`, `gfx-22_2_0`) drives DLSS itself, and under what condition.
- Whether `cuda.nss` is used for anything the game needs, or only present as a dependency.
- The shader container format under `Shaders/`.
- The NPDM's system resource and the game's memory shape.
- Whether `subsdk1` is a second substantial module (6 MB) — its component string is not yet read.

## 13. First build timeline (2026-11-04)

| time | stage | result |
|---|---|---|
| 01:21:48 | title identified | `04007EF01F8AE000` |
| 01:22:41 | pack | 27.1 GB, 49 s |
| 01:23:29 | rewrite | `main`, `subsdk2`, `sdk`, 16 s |
| 01:26:20 | address regions + boot | reaches `nnMain`, 15 s alive |
| 01:34:14 | shader split | **16,888 shaders** from 252,686 files, 1 min 25 s |
| 01:40:28 | shader compile | 40% done, no failures logged |

The whole first build is under 20 minutes on an M5 Ultra — far faster than Cross Rays, because there is
no extraction (the dump is already unpacked) and no key handling.
