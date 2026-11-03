# FEFW Mobile

**Fire Emblem: Fortune's Weave** (Nintendo Switch 2) running natively on iPhone, iPad and Apple
silicon Macs. **Not an emulator**: the game's own arm64 code executes on the Apple chip, only the
instructions Apple's kernel cannot run are rewritten, Horizon's system services are replaced by a host
written for Apple platforms, and the NVN graphics API is rebuilt on Metal.

**Bring your own game files.** Nothing from any game is in this repository.

> **Status: bring-up, not a port yet.** This repository currently holds the survey, the plan, and the
> project scaffolding. There is no working build, and one open question — whether the game can draw a
> frame without DLSS — decides whether there will be. See [docs/PLAN.md](docs/PLAN.md) step 0 and
> [docs/FINDINGS.md](docs/FINDINGS.md) §8.

---

## What was measured before writing any code

From the game's own modules, read without guessing:

| | |
|---|---|
| SDK | **22.2.0** — the newest the host supports, and only two games exercise it |
| Graphics | **NVN** (no Vulkan, no EGL, no Unity) |
| Modules | `main`, `rtld`, `sdk`, `subsdk0` (**DLSS 22.2.0**), `subsdk1`, `subsdk2` (**movie**) |
| `main` | 26.3 MB of text, 6,886,586 instructions |
| Rewrite sites in `main` | **0 `svc`**, 0 `tpidr`, 0 exclusives, 20,609 `x18` |
| Host hook coverage | 835 of the host's 1,041 hooks resolve in this game's `sdk` (80%) |
| RomFS | 28 GB, with `Shaders/` as its own 3 MB folder |
| Links against | `dlss.nss`, `cuda.nss`, `movie.nss`, `nnSdk.nss` ← **the risk** |

Full detail, with how each was measured, in [docs/FINDINGS.md](docs/FINDINGS.md).

---

## The one question that matters first

Apple silicon has no Tensor Core and no CUDA. `main` names `dlss.nss` and `cuda.nss`, and `subsdk0` is
40 MB of DLSS — but `main` never references the NGX API directly, so DLSS may be an optional quality
setting the game can skip.

- **Optional** → ordinary bring-up work, and the plan continues.
- **On every presented frame** → the project stops, honestly and early.

[docs/PLAN.md](docs/PLAN.md) step 0 says how to settle it in about an hour, starting with the eden
emulator bundle that came with the game (it runs on a PC with no Tensor Core either, so the game must
already have a path that works without one).

---

## Layout

```
~/dev/FEFW/
├── AGENTS.md                    working notes: rules, where things are, open questions
├── docs/
│   ├── PLAN.md                  the order of work, and what would end it
│   ├── FINDINGS.md              everything measured, with its evidence
│   └── PORTING-WORKFLOW.md      how to port any Switch title (from the Cross Rays project)
├── patches/                     host fixes the previous port produced
├── FEIYALAIDE/                  the game as it arrived (git-ignored, never committed)
├── Game/                        symlinks in the layout the tools read (git-ignored)
└── work/                        extraction, builds, logs (git-ignored)
```

## The host this builds on

[nxnative](https://github.com/seedds/nxnative) — the same project used for
[Cross Rays](https://github.com/G1n-maker/crossrays-mobile), which plays on the iPhone and the Mac at
60 fps. Two host findings from that work apply here on day one and are in `patches/`:
`nn::fs::ReadFile`'s ReadOption overload without a byte count (already upstream), and `COMPRESSIBLE`
excluded from the texture fill and the CPU-write tracking
([PR #946](https://github.com/seedds/nxnative/pull/946)).

---

## License

MIT for this repository's own contents. The host keeps its license; third-party code under it keeps
its own.

Not affiliated with Nintendo or Intelligent Systems. You need game files dumped from hardware you own.
