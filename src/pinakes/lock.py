"""`.pinakes/sync.lock` — one writer at a time, without stopping forever.

A git hook can fire while another sync is running, so `pnk sync` takes an advisory lock. The subtle
part is not taking it; it is what to do when one is already there (docs/DESIGN.md §6.5):

* **Holder alive, this host** — normal contention. Exit quietly, successfully. A hook firing during
  a manual sync is not an error.
* **Holder dead, this host** — a killed or crashed sync. Reclaim it, and say so. The alternative,
  refusing forever, means one `kill -9` silently disables hook-driven freshness: every later
  `pnk sync --quiet` exits doing nothing, with no symptom anywhere.
* **Another host** — a shared or network checkout. Liveness cannot be checked across machines, so
  refuse and name the command that clears it. Guessing here risks two concurrent writers.

The lock records pid, hostname and start time. Pid reuse can misjudge liveness; the start time
narrows the window, and the cost of a wrong guess is one skipped sync, not a corrupt index.
"""

import json
import os
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast

from pinakes.errors import LockError

LOCK_NAME = "sync.lock"


class LockOutcome(Enum):
    ACQUIRED = "acquired"
    RECLAIMED = "reclaimed"
    BUSY = "busy"


@dataclass(frozen=True, slots=True)
class LockHolder:
    pid: int
    host: str
    started: str

    def describe(self) -> str:
        return f"pid {self.pid} on {self.host}, since {self.started}"


def read_holder(path: Path) -> LockHolder | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    data = cast(dict[str, Any], raw)
    try:
        return LockHolder(
            pid=int(data["pid"]), host=str(data["host"]), started=str(data["started"])
        )
    except (KeyError, TypeError, ValueError):
        return None


def _alive(pid: int) -> bool:
    """Whether a pid runs on *this* host. `PermissionError` means it exists but is not ours."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class SyncLock:
    """Context manager around the advisory lock. `outcome` says how it was obtained."""

    def __init__(self, state_dir: Path, *, force: bool = False) -> None:
        self.path = state_dir / LOCK_NAME
        self._force = force
        self.outcome: LockOutcome = LockOutcome.BUSY
        self.previous: LockHolder | None = None
        self._held = False

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._claim():
            self.outcome = LockOutcome.ACQUIRED
            return self

        holder = read_holder(self.path)
        self.previous = holder
        host = socket.gethostname()

        if holder is None or self._force:
            # Unreadable (a truncated write) or explicitly forced: take it, and say so.
            self.path.unlink(missing_ok=True)
            if not self._claim():  # pragma: no cover — racing another reclaim
                raise LockError(
                    f"could not take {self.path}.", remedy="Retry; another sync may have started."
                )
            self.outcome = LockOutcome.RECLAIMED
            return self

        if holder.host != host:
            raise LockError(
                f"{self.path} is held by {holder.describe()}, on another machine.",
                remedy=(
                    "Liveness cannot be checked across hosts. If that sync is definitely finished, "
                    "clear it with `pnk sync --force-unlock`."
                ),
            )

        if _alive(holder.pid):
            self.outcome = LockOutcome.BUSY
            return self

        self.path.unlink(missing_ok=True)
        if not self._claim():  # pragma: no cover — racing another reclaim
            self.outcome = LockOutcome.BUSY
            return self
        self.outcome = LockOutcome.RECLAIMED
        return self

    def _claim(self) -> bool:
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "started": datetime.now(UTC).strftime("%Y%m%d %H:%M"),
                },
                handle,
            )
        self._held = True
        return True

    @property
    def acquired(self) -> bool:
        return self.outcome in (LockOutcome.ACQUIRED, LockOutcome.RECLAIMED)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False
