# Cheats — the design, and what it takes to fill it in

The host already runs Atmosphère cheat files and shows them in a menu. So a cheat is **not a UI feature**:
its name, its grouping and its behaviour all come from the cheat file. This page fixes the shape of that
file for this title, so that once an address is known the work is mechanical.

Engine behaviour: [`nxnative/docs/reference/cheats.md`](../nxnative/docs/reference/cheats.md). Switches and
the panel: `nxnative/docs/development.md`, section *Cheats*.

## Where it appears

Two entry points, both already implemented upstream:

| | |
|---|---|
| **menu bar → Cheats** | the game's own menu; no overlay on the picture |
| **⌘⇧C** | a floating panel, which also works when the window is fullscreen |

The menu is rebuilt from the cheat file every time it opens, so **adding a cheat means editing the file,
not the code**.

## The three kinds this title needs

Chosen by how the game is played, not by what the engine can do:

| kind | what the player sees | `action` | `value` |
|---|---|---|---|
| **one-shot add** | 金币 +500, 素材 +100 | `set` | a fixed number |
| **set to** | 金币设为…, with a field to type into | `set` | `"ask"` |
| **lock** | 金币锁定…, held every frame | `freeze` | fixed, or `"ask"` |

`set` runs **one pass and turns itself off** — that is what makes "+500" a button rather than a toggle.
`freeze` holds the value every frame.

Engine actions deliberately **not** used, and why:

- `min` / `max` — "never below / never above". A lock covers what this title needs and is simpler to reason
  about. Worth revisiting for a counter that must not run out without being pinned to a number.
- `never-decrease` — a high-water mark, i.e. a statistic. Nothing here needs one, and other engines do not
  support it.

## The file

A TOML source compiled to Atmosphère `.txt` by `nxnative/scripts/cheat_anchor.py`, so no byte arithmetic by
hand:

```toml
[[cheat]]
name    = "金币 +500"
section = "资源"
action  = "set"
target  = "main+0x??????"   # the address, once known
type    = "u32"             # confirm the width with a peek before trusting this
value   = 500

[[cheat]]
name    = "金币设为…"
section = "资源"
action  = "set"
target  = "main+0x??????"
type    = "u32"
value   = "ask"
min     = 0
max     = 9999999

[[cheat]]
name    = "金币锁定…"
section = "锁定"
action  = "freeze"
target  = "main+0x??????"
type    = "u32"
value   = "ask"
min     = 0
max     = 9999999
```

`min` / `max` are the range the field's input box accepts; the panel refuses a value outside it rather than
writing something the game cannot hold. The last accepted value is kept in `<build ID>.values` beside the
file, so a repeated "set to" does not need retyping.

**`type` matters more than it looks.** A `u16` written as `u32` corrupts the neighbouring field. Peek the
bytes at the address first and confirm the width and range agree with what the game displays.

## What is missing: the addresses

Everything above is ready; `main+0x??????` is not. Nothing in this repository knows where gold, materials or
experience live, and the two ways to find out are different jobs:

| how | what it needs |
|---|---|
| **memory search** | the value observed twice: read it, change it in game, read again — the address is the one whose contents moved. This is the Cheat Engine loop, and it works because **in memory** these are aligned integers |
| **save diff** | two saves differing in one value ([FINDINGS §14o](FINDINGS.md)) — slower, and locates the field in the *save*, not in memory |

Memory search is the direct route and needs a running game; the save diff needs two save states. Both need
the player, which is why this page stops at the shape.

## The list to fill in

Written out so that finding addresses is the only remaining task:

```
资源
  金币 +500          set,    u32
  金币 +5000        set,    u32
  金币设为…          set,    ask 0..9999999
  素材 +100          set,    u16?
  素材设为…          set,    ask

成长
  经验 +1000        set,    u32
  经验设为…          set,    ask
  等级 +1            set,    u8?

锁定
  金币锁定…          freeze, ask 0..9999999
  无限生命           freeze, u32
  时间不减           depends on how the counter is stored
```

The `?` marks a type to confirm rather than assume.

## Order of work

1. **One address.** Find gold, confirm the width with a peek, write a single `set` cheat.
2. **Prove the loop.** Load it, click it, watch gold move in the game *and* survive a save and reload.
3. **Then the rest.** Each further cheat is that block with a new `name`, `target` and `value`.
4. **Then the `ask` variants**, which need the same address plus bounds.

Nothing in the menu, the panel or the packaging changes along the way, which is the point of doing it this
way.

## Not the same thing as the save editor

A cheat changes **memory at run time** and never touches the save; a save editor changes the file and
persists. See the save-editor issue for that side. For "more gold right now", a cheat is lower risk; for
"this save is already in a bad state", only the editor helps.
