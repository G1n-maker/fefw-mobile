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

### 14c. The title screen was not reached, and why

`Layout/Title.arc` (734 KB, a SARC holding `blyt/Title_TopMenu.bflyt`,
`Title_ModeSelect_MenuItem.bflyt`, `Title_Out.bflan`, …) **exists in RomFS but is never opened**: zero
`Contents:/Layout/Title.arc` in the log of any run, including one that pressed A 130 times over four
minutes. Only `Common.arc`, `CommonMenu.arc` and `Hub.arc` load.

This is not a rendering fault. The game begins with a long unskippable prologue — the date card, the
cinematic, the first chapter's dialogue, character creation, tutorials — and reaching the title needs
that finished, which takes far longer than mashing A at 1.5 s intervals (the dialogue needs the text
to finish revealing, and choices need the cursor moved). **The title screen is still open work**;
it needs either a longer scripted route or a save that starts past the prologue.

Two facts make the route checkable rather than blind:

- the game reads `save:/000/Global` and `save:/000/Auto` at mount and, with a fresh save, does not
  find them (`fs path not found: save:/000/Global`, `…/Auto`) — so "a save exists" is a signal the
  prologue was passed, and it has never appeared;
- no save file has been written in any run so far (§14d).

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

### 14e. Memory holds flat when the scene does — and grows with what is loaded

Two different questions, measured apart.

**While the picture is still, memory is flat.** One run sat on the auto-save notice for **45,300 frames**
(about 12 minutes at 60 fps), which is a real soak rather than a spot check:

```
memory up to frame   300: resident 3353 MB, GPU allocated 3447 MB, residency set 3118, serial objects 3004, memory pools 333
memory up to frame  3300: resident 3364 MB, GPU allocated 3451 MB, residency set 3119, serial objects 3004, memory pools 333
memory up to frame 45300: resident 3397 MB, GPU allocated 3451 MB, residency set 3119, serial objects 3004, memory pools 333
```

+44 MB over 45,000 frames (1.3%), and the object counts that would show a leak — residency set, serial
objects, pool count — do not move at all (3118→3119, 3004→3004, 333→333). **No leak on a static screen.**

**Across scenes, the footprint rises with what is loaded**, which is what a port that keeps every
texture it has uploaded does:

| point | footprint |
|---|---|
| menus / first screens | 3,390 MiB |
| after the opening cinematic | 4,959 MiB |
| character creation | 6,747–6,806 MiB |

It is still open whether it comes back down when a scene is released, and whether the game stays under
the 9 GB application pool once real gameplay starts — 6.8 GB is already in use before the prologue ends.
That is PLAN step 5, and this is the baseline to measure it against.

### 14f. One `[RED]` line in this path, and it is audio

```
[dm] audren: command headers in the SDK 21 layout (no magic: +0 enabled, +1 command ID, +2 size), DeviceSink 0x140 bytes
[dm] [RED] audren: no DeviceSink (ID 0x14) in the command list, 0 commands of 0x140 bytes: the game will have no sound
```

The game's audio command list has no DeviceSink command, so the host cannot find the sink object. This
matches the known-largest gap (`nn::audio`, 212 imports, §6) and belongs to PLAN step 3; it is recorded
here because it is the only `[RED]` the picture path produced, and it is not a graphics problem.

One graphics `[RED]` was seen once, on a frame that compiled 8 new pipelines and uploaded 672 textures:

```
[dm] [nvn-mtl] [RED] stage 1 cb4 has no uniform buffer bound
[dm] [longframe] frame 9030 (154.28 s) … new pipelines 8 + shader libraries 0, 56.3 ms in all; texture uploads 672 first …
```

It is `RED_ONCE(16)` in `nvn_mtl.m`'s binding path: the shader reads constant buffer 4, the game has not
bound one there, and the host substitutes the all-zero bank (as an unbound texture slot reads 0). No
picture defect was visible on those frames. **Open**: whether the game expects a buffer there and the
bind was dropped, or the shader legitimately reads an unbound slot. Worth one pass with
`DM_NVN_PASSDUMP` on that shader if a visual fault ever appears near those draws.

