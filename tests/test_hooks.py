"""Git hooks: the split that keeps a commit's tree clean, and the refusal to edit a hook."""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pytest
from conftest import pdf_extraction_runnable

from pinakes import store
from pinakes.budget.ledger import LEDGER_NAME
from pinakes.ci import WORKFLOW
from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.errors import HookError
from pinakes.extract import CLAUDE_VISION, PYPDFIUM2
from pinakes.hooks import (
    FREE_BACKEND_FLAG,
    HOOKS,
    MARKER,
    HookState,
    hooks_dir,
    inspect,
    install,
    suggestion,
)
from pinakes.init import init
from pinakes.sidecar import SIDECAR_SUFFIX

DIM = 3
CORPUS = Path(__file__).parent / "pdf-corpus"


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
    environment["PATH"] = f"{Path(sys.executable).parent}:{environment['PATH']}"
    subprocess.run(["git", "commit", "-q", "-m", "add a note"], cwd=kb, check=True, env=environment)

    committed = git(kb, "show", "--name-only", "--pretty=format:", "HEAD").split()
    assert "docs/note.md" in committed
    assert f"docs/note.md{SIDECAR_SUFFIX}" in committed

    # And the tree is clean afterwards. This is the failure the three-hook split exists to prevent:
    # a post-commit sync that minted sidecars would leave an untracked file after every commit.
    assert git(kb, "status", "--porcelain").strip() == ""


#: A real `pnk` that registers the fake *embedding* model before dispatching. The hooks run in a
#: subprocess, where an in-process `register_embedding_backend` is invisible — and downloading real
#: weights to test a git hook is not a trade worth making. Everything else is the shipped CLI: the
#: manifest, the extraction registry, the sync, the index. It also records its own argv, so "the
#: hook ran and passed this flag" is an observation rather than an inference.
PNK_SHIM = """\
#!{python}
import json, os, sys

import numpy as np

from pinakes.embed import ModelInfo, register_embedding_backend, register_reranker

DIM = {dim}


class FakeBackend:
    def embed(self, texts):
        rows = [np.ones(DIM, dtype=np.float32) for _ in texts]
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text):
        return len(text.split())

    def info(self):
        return ModelInfo("fake", "fake-model", "rev1", DIM, 512)


class FakeReranker:
    def score(self, query, passages):
        return [0.0] * len(passages)

    def info(self):
        return ModelInfo("fake", "fake-reranker", "v1", 0, 512)


register_embedding_backend("fake", lambda section, offline: FakeBackend())
register_reranker("fake", lambda section, offline: FakeReranker())

with open(os.environ["PNK_SPY"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")

from pinakes.cli import main

raise SystemExit(main(sys.argv[1:]))
"""


def shim_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Put the shim on PATH as `pnk`, and return the environment plus the spy log's path."""
    bin_dir = tmp_path / "shim-bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "pnk"
    shim.write_text(PNK_SHIM.format(python=sys.executable, dim=DIM), encoding="utf-8")
    shim.chmod(0o755)

    spy = tmp_path / "pnk-calls.jsonl"
    environment = dict(os.environ)
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["PNK_SPY"] = str(spy)
    return environment, spy


