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

`nn::audio` at 212 is the largest single gap by import count, and is expected for a game with this much
voice work (8.5 GB of Sound). **But it is not a functional gap** — see [§14f](FINDINGS.md): the host's
`AudioRenderer` CPU path opens, starts and renders this game's mix to correct stereo PCM (30.8 MB in
160 s, −6.6 dBFS peak, 0 underruns, 0 `[RED]`), and 204 of the 212 imports need no host hook at all
because the game's own `sdk` exports them. What the count really measures is *coverage*: whether every
sound the game asks for comes out, which is unmeasured. `nn::prepo` (26) is Nintendo's own asset
pipeline and appears in games that use it.

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

### 8a. Answered: DLSS is on every drawn frame, and it is not NGX

The question above was framed wrongly. `main` never calls NGX because **NVN2 has DLSS inside it**:
a Switch 2 game builds and evaluates the network through `nvnDlss*`, not through `ngx*`. So the
`dlss.nss` / `cuda.nss` dependency and the 40 MB `subsdk0` are beside the point — and so is
"is DLSS optional?", which is answered **no**.

Measured, not inferred:

| evidence | source |
|---|---|
| the game names **58 `nvnDlss*` entry points**, including `nvnDlssNetworkBuilderSetMethod`, `…SetPreset`, `…GetStorageSize`, every `nvnDlssParametersSet{InputColor,Depth,MotionVectors,OutputColor,JitterOffset,HistoryReset,PreExposure}`, plus the evaluate call `nvnCommandBufferEvaluateDlss` | string census over `Game/base/exefs/main` |
| all of those are fetched from the device at init and called: `DeviceGetProcAddress=2205`, and the init pass counts `DlssNetworkBuilder*`, `DlssNetworkFinalize`, `DlssNetworkInitialize` | run log, `[nvn] init 0: …` |
| the game builds **two** networks before the first frame: `3840x2160, method 2` and `2048x1152, method 0` | run log, `[nvn] DLSS network …` |
| the presentation is **1024x576 → 2048x1152** through the network, every frame | `[nvn-mtl] DLSS: MetalFX temporal scaler 1024x576 → 2048x1152` |
| the call sites are real code, not a table: `main+0x1913b48` opens with `sub sp` + `stp` frame saves and `main+0xb70f00` with `d503237f` (paciasp) + frame saves | disassembled from `Game/base/exefs/main`, build `db93b012…` |

**What makes it work anyway:** the host replays `nvnDlss*` on **MetalFX's temporal scaler**
(`nvn_mtl.m: dlss_eval`), which wants the same inputs — colour, depth, motion vectors at the input
size, the jitter and a history reset. The picture is therefore *upscaled by Metal's own temporal
reconstruction*, not by NVIDIA's network. That is why a "DLSS on every frame" title holds 60 fps with
no Tensor Core: nothing NVIDIA-specific runs.

Two consequences worth keeping:

- **`subsdk0` stays out.** The game reaches DLSS through NVN, so NGX is never called; leaving the module
  unloaded costs nothing. This is measured, not an assumption: the game has now run for minutes across
  the opening cinematic, dialogue, the world map and character creation with `subsdk0` absent.
- **Image quality is MetalFX's, not DLSS's.** Fidelity against the Switch 2 original is a comparison
  nobody has made yet; the render is 1024x576 upscaled to 2048x1152, so a 2× reconstruction either way.

[PLAN.md](PLAN.md) step 0 is therefore **closed as answered — continue**, and the dead end it guarded
against does not exist for this title.

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

## 14. Played in: the opening, and what it proves about the picture (2026-11-04, 02:00–03:00)

Driven with `DM_CTL` (button presses and on-demand screenshots from a file the host polls), not with
timed `DM_KEYS`, because this game's screens are paced by loading and by how long a person reads them:

```
[dm] DM_CTL: reading key presses and screenshot requests from …/work/ctl.txt
[dm] DM_CTL: press 0x1 (hold 0.15 s)          ← "A"
[dm] DM_CTL: screenshot of the next frame → …/work/shots/x.png
```

Captures are made with `shot`, which writes the **raw swapchain texture**; the player-visible part is
the game's own crop inside it (see §14b).

### 14a. All the way through the opening with the picture intact

| screen | result |
|---|---|
| auto-save notice (「自动保存」) | renders, Chinese text crisp, waits for A |
| opening cinematics: date card 「1450/5/1」, wyvern flight, a face in purple mist, a light-figure on a tiled floor | full 3D, fog, particles, bloom, subtitles — **all present** |
| in-engine dialogue (「芙托娜」, 「苏谛斯」, portraits bottom-left, log / hide-UI / auto-play prompts) | 3D scene + 2D portrait + translucent text box, layered correctly |
| branch choice box (「询问名字」/「我不认识你」) | renders and accepts A |
| world map with routes, towns, compass rose | terrain and water textured |
| character creation (`BODY TYPE SELECT`, TYPE A / TYPE B, BODY/SKIN/HEAD/HAIR/CLOTHES/NAME/CHECK) | models and UI complete |
| tutorials, save icon, 「正在自动保存。请勿关闭电源。」 | render |

