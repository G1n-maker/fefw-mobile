# The host changes this project needs on day one

The Cross Rays port produced a set of host changes. Some are upstream now; the rest have to be applied
to `nxnative/` here before this title can boot past its own problems. This file is the checklist.

**Why these and not a patch file:** `nxnative/` is a shallow clone, so a `git apply` of the Cross Rays
patch fails on missing history and on the hunks upstream has since moved. Apply these by hand, one
file at a time, and delete each line from this list as it goes in. When the list is empty, generate a
patch from the tree and keep it here.

## Already upstream — nothing to do

- **`nn::fs::ReadFile`'s `ReadOption` overload without a byte count.** Merged as `6136418b`, reading in
  full via `h_fs_ReadFileExact`. Verify with
  `grep -c h_fs_ReadFileExactOpt nxnative/dm/host/hle_fs.c` → 1.

## Needed now

### 0a. Frame rate: a **Game default** choice, and it is now the default — **applied**

`fps_target 60` ran this game at **double speed**. The engine steps by `60 / target` each frame and ships
with 60 in menus and 30 in battle, so overwriting its 30 with 60 presents 60 frames a second while stepping
each as 1/60 s. A player noticed before any measurement did. Fixed by adding a `0` (leave the game's own
rate) choice to the Frame rate row in `dm/games/settings.tsv` and making it the row's default; `0` is
already a supported value (`hle_fpslock.c`: "0 = leave the game's own limit"), verified from the log —
`DM_FPS_TARGET=0` prints "target frame rate left as the game sets it".

**This is shared with the iOS launcher**, so it changes both front ends' drop-down. Detail and the
before/after table in [../docs/FINDINGS.md](../docs/FINDINGS.md) §14j1.

### 0. The launcher's own text, in Chinese — **applied**

The settings window had no localisation at all: no `.lproj`, no `.strings`, no `NSLocalizedString`, and
every label a hardcoded English literal in `dm/mac/Launcher.swift`. Setting rows were no better — their
names came from `dm/games/settings.tsv`, hardcoded English shared with the iOS front end.

Now every string goes through `L("<English>")` (`dm/ios/Sources/L10n.swift`), and
`dm/l10n/<lang>.lproj/Localizable.strings` holds the table; the English text is the key, so a missing entry
falls back to English and a new language needs no code change. `pack_app.py` gains a `localisations()` list,
copies the `.lproj` folders into `Resources/`, adds them to the build fingerprint, and writes
`CFBundleLocalizations` (the `<lang>` names, not `<lang>.lproj` — the suffixed form makes macOS fail to
match).

Simplified Chinese ships with 56 entries. Verified: with `AppleLanguages = ["zh-Hans-CN"]`,
`Bundle.preferredLocalizations` resolves `zh-Hans`, the table loads 56 keys, and `Play → 开始游戏`,
`Quit → 退出`, `Game language → 游戏语言`.

**This is upstream's code, not this title's.** It belongs in a PR of its own; it is applied here because the
window is the only way in.

### 0b. The **Game language** row needed `control.nacp` — **worked around, no code change**

The row's condition is `languages>1`, and a dump has no control data, so it never appeared. A minimal
`control.nacp` in the extraction directory, with `SupportedLanguageFlag` derived from the game's own
`romfs/Msg/` folders, makes the build report all twelve languages and show the row. Regeneration recipe in
[`../tools/README.md`](../tools/README.md).

### 1. `COMPRESSIBLE` must not exclude a texture in a pool the CPU writes — **applied; measured as no-op on the screens reached**

