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

### 1. `COMPRESSIBLE` must not exclude a texture in a pool the CPU writes

Two places, both in the host. This is
[PR #946](https://github.com/seedds/nxnative/pull/946), still open; until it lands, apply it here.

**`nxnative/dm/gfx/nvn/nvn_mtl.m`, `tex_init_fill`** — move the check after the pool is known:

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

**Why this is day one for an SDK 22 title:** the flag is a Switch memory-compression hint, not a data
format. A game that sets it on every texture draws nothing without this (`tex_init_fill`), and then
draws everything except UI panels generated after creation (`ft_add`). Both symptoms were met on Cross
Rays; a newer SDK setting it more often is the likelier case, not the rarer one.

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
