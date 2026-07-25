"""The sync lock: contention is normal, a dead holder is reclaimed, another host is refused."""

import json
import os
import socket
from pathlib import Path

import pytest

from pinakes.errors import LockError
from pinakes.lock import LOCK_NAME, LockOutcome, SyncLock, read_holder


def write_lock(state: Path, *, pid: int, host: str | None = None) -> Path:
    state.mkdir(parents=True, exist_ok=True)
    path = state / LOCK_NAME
    path.write_text(
        json.dumps({"pid": pid, "host": host or socket.gethostname(), "started": "20260725 15:00"}),
        encoding="utf-8",
    )
    return path


def test_a_free_lock_is_acquired_and_released(tmp_path: Path) -> None:
    with SyncLock(tmp_path) as lock:
        assert lock.outcome is LockOutcome.ACQUIRED
        assert lock.acquired
        holder = read_holder(lock.path)
        assert holder is not None
        assert holder.pid == os.getpid()
    assert not (tmp_path / LOCK_NAME).exists()


def test_a_live_holder_means_busy_not_an_error(tmp_path: Path) -> None:
    """A hook firing during a manual sync is contention, not a failure."""
    write_lock(tmp_path, pid=os.getpid())
    with SyncLock(tmp_path) as lock:
        assert lock.outcome is LockOutcome.BUSY
        assert not lock.acquired
    assert (tmp_path / LOCK_NAME).exists()  # the real holder's lock is left alone


def test_a_dead_holder_is_reclaimed_with_a_warning(tmp_path: Path) -> None:
    """One `kill -9` must not silently disable hook-driven freshness forever."""
    dead = _dead_pid()
    write_lock(tmp_path, pid=dead)
    with SyncLock(tmp_path) as lock:
        assert lock.outcome is LockOutcome.RECLAIMED
        assert lock.previous is not None
        assert lock.previous.pid == dead
    assert not (tmp_path / LOCK_NAME).exists()


def test_a_lock_from_another_host_is_refused(tmp_path: Path) -> None:
    write_lock(tmp_path, pid=1, host="some-other-machine")
    with pytest.raises(LockError) as exc_info, SyncLock(tmp_path):
        pass
    assert "--force-unlock" in exc_info.value.remedy
    assert "another machine" in exc_info.value.message


def test_force_takes_a_foreign_lock(tmp_path: Path) -> None:
    write_lock(tmp_path, pid=1, host="some-other-machine")
    with SyncLock(tmp_path, force=True) as lock:
        assert lock.outcome is LockOutcome.RECLAIMED


def test_an_unreadable_lock_is_reclaimed(tmp_path: Path) -> None:
    """A truncated lock file is debris, not a claim."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / LOCK_NAME).write_text("{ not json", encoding="utf-8")
    with SyncLock(tmp_path) as lock:
        assert lock.outcome is LockOutcome.RECLAIMED


def test_read_holder_tolerates_rubbish(tmp_path: Path) -> None:
    path = tmp_path / LOCK_NAME
    tmp_path.mkdir(parents=True, exist_ok=True)
    assert read_holder(path) is None
    path.write_text("[]", encoding="utf-8")
    assert read_holder(path) is None
    path.write_text('{"pid": "x"}', encoding="utf-8")
    assert read_holder(path) is None


def _dead_pid() -> int:
    """A pid that is not running: fork a child, reap it, reuse its id immediately."""
    pid = os.fork()
    if pid == 0:  # pragma: no cover — child
        os._exit(0)
    os.waitpid(pid, 0)
    return pid