Two places, both in the host. This is
[PR #946](https://github.com/seedds/nxnative/pull/946), still open; until it lands, apply it here.

```c
    if (t->d.samples > 1 || ((int)mt.pixelFormat >= 250 && (int)mt.pixelFormat <= 262)) return 0;
    int no_cpu = (t->pool->flags & NVN_MEMORY_POOL_FLAGS_CPU_NO_ACCESS) != 0, uncached = (t->pool->flags & NVN_MEMORY_POOL_FLAGS_CPU_UNCACHED) != 0;
    if (no_cpu && (t->d.flags & NVN_TEXTURE_FLAGS_COMPRESSIBLE)) return 0;   // a pool the CPU cannot write
```

**`nxnative/dm/gfx/nvn/hle_nvn.c`, `ft_add`** — drop the flag from the exclusion:

```c
    if (!DM_GAME_TEX_FLUSH_UPLOAD || !t->mem || !t->pool || t->has_layout ||
        t->d.target == NVN_TEXTURE_TARGET_BUFFER || (t->pool->flags & NVN_MEMORY_POOL_FLAGS_CPU_NO_ACCESS) ||
        (t->d.flags & (NVN_TEXTURE_FLAGS_LINEAR | NVN_TEXTURE_FLAGS_LINEAR_RENDER_TARGET))) return;
```

**Why it is day one for an SDK 22 title:** the flag is a Switch memory-compression hint, not a data
format. A game that sets it on every texture draws nothing without this (`tex_init_fill`), and then
draws everything except UI panels generated after creation (`ft_add`). Both symptoms were met on Cross
Rays; a newer SDK setting it more often is the likelier case, not the rarer one.

**What it actually did here (2026-11-04):** the premise holds — this game sets the flag on **every**
texture it builds (`0x8`, or `0x9` with `IMAGE`) — but **the picture does not change**. The only
`COMPRESSIBLE` textures are full-size render targets in `CPU_NO_ACCESS` pools (3840x2160 and 2048x1152,
i.e. the swapchain and the DLSS input/output), so the old check never suppressed a texture that had
content to upload. A/B on the same screen: 660 of 2,359,296 pixels differ, all of them the save
spinner. Detail in [../docs/FINDINGS.md](../docs/FINDINGS.md) §14a.

Applied anyway: the check's order is wrong on its own terms, and it removes a trap for a later screen
that does write a `COMPRESSIBLE` texture from the CPU. Do not treat a missing layer as this bug again —
look at `tex_flush_upload` and the pool flags first.

### 2. Full screen (`present_fill`)

Four files. Only needed once the game draws; harmless before.

- `nvn_mtl.m`, `present_viewport`: return the whole canvas when `DM_PRESENT_FILL=stretch`, and scale to
  the canvas width when `crop` (`fmax` instead of `fmin`), keeping `min` otherwise.
- `dm/games/game.py`: a `present_fill` profile key (empty / `crop` / `stretch`), emitted as
  `#define DM_GAME_PRESENT_FILL "…"`.
- `dm/games/settings.tsv`: a `DM_PRESENT_FILL` row so the launcher shows it.
- `dm/ios/Sources/front_ios.m`: `game_rect()` — the full bounds when `present_fill` is set, the centred
  16:9 rectangle otherwise. Without this the letterbox comes from the view being pinned to 16:9, and
  changing only the Metal viewport does nothing.

The full versions of all four are in the Cross Rays repository,
[G1n-maker/crossrays-mobile](https://github.com/G1n-maker/crossrays-mobile) under `patches/`.

### 3. Touch shoulder keys reaching the edge

`dm/ios/Sources/DmGamepad.m`: `dropCenter` and `clickCenter` use `self.corner` (half the safe-area
inset) instead of `self.safe` (all of it), and `K_ZL_X`/`K_L_X` drop from 44 to 30. Cosmetic, but the
difference between usable and not on a phone.

## Not needed unless the port gets that far

- The Cross Rays `mem_used` value — this game's modules are much larger, so measure it rather than copy.
- `present_interval`, `fps_target` — decide from what the game itself does.

## When the list is done

```bash
cd nxnative && git diff > ../patches/fefw-host-changes.patch
```

and record in [../docs/FINDINGS.md](../docs/FINDINGS.md) what each change fixed here, with the log line
that showed it.

**State now:** items 0, 0b and 1 are applied and saved as [`fefw-host-changes.patch`](fefw-host-changes.patch)
(7 files, 160 insertions). Items 2 and 3 are untouched — item 2 (`present_fill`) only matters once the
phone's aspect ratio is in play, and item 3 is an iOS-only cosmetic change. Item 0b needed no code at all:
it is a generated `control.nacp` beside the game data.
