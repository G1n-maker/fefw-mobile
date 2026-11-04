# Plan

The order of work, and the gate that decides whether there is work at all.

Everything here assumes the procedure in [PORTING-WORKFLOW.md](PORTING-WORKFLOW.md), which came out of
the Cross Rays port. That project took about 16 hours end to end because the title was a good fit;
this one has a single unknown that could make all of it moot, so it is answered first.

---

## Step 0 — Decide whether to continue (about 1 hour)  ← **start here**

**Question: does the game need DLSS to draw a frame?**

Facts, from [FINDINGS.md](FINDINGS.md) §8: `main` links `dlss.nss` and `cuda.nss`, carries a
`DLSSInput` structure, and never references `ngx`/`NGX` itself. `subsdk0` is 40 MB of DLSS.

How to answer it, in this order:

1. **Find who calls `ngxEvaluate` / `ngxCreate`.** `cuda.nss` and `dlss.nss` export the NGX API; the
   caller is in `main`. Look for the loader pattern (a table of function pointers filled by name) the
   way `dm/tools/nvn_slots_got.py` does for NVN, or search `main` for the strings `ngxEvaluate`,
   `NVSDK_NGX_Parameter_*` and the feature ID `NGX_DLSS_MODE_*`.
2. **Read the condition around that call.** Quality settings in this engine are usually a table of
   `DLSS / TAA / FXAA / off`; if the call sits behind a comparison against a setting value, the port
   can pin the setting to `off`.
3. **Cross-check with the emulator bundle.** `eden` runs the game on a PC with no Tensor Core, so the
   game must already have a path that works without NGX hardware — either DLSS is off by default there,
   or the emulator stubs it. `eden`'s configuration in `FEIYALAIDE/` and its logs would say which. This
   is the cheapest evidence available and should be read first.

**Gate.** If DLSS turns out to be optional (a quality setting, off by default on non-NVIDIA paths),
continue. If every presented frame is upscaled through it, stop: Apple silicon has no Tensor Core, and
a software DLSS would not hold a frame rate. Say so in the issue and close the plan.

Deliverable: a short section in [FINDINGS.md](FINDINGS.md) §8 replacing the open question with the
answer and the evidence for it.

**Answered — see [FINDINGS §8a](FINDINGS.md).** The question was framed on a false premise: this title
reaches DLSS through **NVN's own `nvnDlss*`**, not through NGX, so `subsdk0` and `cuda.nss` are never
called. Every presented frame *is* upscaled (1024x576 → 2048x1152), but by MetalFX's temporal scaler,
which the host supplies — so the gate's dead end ("Apple silicon has no Tensor Core") does not apply.
Continue.

---

## Step 1 — Get the host to build and boot it (the bulk of the work)

Once step 0 says go, this is the ordinary bring-up, and it is where the weeks go.

