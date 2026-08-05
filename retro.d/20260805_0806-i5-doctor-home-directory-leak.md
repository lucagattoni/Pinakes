## Item 5 — doctor never prints the operator's home directory (20260805 08:06)

**LOW — two residual home-directory leaks exist, both correctly out of this increment's scope.**
An adversarial review confirmed the sweep of `src/pinakes/doctor.py` is exhaustive against every
`PinakesError` subclass doctor.py forwards, and found no defect in the fix itself (three
independent mutations — a no-op `_de_homed`, a swapped `_local` tuple order, and a reverted
`_sidecars` call site — each broke exactly the test that should catch it, and nothing else). Two
things remain that print an absolute path containing the operator's home directory, both outside
the item's stated boundary ("paths outside the KB stay as they are"):

1. `_linked_kbs`'s `except OSError as exc: absent.append(f"{linked.name} ({exc.strerror or exc})")`
   — the `or exc` fallback stringifies a bare `OSError`, whose default `__str__` includes
   `.filename` when set. The path involved is a *linked* KB's resolved location, not
   `manifest.root` — legitimately a different KB elsewhere on disk, not this one — so it falls
   outside "paths outside the KB stay as they are" by the same reasoning that already keeps
   `hf_cache_dir()` untouched. Rare: only fires when `why_not_a_kb`'s `OSError.strerror` is falsy,
   an edge case its own docstring already calls out as rare (an unreadable parent directory).

2. `budget.prices.PricesMissingError(reason=str(exc))` — ships a package-relative path
   (`prices.toml`'s location inside the installed wheel or an editable checkout), not
   `manifest.root`-derived, so `_de_homed` correctly leaves it alone. In an editable/source
   install, that path is often literally under the developer's home directory too (e.g.
   `~/Code/pinakes/src/pinakes/budget/prices.toml`) — the same *shape* of leak as `hf_cache_dir()`,
   for the same reason (a real filesystem location worth showing, not KB-derived).

**Worth keeping:** if "no home directory in `pnk doctor` output, ever" becomes the actual goal
rather than "no home directory *via the KB's own location*", both of these are where to look next
— they were not fixed here because the item's own text draws the boundary at `manifest.root`, and
extending it is a separate decision.
