"""Git hooks: the split that keeps a commit's tree clean, and the refusal to touch someone's hook."""

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.errors import HookError
from pinakes.hooks import HOOKS, MARKER, HookState, hooks_dir, inspect, install, suggestion
from pinakes.init import init
from pinakes.sidecar import SIDECAR_SUFFIX

DIM = 3


class FakeBackend:
    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = [np.ones(DIM, dtype=np.float32) for _ in texts]
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", "rev1", DIM, 512)


class FakeReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [0.0] * len(passages)

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-reranker", "v1", 0, 512)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    register_embedding_backend("fake", lambda section, offline: FakeBackend())
    register_reranker("fake", lambda section, offline: FakeReranker())

    result = init(tmp_path / "kb", now="20260725 17:45")
    path = result.root / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    text = text.replace('provider = "sentence-transformers"', 'provider = "fake"')
    text = text.replace('model    = "BAAI/bge-small-en-v1.5"', 'model    = "fake-model"')
    text = text.replace("dim      = 384", f"dim      = {DIM}")
    text = text.replace('model    = "BAAI/bge-reranker-base"', 'model    = "fake-reranker"')
    path.write_text(text, encoding="utf-8")

    git(result.root, "init", "-q")
    git(result.root, "config", "user.email", "t@example.com")
    git(result.root, "config", "user.name", "Test")
    # Commit the scaffolding init produced, so a later "is the tree clean?" assertion is about the
    # hooks and not about files the fixture forgot.
    git(result.root, "add", "-A")
    git(result.root, "commit", "-q", "-m", "init")
    return result.root


def test_install_writes_all_three_hooks_executable(kb: Path) -> None:
    written, refused = install(kb)
    assert {status.name for status in written} == set(HOOKS)
    assert refused == []

    for status in written:
        assert status.path.is_file()
        assert os.access(status.path, os.X_OK)
        assert MARKER in status.path.read_text(encoding="utf-8")


def test_the_split_is_what_the_design_specifies(kb: Path) -> None:
    """pre-commit touches docs/; post-commit and post-merge touch only the index (§6.3)."""
    install(kb)
    directory = hooks_dir(kb)

    pre = (directory / "pre-commit").read_text(encoding="utf-8")
    assert "--sidecars-only" in pre and "--stage" in pre
    assert "--index-only" not in pre

    for name in ("post-commit", "post-merge"):
        body = (directory / name).read_text(encoding="utf-8")
        assert "--index-only" in body
        assert "--sidecars-only" not in body


def test_reinstalling_is_idempotent(kb: Path) -> None:
    install(kb)
    before = {s.name: s.path.read_text(encoding="utf-8") for s in inspect(kb)}
    written, refused = install(kb)
    assert refused == []
    assert {s.name: s.path.read_text(encoding="utf-8") for s in written} == before


def test_a_foreign_hook_is_never_touched(kb: Path) -> None:
    """Silently appending to someone's hook is a trust violation, not a convenience."""
    directory = hooks_dir(kb)
    directory.mkdir(parents=True, exist_ok=True)
    existing = directory / "pre-commit"
    existing.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")

    written, refused = install(kb)
    assert existing.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"
    assert [status.name for status in refused] == ["pre-commit"]
    assert {status.name for status in written} == {"post-commit", "post-merge"}
    assert "--sidecars-only" in suggestion("pre-commit")


def test_inspect_classifies_each_hook(kb: Path) -> None:
    assert {s.state for s in inspect(kb)} == {HookState.ABSENT}
    directory = hooks_dir(kb)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "post-merge").write_text("#!/bin/sh\necho theirs\n", encoding="utf-8")
    install(kb)

    states = {s.name: s.state for s in inspect(kb)}
    assert states["pre-commit"] is HookState.OURS
    assert states["post-merge"] is HookState.FOREIGN


def test_a_hook_survives_pnk_being_absent(kb: Path) -> None:
    """A hook that fails every commit teaches people to use --no-verify forever."""
    install(kb)
    result = subprocess.run(
        [str(hooks_dir(kb) / "pre-commit")],
        cwd=kb,
        capture_output=True,
        text=True,
        env={"PATH": "/nonexistent", "HOME": os.environ.get("HOME", "")},
        check=False,
    )
    assert result.returncode == 0
    assert "not on PATH" in result.stderr


def test_a_real_commit_lands_the_sidecar_in_the_same_commit(kb: Path) -> None:
    """The whole point of the pre-commit half: id and document arrive together (§6.3)."""
    install(kb)
    (kb / "docs" / "note.md").write_text("# Note\n\nSome text.\n", encoding="utf-8")
    git(kb, "add", "docs/note.md")

    environment = dict(os.environ)
    environment["PATH"] = f"{Path(os.sys.executable).parent}:{environment['PATH']}"
    subprocess.run(["git", "commit", "-q", "-m", "add a note"], cwd=kb, check=True, env=environment)

    committed = git(kb, "show", "--name-only", "--pretty=format:", "HEAD").split()
    assert "docs/note.md" in committed
    assert f"docs/note.md{SIDECAR_SUFFIX}" in committed

    # And the tree is clean afterwards. This is the failure the three-hook split exists to prevent:
    # a post-commit sync that minted sidecars would leave an untracked file after every commit.
    assert git(kb, "status", "--porcelain").strip() == ""


def test_hooks_outside_a_git_repository_explain_the_design(tmp_path: Path) -> None:
    with pytest.raises(HookError) as exc_info:
        hooks_dir(tmp_path)
    assert "git-triggered by design" in exc_info.value.remedy