def run_git(
    root: Path, environment: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=False, env=environment, capture_output=True, text=True
    )


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_hooks_force_the_free_backend(make_fake_kb: Callable[..., Path], tmp_path: Path) -> None:
    """Execute the hooks against a KB configured for `claude-vision`, and prove three things by
    what actually happened: the hooks ran, the free backend did the extraction, and nothing was
    spent.

    Asserting that `--extract=pypdfium2` appears in the hook *text* is the string-assertion
    failure the ground rules exist to prevent — it passes on a hook that never runs, on a flag the
    CLI ignores, and on a sync that fails outright. So the assertions here are the spy log (each
    hook really invoked `pnk sync` with the flag), the index row (the document was extracted, by
    the free backend) and the absent ledger (no reservation was ever written). The control at the
    end strips the flag from the same hook and shows it failing, which is what makes the rest
    evidence rather than coincidence.
    """
    kb = make_fake_kb(extraction_backend=CLAUDE_VISION)
    _rewrite_include_for_pdfs(kb)
    environment, spy = shim_environment(tmp_path)

    run_git(kb, environment, "init", "-q")
    run_git(kb, environment, "config", "user.email", "t@example.com")
    run_git(kb, environment, "config", "user.name", "Test")
    run_git(kb, environment, "add", "-A")
    run_git(kb, environment, "commit", "-q", "-m", "init")
    install(kb)

    shutil.copyfile(CORPUS / "baseline-1p.pdf", kb / "docs" / "scan.pdf")
    run_git(kb, environment, "add", "docs/scan.pdf")
    result = run_git(kb, environment, "commit", "-q", "-m", "add a scanned page")
    assert result.returncode == 0, result.stderr

    # 1. Both hooks ran, and both passed the flag. Not "the file contains the string".
    invocations = [json.loads(line) for line in spy.read_text(encoding="utf-8").splitlines()]
    assert len(invocations) == 2, invocations
    for argv in invocations:
        assert argv[0] == "sync"
        assert FREE_BACKEND_FLAG in argv
    assert {"--sidecars-only", "--index-only"} <= {flag for argv in invocations for flag in argv}

    # 2. The sidecar landed with the document, and the free backend is what extracted it.
    assert (
        f"docs/scan.pdf{SIDECAR_SUFFIX}"
        in git(kb, "show", "--name-only", "--pretty=format:", "HEAD").split()
    )
    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        rows = connection.execute(
            "SELECT path, extraction_backend FROM documents WHERE state = 'active'"
        ).fetchall()
    finally:
        connection.close()
    assert [(str(row["path"]), str(row["extraction_backend"])) for row in rows] == [
        ("docs/scan.pdf", PYPDFIUM2)
    ]

    # 3. Spent nothing: no reservation was written, so there is no ledger at all.
    assert not (kb / ".pinakes" / LEDGER_NAME).exists()

    # The control. Same hook, same KB, flag removed — it fails, on the paid backend it then picks
    # up from the manifest. Without this, every assertion above could hold for a KB that was never
    # configured for a paid backend in the first place, and the whole test would prove nothing.
    unforced = hooks_dir(kb) / "post-commit"
    unforced.write_text(
        unforced.read_text(encoding="utf-8").replace(f" {FREE_BACKEND_FLAG}", ""), encoding="utf-8"
    )
    stripped = subprocess.run(
        [str(unforced)], cwd=kb, capture_output=True, text=True, env=environment, check=False
    )
    assert stripped.returncode != 0, stripped.stdout
    assert "a paid extraction cannot run under --index-only" in stripped.stderr


def _rewrite_include_for_pdfs(root: Path) -> None:
    path = root / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    old = 'include = ["**/*.md", "**/*.txt"]'
    assert old in text, "the template's `include` line changed shape"
    path.write_text(text.replace(old, 'include = ["**/*.pdf"]'), encoding="utf-8")


def test_every_hook_and_the_ci_workflow_carry_the_free_backend_flag(kb: Path) -> None:
    """The cheap readability half of the test above: a reader opening a hook should see, on the
    line itself, that it cannot spend. This one greps *because* the executing test exists."""
    install(kb)
    directory = hooks_dir(kb)
    for name in HOOKS:
        body = (directory / name).read_text(encoding="utf-8")
        assert FREE_BACKEND_FLAG in body
        assert "can never spend" in body
    assert FREE_BACKEND_FLAG in WORKFLOW
    assert FREE_BACKEND_FLAG in suggestion("pre-commit")


def test_install_hooks_says_out_loud_that_it_forces_the_free_backend(
    kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pinakes.cli import main

    assert main(["install-hooks", "--kb", str(kb)]) == 0
    assert FREE_BACKEND_FLAG in capsys.readouterr().out


def test_hooks_outside_a_git_repository_explain_the_design(tmp_path: Path) -> None:
    with pytest.raises(HookError) as exc_info:
        hooks_dir(tmp_path)
    assert "git-triggered by design" in exc_info.value.remedy
