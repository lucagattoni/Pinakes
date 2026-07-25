"""`pnk install-hooks` — three git hooks, split by what each is allowed to touch (§6.3).

`pnk sync` writes in two places: sidecars under `docs/`, which are committed, and the index under
`.pinakes/`, which is not. Only one of those belongs after a commit:

* **`pre-commit`** mints ids for staged documents and stages the sidecars, so a document and its
  permanent id land in the *same* commit. Fast — no embedding happens here.
* **`post-commit`** and **`post-merge`** update the index only. They never write into `docs/`, so
  the tree stays clean after a commit rather than immediately dirty with an untracked sidecar.

Two refusals matter more than they look. An existing hook that is not ours is **never** modified —
it is printed, with the lines to add, because silently appending to someone's hook is a trust
violation. And a hook that cannot find `pnk` warns and exits 0 rather than failing the commit: a
hook that blocks every commit because a virtualenv was not activated teaches people to pass
`--no-verify` permanently, which disables the hooks they installed on purpose.
"""

import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pinakes.errors import HookError

MARKER = "# installed by pinakes"

HOOKS: dict[str, str] = {
    "pre-commit": "sync --sidecars-only --stage --quiet",
    "post-commit": "sync --index-only --quiet",
    "post-merge": "sync --index-only --quiet",
}

SCRIPT = """\
#!/bin/sh
{marker}
# Keeps the pinakes index and sidecars in step with your commits. Remove this file to stop.
#
# Exits 0 even when pnk is missing: a hook that fails every commit because a virtualenv was not
# activated only teaches you to use --no-verify, which disables the hooks you wanted.
if ! command -v pnk >/dev/null 2>&1; then
  echo "pinakes: pnk is not on PATH, skipping {name}" >&2
  exit 0
fi
exec pnk {command}
"""


class HookState(Enum):
    ABSENT = "absent"
    OURS = "ours"
    FOREIGN = "foreign"


@dataclass(frozen=True, slots=True)
class HookStatus:
    name: str
    state: HookState
    path: Path


def hooks_dir(root: Path) -> Path:
    git = root / ".git"
    if not git.exists():
        raise HookError(
            f"{root} is not a git repository.",
            remedy=(
                "Freshness is git-triggered by design (§6.3). Run `git init` here, or keep the KB "
                "fresh with a cron `pnk sync`."
            ),
        )
    if git.is_file():
        # A worktree or submodule: .git is a file pointing at the real directory.
        pointer = git.read_text(encoding="utf-8").strip()
        _, _, target = pointer.partition("gitdir: ")
        if not target:
            raise HookError(f"cannot read {git}.", remedy="Is this a valid git worktree?")
        git = (root / target).resolve()
    return git / "hooks"


def inspect(root: Path) -> list[HookStatus]:
    directory = hooks_dir(root)
    statuses: list[HookStatus] = []
    for name in HOOKS:
        path = directory / name
        if not path.exists():
            statuses.append(HookStatus(name, HookState.ABSENT, path))
        elif MARKER in path.read_text(encoding="utf-8", errors="replace"):
            statuses.append(HookStatus(name, HookState.OURS, path))
        else:
            statuses.append(HookStatus(name, HookState.FOREIGN, path))
    return statuses


def install(root: Path) -> tuple[list[HookStatus], list[HookStatus]]:
    """Install the three hooks. Returns (written, refused). Foreign hooks are never touched."""
    directory = hooks_dir(root)
    directory.mkdir(parents=True, exist_ok=True)

    written: list[HookStatus] = []
    refused: list[HookStatus] = []
    for status in inspect(root):
        if status.state is HookState.FOREIGN:
            refused.append(status)
            continue
        status.path.write_text(
            SCRIPT.format(marker=MARKER, name=status.name, command=HOOKS[status.name]),
            encoding="utf-8",
        )
        status.path.chmod(status.path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(HookStatus(status.name, HookState.OURS, status.path))
    return written, refused


def suggestion(name: str) -> str:
    """What to paste into an existing hook, since we will not edit it for you."""
    return f"command -v pnk >/dev/null 2>&1 && pnk {HOOKS[name]}  {MARKER}"