1. **Clone and patch the host.**
   ```bash
   git clone https://github.com/seedds/nxnative.git nxnative
   cd nxnative && git apply ../patches/*.patch   # the Cross Rays fixes, see below
   ```
   The Cross Rays work produced two host fixes that are already upstream or in review, and this title
   will want both on day one:
   - `nn::fs::ReadFile`'s `ReadOption` overload without a byte count — **merged** as `6136418b`.
   - `COMPRESSIBLE` excluded from both `tex_init_fill` and `ft_add` —
     [PR #946](https://github.com/seedds/nxnative/pull/946), still open. Without it a game that sets
     that flag on all its textures draws nothing; SDK 22 titles are the likeliest to.

2. **Make the workspace look like a dump** the tools accept:
   ```
   Game/base/exefs/   -> FEIYALAIDE/…/room/exefs
   Game/base/romfs/   -> FEIYALAIDE/…/room/romfs
   ```
   `scripts/pack_dump.py` reads that layout, and needs **no keys** — the files are already unpacked.

3. **Survey it** (`scripts/build_ipa_from_nsp.py Game --survey-only` on a dump writes the survey from
   the profile, since the survey proper reads NSPs). For a dump the first real information comes from
   the profile and the first boot, not from the survey.

4. **Write the profile** `nxnative/dm/games/<title id>/game.tsv`. Start from the Cross Rays one —
   it is the closest neighbour in SDK generation — and expect to change:
   - `modules`: `main subsdk1 subsdk2 sdk`? `subsdk0` is DLSS and must not load unless step 0 says the
     game needs it. **Loading a module the host cannot satisfy is worse than omitting it**, because a
     missing DLSS call fails inside the game rather than at the import.
   - `mem_used`: an SDK 20+ title's modules are large; measure before guessing. `main` alone is 35 MB
     of image plus 1.1 MB of bss.
   - `sys_resource`: read it from `main.npdm` (META +0x14).

5. **Boot, and work the crash list.** This is the loop in
   [PORTING-WORKFLOW.md §5](PORTING-WORKFLOW.md#5-阶段-3bring-up-循环重点), and it is the same shape
   every time: crash → disassemble the faulting instruction → resolve the GOT slot to a symbol → diff
   that against the host's `HLE_FORCE` list → fix. On the Cross Rays port that loop found three causes
   in an afternoon once the tooling existed; here it will find more, because SDK 22 has had far less
   exposure.

Expected first failures, from the SDK alone:
- an `nn::prepo` or `nn::lmem` import with no hook (26 and 5 imports respectively);
- an SDK 22 object-size difference in an `nn::os` or `nn::vi` structure;
- `nn::audio` at 212 imports, where a missing one aborts inside `nn::sm::Initialize`.

6. **Shaders.** `Shaders/` is a separate 3 MB folder. Find the container
   (`shader_split.py`'s readers cover BNSH, BAHS, GLSLC-in-`main`, Unity bundles, KTGL, PAK, PKZ, CPK,
   XNB, and more), then run the split and check the acceptance rate. Above 95% is normal; below that,
   the container is new and needs a reader.

7. **First frame, then memory, then input and audio.** Same order as the workflow document, for the
   same reasons: each later stage is unmeasurable until the one before it works.

---

## Step 2 — Make it playable

- Frame rate: the target here is whatever the game runs at on the Switch 2. Do not promise 60 fps
  before it is measured; a Switch 2 title may run at 30 with heavy upscaling.
- Touch controls: this genre wants a virtual D-pad and confirm/cancel at minimum. The Cross Rays port
  has a working layout to copy and, more usefully, a documented way to adjust it
  (`DmGamepad.m`'s `safe` vs `corner` insets).
- Screen fill: `present_fill crop` from the Cross Rays work, if the phone's ratio differs from the
  game's.
- Save data, the 28 GB RomFS pushed once, and an IPA that does not try to carry the data.

---

## Step 3 — Upstream what is general

Anything that turns out to be a host bug rather than a quirk of this title goes upstream as its own
PR, in the shape `CONTRIBUTING.md` asks for: one concern, a `docs/reference/<subsystem>.md` entry with
Symptom / Cause / Fix / Found on, and `docs_symptoms.py` run.

---

## What would make this a dead end

Stated plainly, so the project stops early instead of late:

1. **DLSS on the mandatory path** (step 0). No Tensor Core, no CUDA, no software substitute.
2. **A shader container nothing reads, holding compiled SASS rather than NVN code.** NVN shaders are
   recompilable; raw Tensor-Core kernels would not be.
3. **The game refusing to run without `cuda.nss`** for something other than DLSS — for instance a
   physics or audio path that only has a CUDA implementation on this hardware.
4. **SDK 22.2.0 differences so wide that the host's object model does not fit**, i.e. every structure
   it knows is a different size. Two games already run on 22.2.0, so this is unlikely, but it is the
   reason step 1 is described as weeks and not days.

---

## Status

| step | state |
|---|---|
| 0 — is DLSS optional? | **answered: no, and it does not matter** — DLSS is on every drawn frame, but through NVN's own `nvnDlss*`, which the host replays on MetalFX's temporal scaler. `subsdk0`/NGX is never reached. See [FINDINGS §8a](FINDINGS.md) |
| 1 — host boots the game | **done** — reaches `nnMain`, 60 fps, 0 `[RED]` on the graphics path, cinematic → dialogue → world map → character creation all render |
| 1b — progress past the prologue | **prologue passed** — layouts `Common → CommonMenu → Hub → Gmap → Title → UnitMake`; the world map, the difficulty screen and character creation all load and render. `Battle`/`Ending` still unopened. See [FINDINGS §14i](FINDINGS.md) |
| 1c — title screen | **reached and captured** — the difficulty screen (`请选择难度`) at [docs/images/title-difficulty.png](images/title-difficulty.png): ~900,000 non-black pixels, 37,086 colours, every layer present. It sits inside the chapter flow, not at boot. See [FINDINGS §14c](FINDINGS.md) |
| 1d — into a battle | **done** — the whole flow runs to the tactical map: `Common → CommonMenu → Hub → Gmap → Title → UnitMake → Battle`, at 60 fps with 1,024 draws a frame (p95 16.94 ms, GPU 7.5 ms). [docs/images/battle-training.png](images/battle-training.png). See [FINDINGS §14k](FINDINGS.md) |
| 1e — play a turn | **done** — a whole training battle was played to a **level-up** (`LEVEL UP 2`, Zephyr 卫士, 力量/速度/技巧/魔防/幸运/魅力 each +1). The combat particles loaded and drew (`Combat.ptcl`, `CombatHitDamageCMN.ptcl`, `CombatDeathVision.ptcl`), draws ranged 161→975 a frame, and frame time held at `p50 16.66 / p95 16.99`. [docs/images/battle-levelup.png](images/battle-levelup.png). See [FINDINGS §14k2](FINDINGS.md) |
| 1f — Mac hardening | **done** — a 20-minute soak inside a battle (memory flat to the megabyte), and the cutscene frame-time question settled: the overrun is the game's own per-frame code, not the decoder or the host. See [FINDINGS §14e](FINDINGS.md) and [§14j](FINDINGS.md) |
| 2 — audio | **works** — real BGM to 48 kHz stereo: −6.6 dBFS peak, 0 underruns, 0 `[RED]`, verified as music by spectrum. Coverage (is every sound heard?) is unmeasured. See [FINDINGS §14f](FINDINGS.md) |
| 2b — memory stability | **no leak; flat through gameplay** — 20 minutes inside a battle, playing, held resident at 4,641 MB with every counter frozen (29 samples, 48,000 frames, slope +0.00). The high-water mark is 6.6 GB from the prologue's cinematic set and does not come back down — that policy, not a leak, is the iPhone risk. See [FINDINGS §14e](FINDINGS.md) |
| 2c — frame rate | **60 held on menus and dialogue; not on the prologue's movies** — at frame 3300 (movies start) the main thread + `MovieVideoHandler` need 21 ms a frame, while GPU is 0.8 ms. The game's own 30 is flat all the way through. See [FINDINGS §14j](FINDINGS.md) |
| 2c — touch | not started (Mac first; iOS front end untouched) |
| 2d — saves | **work** — the game writes `run/save/000/Auto` (198 KB) + `Global` through the transactional save, and the next session reads them and skips character creation. See [FINDINGS §14d](FINDINGS.md) |
| 2e — packaging | not started — 27 GB RomFS goes over separately, never in the IPA |
| 3 — upstream | one change staged locally (`COMPRESSIBLE`, PR #946's shape), saved as `patches/fefw-host-changes.patch`; nothing sent yet |

The facts behind every statement above are in [FINDINGS.md](FINDINGS.md), each with how it was
measured.