**No missing-texture artefact was found anywhere in that path.** Measured on the frames, not by eye:

- **0 magenta pixels** — the error colour a texture-less draw produces — over the character-creation
  and dialogue frames (2,359,296 pixels each).
- Pure black covers **711 of 2,359,296 pixels** (0.03%) in the character-creation frame; there is no
  large black region standing in for a missing layer.
- Colour counts in the tens to hundreds of thousands per frame (15,587–341,000 unique colours), i.e. real
  gradients and photographs, not flats.

So **the `COMPRESSIBLE` fix in [`patches/NEEDED.md`](../patches/NEEDED.md) changes nothing visible here** — and
the reason is measurable, not lucky. This game sets the flag on *every* texture it builds (`0x8`, or `0x9`
with `IMAGE`; counted at `nvnTextureBuilderSetFlags`), but the textures the exclusion was skipping are
**not content at all**:

| texture | size | flags | why the old check skipped it |
|---|---|---|---|
| ser=3, ser=1204/1205 | 3840x2160 | `0x9` | COMPRESSIBLE **and** in a `CPU_NO_ACCESS` pool |
| ser=173/174, ser=1206 | 2048x1152 | `0x8` | same |

Those are the swapchain and the DLSS input/output render targets — full screen, GPU-only, nothing for the
CPU to upload. So the old `COMPRESSIBLE` test never fired on a texture that had content waiting.

Confirmed by an A/B on the identical screen: with the fix applied the frame differs from the baseline by
**660 of 2,359,296 pixels**, and every one of them is the save spinner's ring; with the tree cleaned up
again, **521 pixels**, the same spinner. There is no hidden layer to recover on these screens.

The fix is still applied in `nxnative/` because the order of the checks is wrong on its own terms —
`COMPRESSIBLE` is a memory-compression hint, not a data format, and it should only suppress the fill when
the pool is one the CPU cannot write, which the code now tests directly. That is upstream PR #946's
change, it is harmless here, and it removes a trap for a later screen (a CPU-written texture that *does*
carry the flag would otherwise come out empty). If a missing layer ever does appear, this is no longer the
first suspect: look at `tex_flush_upload` and the pool flags instead.

### 14b. The "UI in the top-left corner" is the game's crop, not a layout bug

The screenshots look like the UI sits in the top-left quadrant of a black screen. It does not: the host
captures the whole swapchain, and the game presents a crop of it.

```
[dm] [nvn] WindowInitialize swap chain 2 textures, interval 1, first 3840x2160 format 0x3d
[dm] [nvn] WindowCrop 0,0 2048x1152
[dm] [nvn] WindowInitialize swap chain 2 textures, interval 1, first 3840x2160 format 0x38
[dm] [nvn] WindowCrop 0,0 2048x1152
```

- swapchain **3840x2160**, crop **0,0 2048x1152**.
- **100.0%** of the non-black pixels lie inside that 2048x1152 rectangle (789,774 of 789,774 in each of
  the four original captures), and the crop's own content spans x 384–1662, y 3–1151 — i.e. the picture
  is laid out inside the crop, centred within it left-to-right, not against the swapchain's corner.
- `shot` writes the raw texture, so the area outside the crop comes out black. A window or a device sees
  only the crop.

This is the same shape as Link's Awakening cropping its layer, and needs no fix. It does mean **a
screenshot is not what the player sees**: for any comparison, crop to `0,0 2048x1152` first, or capture
through the present pass with `DM_NVN_SHOT_OUT=2048x1152`.

### 14c. The title screen **is** reached — it sits inside the chapter flow

Earlier sessions reported `Layout/Title.arc` as never opened. That was a limit of the driving, not of
the game. A press plan with directions mixed in (the d-pad matters on map and menu screens; plain A
does not move a cursor) gets there:

```
layout load order: Common -> CommonMenu -> Hub -> Gmap -> Title -> UnitMake
```

`Title.arc` opens at **t=256 s / press 220**, in the middle of the chapter flow — after the world map and
before character creation. So the file is not a "boot-time title screen" that this port skips; the game
shows it at the point in the story where it belongs. Reaching it is a solved problem, and the sequence
above is the recipe.

What this makes checkable, and worth doing once with a real capture of the same moment: the title's own
layout (`blyt/Title_TopMenu.bflyt`, `Title_ModeSelect_MenuItem.bflyt`, `Title_Out.bflan` per §14c's
original note) is now on screen, so any missing layer there is observable rather than hypothetical.

**Captured, and it renders cleanly.** [`docs/images/title-difficulty.png`](../images/title-difficulty.png)
is that screen at 2048x1152 (the game's own crop, §14b): the underwater gradient behind, the
「请选择难度」 prompt, both difficulty buttons with their woven and diamond patterns intact, the gold
dagger cursor on 普通, and the two description lines.

```
title_0: nonzero   117821 colors      62      <- transition frame
title_1: nonzero   904192 colors   35988
title_2: nonzero   903531 colors   37086      <- the one kept
title_3: nonzero   905273 colors   36768
```

~900,000 non-black pixels and 35,000–37,000 colours, stable across a second of samples: real artwork with
gradients and textures, not a flat placeholder. No black region standing in for a panel, no magenta. So
the "floating layer missing its background" symptom does **not** occur on the title either — the
`COMPRESSIBLE` question is settled here too (§14a, §14h).

**`Battle.arc` is still never opened**, and the reason is now specific rather than "the prologue is
long": character creation has a final `CHECK` page that must be confirmed, and after it the game is at
its own story pace. A blind sequence reaches `UnitMake` reliably and then loops there. Getting into a
battle needs the naming screen completed (a name grid, not a plain-A prompt) and the `CHECK` page
confirmed — i.e. it needs the screen read, not more presses. That is the next concrete step.

### 14d. No save has been written yet — and that is not a host bug

Every run so far, including one with `DM_FS=1` (`fs` logs opens, misses and read totals) and one with a
scratch `DM_SAVE`:

```
commit/ : (empty)
commit.work/ : (empty)
```

The save mount is in place — `fs mount save: → …/save.work (transactional save: work directory, swapped
in atomically on Commit)` — and the game *reads* it, but no `CreateFile`, `WriteFile` or `Commit`
happens. The host side was checked rather than assumed:

- `main` imports the whole write path: `_ZN2nn2fs10CreateFileEPKcl`, `…9WriteFile…WriteOptionE`,
  `…6CommitEPKc`, `…9FlushFile`, `…11SetFileSize`, `…15CreateDirectory`. (Read from main's dynamic
  symbol table: 931 symbols, 27 of them `nn::fs`. `sdk` imports no `nn::fs` at all — its 1,478 are
  definitions.)
- each of those has a hook, including `Commit(PKc)`, `Commit(PKc, CommitOption)`, `Commit(PKPKci)` and
  the SDK 11 `CommitSaveData(PKc)`.

**The "Saving..." on the auto-save panel is part of the artwork.** Two things say so, and both are
observable rather than inferred:

- it is the only English text on a screen that is otherwise entirely Chinese — the game is running
  `DM_LANG=zh-Hans`, and a live status string would have been localised like everything around it;
- nothing was written while it span: no file in `commit/` or `commit.work/`, no `save:` open with a
  write mode, and the panel sits still for as long as you leave it (45,300 frames in §14e).

So the screen is a tutorial *explaining* auto-save, and the first real save comes later. Consistent
with §14c: `save:/000/Global` and `save:/000/Auto` are still missing, so the prologue has not been
passed. What to watch for, when a run does save: a non-empty `commit/`, and
`[dm] fs open … save:/…` with the mode's write bit set.

### 14e. Memory: flat once a scene settles, no leak over a 10-minute soak

Three measurements, each doing a different job.

**1. Still screen, long dwell.** One run sat on the auto-save notice for **45,300 frames** (about 12
minutes at 60 fps):

```
memory up to frame   300: resident 3353 MB, GPU allocated 3447 MB, residency set 3118, serial objects 3004, memory pools 333
memory up to frame  3300: resident 3364 MB, GPU allocated 3451 MB, residency set 3119, serial objects 3004, memory pools 333
memory up to frame 45300: resident 3397 MB, GPU allocated 3451 MB, residency set 3119, serial objects 3004, memory pools 333
```

+44 MB over 45,000 frames (1.3%), with residency set, serial objects and pool count not moving at all.

**2. Ten minutes while the game keeps advancing** (A every 2 s, so scenes load — the case where a leak
would show). Resident memory climbs while scenes load and then **stops dead**:

| frame | resident |
|---|---|
| 300 | 3,376 MB |
| 10,200 | 3,732 MB |
| 12,300 | 5,716 MB |
| 16,200 | 6,162 MB |
| 21,300 | 6,683 MB |
| 27,300 | **6,645 MB** |
| 30,300 | **6,645 MB** |
| 33,300 | **6,645 MB** |
| 36,300 | **6,645 MB** |

The last four samples span **9,000 frames (2.5 minutes) with an identical resident figure to the
megabyte**, and the counters behind it are frozen too — residency set 4,991, serial objects 4,324,
memory pools 561, all unchanged from frame 27,300 on. **This is not a leak**: it is the loaded set, and
it stops growing once the game stops loading new scenes.

The plateau is *high* (6.6 GB of the profile's 9 GB application pool) because the port keeps every
texture a scene touched. That is the real risk for iPhone, and it is a policy question — releasing
textures on scene change — not a leak to fix.

A note on the measuring tool: a straight-line fit over the whole run reports "GROWS, +114 MiB/min",
because it averages in the ramp while scenes load. Fit the plateau, not the ramp; the plateau is the
question.

**3. Across scenes, the footprint rises with what is loaded**, which is what the table above shows:
3,390 MiB (menus) → 4,959 MiB (after the opening cinematic) → 6,747 MiB (character creation).

### 14f. Audio works: real BGM, no underruns

The first sessions ran `DM_AUDIO=0`, which on the Mac means the **silent sink** — the game's audio was
mixed correctly but discarded, so "no sound" then said nothing about audio support. With
`DM_AUDIO=1` and `DM_AUDIO_DUMP` writing every PCM block the game appends, measured over 160 s:

```
audren: rendered 24000 frames, 13492 of them not silent
audio #0 device callbacks 32000: 240–240 frames each, 4.0 blocks queued on average at callback; in these 2000, 0 underruns, 0.0 ms zero-padded
```

| measurement | value |
|---|---|
| PCM written | 30,818,304 bytes = 7,704,576 frames = **160.5 s** stereo at 48 kHz |
| peak | 15,414 of 32,767 (**−6.6 dBFS**) |
| rms | 1,011 (**−30.2 dBFS**) |
| frames above −54 dBFS | 4,836,000 of 7,704,576 (**62.8%**) |
| longest sustained loud stretch | **43.8 s** |
| underruns | **0**, 0.0 ms zero-padded |
| `[RED]` lines | **0** |

It is music, not noise or stuck DC — the spectrum of the loudest second shows harmonics over a
~23.4 Hz fundamental (47, 70, 94…), a **spectral flatness of 0.151** (white noise is ~1.0), and DC
holding only 1.1% of the energy.

**So the 212 `nn::audio` imports are not the gap they looked like.** 204 of them have no host hook, but
they resolve inside the game's own `sdk`, which exports them — the host never has to provide them. What
the host does provide is the thing this game actually calls: the `AudioRenderer` CPU path (open, start,
update, voice/effect nodes, `DeviceSink`), and that path produces correct stereo mixdown.

What is still unknown is *coverage*, not function: whether every sound the game asks for is heard. That
needs either `DM_AUDIO_DUMP` comparisons against the Switch 2 original, or a listen along a scripted
route.

### 14g. Two `[RED]` findings, with their status

**Audio: `no DeviceSink` — reproducible, and it is a false alarm, not lost sound.** It happens on
roughly a third of runs (3 of 5 measured). The difference is in the *first* command list:

| run | first-frame commands | DeviceSink present |
|---|---|---|
| `audio.log`, `advance.log`, `fps_30.log` | **9**: `7×6 15×1 20×1 25×1` | yes |
| `finishchar.log`, and one earlier run | **8**: `7×6 15×1 25×1` | **no** |

So the game sometimes generates its first list without the sink command — a race at startup, not
anything the host does. The host scans for the sink **once** (guarded by `!hist_logged && ncmd > 4`) and
warns at that moment:

```
[dm] [RED] audren: no DeviceSink (ID 0x14) in the command list, 0 commands of 0x140 bytes: the game will have no sound
```

**But the sound works anyway**, and the log says so two lines later:

```
[dm] audren: DeviceSink inputs 6 (24 25 …) rate 48000 samples per frame 240 mix buffer 0x81…
```

The sink is matched per list by `cmd_id(c) == g_sink_id`, and `g_sink_id` stays `0x14`, so a later list
that does carry it is handled normally. Confirmed against the audio measurement: the runs that printed
this line still produced full PCM (§14f — 30.8 MB, −6.6 dBFS, 0 underruns).

**So the `[RED]` is wrong, not the audio.** It claims a consequence the host does not actually produce:
it fires on "the first list I happened to inspect has no sink", which is not the same as "no sound". The
honest fix is to defer the verdict until a list *with* the sink has been seen, or to demote the line to
`LOG`. Not done here — it is host code shared with every other title, so it belongs in a separate change
with its own test, and this title is not broken by it. **Recorded as a known false positive** so it is not
chased again; a run that prints it is still a run with sound.

**Graphics: `stage 1 cb4 has no uniform buffer bound` — reproducible in deeper scenes, and answered by
upstream as not a bug.** It appears in the runs that get past the opening (character creation and beyond)
and not in the ones that sit on a menu. It now names its shader (the message was extended to do so):

```
[dm] [nvn-mtl] [RED] stage 1 cb4 has no uniform buffer bound (shader 300c5dd0fd84cf79_b, 28 bindings)
```

That shader is a **particle effect**: `shader_map.tsv` line 7340 maps key `300c5dd0fd84cf79` to
`ps_effect.bin 2963 pixel /Effect/Particle/FieldBtl200.ptcl.zst#BNSH@0x161000#var2` — a battlefield
effect, `var2` variant. The host substitutes the all-zero bank and continues, as it does for an unbound
texture slot; no picture defect was found on the frames it appears on (no magenta, no visible artefact
in §14a's checks).

This section originally listed two candidate causes — the game relying on stale binding state, or the
host dropping a bind. **The second is ruled out by upstream**, which has the exact symptom documented in
[An unbound uniform slot reads the zero bank](https://github.com/seedds/nxnative/blob/main/docs/reference/rendering.md#an-unbound-uniform-slot-reads-the-zero-bank):
"the game draws with nothing bound there; **the host misses no bind**". The zero bank is the intended
stand-in and is present in this tree. See §14m.

**Status: not a defect.** The one thing still genuinely unknown is what the Switch reads from an
unbound slot, which upstream also records as unknown; if a particle ever looks wrong here, that is the
question to ask, not whether a bind went missing.

### 14h. `write-protection faults` is not zero, and that is correct

The check suggested for verifying the `COMPRESSIBLE` change was that write-protection faults should be
non-zero, i.e. that textures the CPU writes are being tracked and re-uploaded:

```
packaged textures: first uploads 2736, re-uploads on pool content change 0, writes beside a texture only (not re-uploaded) 54901; write-protection faults 54901, pages unprotected before host writes 0; missed 0 (cumulative)
```

**54,901 faults, 0 missed.** The path is live. (As §14a records, that is not *because* of the
COMPRESSIBLE change — the changed checks never fire on this title's textures — but the tracking the
number proves is the mechanism a missing generated-UI layer would depend on.)

### 14i. Reached `Gmap` — and the black screen before it was a transition, not a fault

Driving the opening with an adaptive press plan (A mostly, a `Down` and a `B` cycled in so a cursor that
ignores A still moves) got further than the plain A loop: the fourth layout loaded.

```
layout load order: Common -> CommonMenu -> Hub -> Gmap
```

`Gmap.arc` is the world map — new ground, and proof the engine survives the whole prologue into the
chapter flow. `Battle.arc`, `Title.arc` and `Ending.arc` were still never opened, so tactical gameplay
and the title screen remain unreached.

**The `Gmap` transition looks alarming and is not.** At the hand-off the frame is solid black except one
small circular icon in the bottom-right corner (28,782 non-black pixels, 8,371 colours) — exactly the
"全屏黑" shape worth being suspicious of. Sampled 2 s later, the same screen holds **557,800 non-black
pixels and 48,626 colours**, and the pixels *changed* (559,359 of them) between samples. The log explains
it:

```
fs open [210.06s] Contents:/Movie/Product/MV00_05.webm
fs open [210.59s] Contents:/Sound/stream/V_JP/V/JP/MV00/05/V_JP_MV00_05.opus
[movie] AV1: VideoToolbox decoding 2560x1440, profile 0 level 12
[codec] image pool 2560x1440 format 2, tiling or mode 2, 1 picture(s): the host keeps the decoded pictures
```

It is a movie hand-off: the decoder has been initialised, the first picture is in, and the frame arrives
within two seconds. **No layer is missing** — this is the game's own blue-flame interlude (§14a's frame
list has it as "a light-figure on a tiled floor"). A black frame between movies is what the game does.

**One detail worth knowing before any audio comparison:** the voice stream is the **Japanese** one —
`Sound/stream/V_JP/…V_JP_MV00_05.opus` — while the UI is the Chinese `zh-Hans` build. Both voice sets
ship (`V_JP` 3.2 GB, `V_EN` 2.8 GB) and the host does not choose: it passes `DM_LANG` through
`oe::GetDesiredLanguage` and the *game* picks the voice track. That matches the series' habit of fixed
Japanese voice with localised text, and it means a voice check must compare against the Japanese
original, not the English one.

### 14j. `fps_target`: 60 works, but the prologue's movies do not hold it

The profile raises this game's own frame rate. That is legal and deliberate — the host's own note says
`gxc` holds the target at `+0x1dc` and "at 60 the game asks for interval 1 and steps by 1.0 a frame" —
but it is worth knowing what it costs. Both runs use the same press route; only `DM_FPS_TARGET` differs.

| | `fps_target 30` (the game's own) | `fps_target 60` |
|---|---|---|
| frame time p50 | **33.31 → 33.34 ms**, flat | 16.66 ms → **21.18 ms** after frame 3300 |
| frame time p95 | 33.61 ms | 17.04 → **23.25 ms** |
| measured fps | 30.0, stable | 60.0, then frames take 21 ms |
| present interval | `1 → 2` once | `1 → 2`, `2 → 1` |
| `[RED]` | 0 | 0 |

**30 fps is rock steady through the same frames; 60 fps degrades at frame 3300 and stays degraded.**
The breakdown says it is not the renderer:

```
[longframe] frame 3300 (55.51 s) whole frame 23.2 ms, submit+present 0.3 ms, GPU 0.8 ms; new pipelines 0 …
threads up to frame 6900: top: 'main thread' 218 ms/s, 'MovieVideoHandler' 16 ms/s
```

GPU 0.8 ms and submit+present 0.3 ms out of a 23.2 ms frame: the time is the **main thread and the movie
decoder**, not Metal. `MovieVideoHandler` is active, so frame 3300 is where the opening's movies start —
at 60 fps the main thread needs 21.8% of every 16.67 ms budget for work that fit in 32% of a 33.33 ms
budget at 30 fps, and it misses.

**What this does and does not mean.** It does not say 60 fps is wrong for this game: 60 held perfectly on
every menu and dialogue screen measured (§14a), and 30 does not exercise the extra headroom at all. It
says **the prologue's video playback is not a 60 fps workload on this host**, and that a claim of "60 fps"
needs to be qualified by scene. The measured answer for gameplay — the 30 fps the game itself picks for
battles — is not in yet, because battles are not reachable (§14i).

Practical consequence for the Mac target: leave `fps_target 60` (menus and dialogue genuinely benefit,
and it is what the earlier 60 fps verification measured), and do not treat a 21 ms frame during a
cutscene as a regression. If battles turn out to be the game's own 30, the honest setting there is the
game's choice, not a forced 60.

**A correction to §14m.** The paragraph there named `nxnative-fc26-120fps` as "another SDK 22.2.0 title".
It is not: that patch builds on **EA SPORTS FC 26, SDK 19.3.3** (title `01004FF021942000`, engine
`65501fbb`). The real SDK 22.2.0 neighbours are **EA SPORTS FC 27** (`0100C49025D3E000`, "SDK 22.2.0, NVN
in the renderer NRO") and **Well Dweller** (`0100217023F6C000`, same `sdk` build hash `fed212d6…` as FC
27). Checked against ours:

| FC 27 setting | why FC 27 needs it | this title |
|---|---|---|
| `shader_key_skip 0x7d0+0x18` | its renderer keeps one control section per hash that ignores GLSLC's compile information, so later shaders' bytes name another shader | **not needed** — our `shader_map.tsv.conflicts.tsv` is empty (`# … conflict rulings: empty`), i.e. no two shaders collided on a key |
| `present_interval display` | the game asks for interval 2, which display pacing ignores | **not applied** — ours runs `game` mode and the game's own 1↔2 flips are meaningful (§14j); worth an A/B only if frame pacing is ever the complaint |
| `mem_alias 0x150000000` (5.25 GB) | Frostbite reserves 264 address regions and runs past 4.38 GB | **not applicable** — different allocator; ours reaches alias +36 GB only through StandardAllocator regions, which the host fits (§9c) |

The SDK 22 object-model question (AGENTS.md open question 3) stays open, but it is now scoped: both real
22.2.0 titles share one `sdk` hash and neither needed an object-size change beyond the node-area rule in
`dm/tools/sdk_patches.py`.

### 14k. Into the battle: the whole flow runs, at 60 fps with 1,024 draws a frame

The blocker in §14c was not the game. It was **one environment variable**: the character name is entered
through the system software keyboard, and on the Mac with no input window the host answers it as
*cancel*:

```
swkbd: title '请决定名字（无法使用的文字会于游戏内显示为■）' initial '' limit 8 min 0 → no window, treated as cancel
```

so the name could never be set and the flow could never leave NAME. The host already supports answering
it — `DM_KBD=<text>` returns that text as OK — and with it set:

```
swkbd: title '请决定名字（无法使用的文字会于游戏内显示为■）' initial '' limit 8 min 0 → OK 'Zephyr'
```

Two more things were needed to drive it, both worth recording because neither is obvious:

- **`A` alone does not advance the body-type page.** It needs a direction first (`Left` then `A` moved
  BODY → SKIN). Every later page advances on `A` alone.
- **presses sent during dialogue are consumed by the dialogue.** Arriving at `UnitMake` and immediately
  pressing 60 times leaves the screen on BODY; the same session advanced to SKIN on the *first* `A`
  once the intro dialogue had settled.

**Result: the full flow runs.** Layout order, all seven archives, ending in gameplay:

```
Common -> CommonMenu -> Hub -> Gmap -> Title -> UnitMake -> Battle
```

[`docs/images/battle-training.png`](../images/battle-training.png) is the tactical map:

- the status panel reads **`Zephyr` Lv 1, `HP 30/30`, `物攻 22`, `命中 109`, `耐物 9`, `耐魔 10`,
  武器「木制枪」** — the injected name, proving the `DM_KBD` path end to end;
- the blue movement grid and the red semi-transparent danger zone are drawn over the 3D plaza;
- the mini-map, `回避 0%`, `[ZL] 切换危险范围` and `[ZR] 环境设定` are all present;
- the world underneath is the town square with market awnings, planters, carts and soft shadows.

**And it holds 60 fps where it matters.** The battle's own numbers, at 1,024 draws a frame (vs ~50 in the
menus):

| metric | battle |
|---|---|
| frame time p50 | **16.66 → 16.68 ms** |
| frame time p95 | **16.94 ms** (0.3 ms above p50) |
| GPU p50 | 6.53 → **7.51 ms** (p95 8.50) |
| draws per frame | **1,024** |

GPU uses 7.5 ms of a 16.67 ms budget — roughly half the frame still spare — and p95 sits 0.3 ms above
p50, i.e. no stutter. **This answers §14j's open question**: the 21 ms frames there were the
*prologue's movies*, not the game. Gameplay at 60 fps is not a compromise; it is comfortable.

So the earlier "60 works on menus but not on the prologue's movies" stands as measured, and the
conclusion for the Mac target is now complete: **keep `fps_target 60`.** It is flat in menus, flat in
battle, and only the cutscene decode is short of budget — which is a decoder/thread question, not a
graphics one, and affects a scene type that is not what the port is being judged on.

**One thing this does not yet claim.** Reaching the map with a unit selected and a move grid drawn is
"the battle UI and the 3D board render correctly at 60 fps". It is not "a full turn was played": selecting
a unit, moving it, confirming an attack and watching combat resolve — and the `Effect/Particle` shaders
that fire there, including the `cb4` one from §14g — are the next thing to exercise, and the parked
session is the way to do it without re-running the 5-minute drive.

### 14l. The driving tools that made this reachable, kept in `work/`

Everything under `work/` is throwaway by design, but these were the difference between "cannot reach the
title" and "in a battle" and are worth rebuilding rather than rediscovering:

| script | what it does |
|---|---|
| `work/park.py` | starts a detached host, drives it to `UnitMake`, and **leaves it running**, so the next step costs a second instead of five minutes |
| `work/ctlp.py` | sends one `key` or one `shot` to that parked session — the `DM_CTL` "look, decide, press, look again" loop |
| `work/step1.py` | one key per screenshot, printing changed pixels and colour count per step, so "did the screen advance?" is a number |
| `work/titlecap.py` | runs to `Layout/Title.arc` and captures it |
| `work/tobattle2.py` | the full run with `DM_KBD` set, to a battle |
| `work/fps_ab.py`, `work/gputs_ab.py`, `work/audio_probe.py`, `work/mem_soak.py` | the A/B and soak measurements behind §14e, §14f, §14j |

The reusable lesson, in the spirit of `docs/PORTING-WORKFLOW.md`: **when a screen will not advance,
suspect a host-side answer to a system dialog before suspecting the game.** The `swkbd` line had been
in the log for hours, saying "treated as cancel", and the whole five-minute drive was being wasted on a
name field that could never be filled.

### 14m. What upstream and the sibling forks already know (surveyed 2026-11-04)

The `nxnative` ecosystem turned out to hold the answers to three of the open items. Read before
re-deriving anything here.

**The best reference is Donkey Kong Bananza, `040074A01BF12000`** — upstream's one shipped Switch 2
profile (`dm/games/040074A01BF12000/`), same generation as this title, built from a dump folder the same
way, SDK 20.5.19 / NVN2 / Ampere shaders. Its README is a step-by-step bring-up log and is worth reading
in full. Of the settings it needs, checked against ours:

| DKB setting | why DKB needs it | does this title need it? |
|---|---|---|
| `sys_resource 0x0` | its NPDM declares no system resource, so virtual address memory is off and the game sets a heap | **no** — our NPDM declares 64 MB and our profile already sets `0x4000000` |
| `app_pool 0x240000000` (9 GB) | Switch 2 leaves games 9 GB; with a 3.2 GB pool its `AudioSystemHeap` creation returned null | **already set** |
| `render_cond on` | agl wraps clears in `SetRenderEnableConditional`; drawn unconditionally, the composite was wiped before the upscaler read it and **every gameplay frame came out black** | **no** — this game never calls `SetRenderEnable*` at all (0 calls in every run), so the key is inert here |
| `gpu_timestamps segment` | its frame-rate controller and dynamic resolution read GPU time between timestamp reports; with one time per submission they read ~0 and it held 2304x1296 at 14 ms over budget | **measured: no effect** — see below |

**`gpu_timestamps`: tested, no difference.** This game does report 60 counters a frame
(`CommandBufferReportCounter=60`) and does flip its present interval 1 ↔ 2, which is the shape that made
`segment` necessary for DKB. An A/B on identical runs (80 s each, same presses) shows the same behaviour
either way: present interval changes `1→2` and `2→1` in both, frame time p50 16.66 → 21.19 ms
(submission) vs 16.65 → 21.89 ms (segment), crop 2048x1152 unchanged, 0 `[RED]` in both. The interval
flip here happens once near startup, not as a continuous controller, so the setting stays at the default.

**The `cb4` line is a documented non-bug.** Upstream has an entry for exactly this symptom —
[An unbound uniform slot reads the zero bank](https://github.com/seedds/nxnative/blob/main/docs/reference/rendering.md#an-unbound-uniform-slot-reads-the-zero-bank)
— and its **Cause** rules out the second candidate §14g listed:

> the argument buffer kept a null pointer for the unbound slot. **The game draws with nothing bound
> there; the host misses no bind.** What the Switch reads from an unbound slot is not known.
> **Fix:** the slot now reads the all-zero bank, as an unbound texture slot reads the zero texture.

The fix is present in this tree (`zero_bank_gpu()`, `nvn_mtl.m`). So the message is the host **reporting**
a state the game put it in, not a dropped bind. **Status changes from "two candidate causes" to
resolved-by-upstream**: keep the zero bank, and treat a picture defect near those draws as a separate
question about what the Switch really reads from an unbound slot — which upstream records as unknown.
The value of the shader name added in §14g stands: it says this is the particle effect
(`/Effect/Particle/FieldBtl200.ptcl`, variant `var2`), i.e. a title that leaves a slot unbound for
particles.

**Other forks worth knowing** (all MIT, all built on the same host):

- `robldctrl/nxnative-pokopia` — another Switch 2 title (Pokopia). Its additions are Switch 2 **KTGL**
  shader support (GLSLC v2, LINKDATA, runtime-captured shaders), Ampere translator fixes (MEMBAR,
  ERRBAR, ATOMS, BREV, `.X4` shared-memory scaling, predicated variable-latency loads, 1D fetches of 2D
  textures), and a 9 GB pool. Not applicable to this title's engine (NintendoWare, not KTGL), but the
  translator fixes are the same subsystem ours runs through.
- `ltomo2/nxnative-tv-builder` — tvOS work listing **BC texture fallback** and per-game memory adapters.
  The BC fallback matters for the iPhone target, whose GPUs need iOS 26+/A17 Pro for BC textures
  (upstream README states this); worth reading before the packaging step.
- `imnotsharingmyname/nxnative-fc26-120fps` — EA SPORTS FC 26 profile and 120 fps mode, i.e. another
  **SDK 22.2.0** title, the same SDK generation as this one. The closest neighbour for SDK 22 object
  layouts.

Upstream issue [#919 "Switch 2 Edition Support"](https://github.com/seedds/nxnative/issues/919) is open
and reports that Switch 2 *Edition* titles (a Switch 1 game plus a Switch 2 upgrade) only run their
Switch 1 version. This title is a native Switch 2 release, not an Edition, so it does not apply — noted
so nobody re-treads it.

Driving the opening with an adaptive press plan (A mostly, a `Down` and a `B` cycled in so a cursor that
ignores A still moves) got further than the plain A loop: the fourth layout loaded.

```
layout load order: Common -> CommonMenu -> Hub -> Gmap
```

`Gmap.arc` is the world map — new ground, and proof the engine survives the whole prologue into the
chapter flow. `Battle.arc`, `Title.arc` and `Ending.arc` were still never opened, so tactical gameplay
and the title screen remain unreached.

**The `Gmap` transition looks alarming and is not.** At the hand-off the frame is solid black except one
small circular icon in the bottom-right corner (28,782 non-black pixels, 8,371 colours) — exactly the
"全屏黑" shape worth being suspicious of. Sampled 2 s later, the same screen holds **557,800 non-black
pixels and 48,626 colours**, and the pixels *changed* (559,359 of them) between samples. The log explains
it:

```
fs open [210.06s] Contents:/Movie/Product/MV00_05.webm
fs open [210.59s] Contents:/Sound/stream/V_JP/V/JP/MV00/05/V_JP_MV00_05.opus
[movie] AV1: VideoToolbox decoding 2560x1440, profile 0 level 12
[codec] image pool 2560x1440 format 2, tiling or mode 2, 1 picture(s): the host keeps the decoded pictures
```

It is a movie hand-off: the decoder has been initialised, the first picture is in, and the frame arrives
within two seconds. **No layer is missing** — this is the game's own blue-flame interlude (§14a's frame
list has it as "a light-figure on a tiled floor"). A black frame between movies is what the game does.

**One detail worth knowing before any audio comparison:** the voice stream is the **Japanese** one —
`Sound/stream/V_JP/…V_JP_MV00_05.opus` — while the UI is the Chinese `zh-Hans` build. Both voice sets
ship (`V_JP` 3.2 GB, `V_EN` 2.8 GB) and the host does not choose: it passes `DM_LANG` through
`oe::GetDesiredLanguage` and the *game* picks the voice track. That matches the series' habit of fixed
Japanese voice with localised text, and it means a voice check must compare against the Japanese
original, not the English one.
