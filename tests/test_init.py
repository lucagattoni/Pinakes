"""`pnk init`: a directory that is already correct, and an id that is never minted twice."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pinakes import template
from pinakes.ci import WORKFLOW_PATH
from pinakes.errors import InitError, TemplateError
from pinakes.ids import parse_kb_id
from pinakes.init import init
from pinakes.manifest import load


def test_init_produces_a_kb_that_parses(tmp_path: Path) -> None:
    result = init(tmp_path / "research", now="20260725 17:30")
    manifest = load(result.root)

    assert manifest.kb.name == "research"
    assert manifest.kb.id == result.kb_id
    assert manifest.kb.template == "notes@1.1"
    assert manifest.kb.created == "20260725 17:30"
    assert manifest.embedding.model == "BAAI/bge-small-en-v1.5"
    assert manifest.rerank.model == "BAAI/bge-reranker-base"
    assert parse_kb_id(manifest.kb.id) == manifest.kb.id


def test_init_creates_docs_and_ignores_generated_state(tmp_path: Path) -> None:
    """Publishing a KB must never publish its index or its ledger (§4.7)."""
    result = init(tmp_path / "kb")
    assert (result.root / "docs").is_dir()
    assert ".pinakes/" in (result.root / ".gitignore").read_text(encoding="utf-8")


def test_the_template_ships_its_readme_and_a_golden_set_stub(tmp_path: Path) -> None:
    result = init(tmp_path / "kb")
    assert (result.root / "README.md").is_file()
    assert (result.root / "eval" / "questions.yaml").is_file()


def test_confidence_thresholds_are_commented_out(tmp_path: Path) -> None:
    """Thresholds fitted on someone else's corpus are not a calibration (§4.2)."""
    result = init(tmp_path / "kb")
    manifest_text = (result.root / "pinakes.toml").read_text(encoding="utf-8")
    assert "# [retrieval.confidence]" in manifest_text
    assert load(result.root).retrieval.confidence is None


def test_pdfs_are_off_by_default_but_the_manifest_says_how_to_turn_them_on(tmp_path: Path) -> None:
    """`init` cannot see whether `pinakes[pdf]` is installed, so stamping a `**/*.pdf` glob would
    turn every PDF into a failed document on a core-only install (plan decision 6). Off, then —
    but *discoverably* off: 0.2.0 shipped PDF ingest as its headline feature with no glob and no
    mention of one anywhere the user would look, so a PDF dropped into a fresh KB was skipped in
    silence. `pnk sync` names it now too (`test_sync.py`)."""
    result = init(tmp_path / "kb")
    manifest_text = (result.root / "pinakes.toml").read_text(encoding="utf-8")

    assert "**/*.pdf" in manifest_text  # the exact glob, spelled out to copy
    assert "pinakes[pdf]" in manifest_text  # and the extra it needs
    assert "**/*.pdf" not in load(result.root).sources.include  # but not actually enabled


def test_two_kbs_never_share_an_id(tmp_path: Path) -> None:
    first = init(tmp_path / "a")
    second = init(tmp_path / "b")
    assert first.kb_id != second.kb_id


def test_a_custom_name_is_kept(tmp_path: Path) -> None:
    result = init(tmp_path / "kb-directory", name="My Research")
    assert load(result.root).kb.name == "My Research"


def test_refusing_to_re_initialise_explains_why(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    init(root)
    with pytest.raises(InitError) as exc_info:
        init(root)
    assert "orphan every inbound link" in exc_info.value.remedy


def test_a_directory_that_already_has_content_is_adopted(tmp_path: Path) -> None:
    """**Re-decided 20260805**, after the blanket emptiness refusal was hit three times
    independently. Creating the repo, cloning it, then running `pnk init` inside it is what the
    corpus plan prescribes and what everyone does — and a `.git`, a `README.md` and a
    `pyproject.toml` are already "not empty". *"Clear this one first"* is an alarming thing to read
    about a directory holding the documents you meant to index.

    The emptiness test is gone because what replaced it is narrower and stronger: `init` never
    overwrites a file that is already there, so there is nothing left for it to protect."""
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "something.txt").write_text("hello", encoding="utf-8")

    result = init(root)
    assert (root / "pinakes.toml").exists()
    assert (root / "something.txt").read_text(encoding="utf-8") == "hello"
    assert result.adopted == []


def test_init_never_overwrites_the_files_a_real_repository_already_has(tmp_path: Path) -> None:
    """The adoption case in full: a repo has a README and a .gitignore before it is ever a KB, and
    both are files `init` would otherwise write. Replacing them would be destroying the user's work
    to make room for a template's — so they are left **byte-identical** and reported."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (root / "README.md").write_text("# My Project\n\nReal content.\n", encoding="utf-8")

    result = init(root)

    assert (root / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"
    assert (root / "README.md").read_text(encoding="utf-8") == "# My Project\n\nReal content.\n"
    assert {path.name for path in result.adopted} == {".gitignore", "README.md"}
    assert all(path not in result.created for path in result.adopted), (
        "a file that was left alone must never be reported as created"
    )


def test_an_adopted_gitignore_that_misses_pinakes_is_flagged(tmp_path: Path) -> None:
    """`.gitignore` is the one skipped file whose *absence of content* has a consequence: an index
    and a spend ledger that can leave the machine. It is reported rather than appended to, because
    appending would be editing a file this tool does not own."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    assert init(root).gitignore_unprotected is True

    other = tmp_path / "already-safe"
    other.mkdir()
    (other / ".gitignore").write_text("build/\n.pinakes/\n", encoding="utf-8")
    assert init(other).gitignore_unprotected is False, (
        "a .gitignore that already covers .pinakes/ must not be flagged"
    )


def test_ci_refuses_an_existing_workflow_before_creating_anything(tmp_path: Path) -> None:
    """`write_workflow` already refused to overwrite, but it ran *after* `pinakes.toml` was
    written — so the refusal left a half-made KB that the next `pnk init` rejects as "already a
    KB". The old emptiness check was incidentally preventing that; removing it exposed the gap.

    `--ci` is refused rather than adopted because it is an explicit request: honouring it by
    silently doing nothing is worse than refusing."""
    root = tmp_path / "kb"
    (root / WORKFLOW_PATH).parent.mkdir(parents=True)
    (root / WORKFLOW_PATH).write_text("# mine\n", encoding="utf-8")

    with pytest.raises(InitError) as exc_info:
        init(root, ci=True)
    assert "already exists" in exc_info.value.message
    assert not (root / "pinakes.toml").exists(), "nothing may be created before the refusal"
    assert (root / WORKFLOW_PATH).read_text(encoding="utf-8") == "# mine\n"


def test_an_unknown_template_lists_the_known_ones(tmp_path: Path) -> None:
    with pytest.raises(TemplateError) as exc_info:
        init(tmp_path / "kb", template_name="nonexistent")
    assert "notes" in exc_info.value.remedy


def test_templates_are_readable_from_the_installed_package() -> None:
    assert "notes" in template.available()
    info = template.describe("notes")
    assert info.reference == "notes@1.1"


def test_a_template_variable_that_is_never_supplied_fails_loudly() -> None:
    """StrictUndefined: a typo in a template must not render as an empty manifest key.

    It fails as a `TemplateError` rather than a raw `jinja2.UndefinedError`, which is not a
    `PinakesError` and would reach the user as a traceback. The message names the reference and the
    variable, because "something is undefined somewhere" is not a thing anyone can act on.
    """
    from pinakes.errors import TemplateError

    with pytest.raises(TemplateError) as caught:
        template.render_manifest("notes", {"name": "x"})
    assert "notes@1.1" in str(caught.value)
    assert "kb_id" in str(caught.value)


def test_created_is_utc_even_where_the_machine_clock_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`created` is the UTC instant, never the machine's wall clock.

    Run under `TZ=Pacific/Kiritimati` (UTC+14), a naive `datetime.now()` reads fourteen hours
    ahead — so a KB minted on one machine and read on another disagrees about when it was made,
    and `pnk doctor`'s age checks compare stamps that never shared a zero point. The zone is
    picked for the size of the gap: at UTC+14 the naive stamp is on a different *date* for ten
    hours of every day, which is what makes this fail loudly rather than by a rounding minute.
    """
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    time.tzset()

    before = datetime.now(UTC)
    created = load(init(tmp_path / "kb").root).kb.created
    after = datetime.now(UTC)

    assert created is not None
    assert before.strftime("%Y%m%d %H:%M") <= created <= after.strftime("%Y%m%d %H:%M"), (
        f"created {created!r} is not the UTC instant "
        f"({before:%Y%m%d %H:%M}..{after:%Y%m%d %H:%M}) — a naive clock would read "
        f"{datetime.now().strftime('%Y%m%d %H:%M')}"
    )


# --- T7: a template declares the files it writes -------------------------------------------------
#
# **Every one of these needs a filesystem-backed template, not the packaged one.** `notes` declares
# no `files` key at all (which is what the historical-two test below asserts), and the symlink cases
# need something `resolve()` can follow — `importlib.resources` hands back a `Traversable`, which
# for a zip-imported package has neither symlinks nor a `resolve()`. `synthetic_template` builds a
# real directory in a real importable package, so `_root` runs its actual `importlib.resources`
# path against it.

MINIMAL_MANIFEST = '[kb]\nname = "{{ name }}"\nid = "{{ kb_id }}"\n'


def test_a_template_without_a_files_key_still_copies_the_historical_two(tmp_path: Path) -> None:
    """Absent means the two files that were hardcoded before T7 — never none.

    Every template in existence declares nothing, `notes` included, so reading an absent key as an
    empty list would silently stop stamping a README and a starter golden set into every new KB.
    """
    target = tmp_path / "kb"
    target.mkdir()

    written, adopted = template.copy_extras("notes", target)

    assert adopted == []
    assert {path.relative_to(target).as_posix() for path in written} == {
        "README.md",
        "eval/questions.yaml",
    }


def test_a_declared_file_list_is_copied_and_an_undeclared_file_is_not(
    synthetic_template: Callable[..., str], tmp_path: Path
) -> None:
    """Three files in the tree, two declared. The third is the discriminator.

    Without it the test would pass under an implementation that ignores `files` entirely and copies
    whatever it finds.
    """
    name = synthetic_template(
        "declared",
        versions={"1.0": MINIMAL_MANIFEST},
        current="1.0",
        files=["README.md", "eval/questions.yaml"],
        extras={
            "README.md": "the template's readme\n",
            "eval/questions.yaml": "questions: []\n",
            "UNDECLARED.md": "never asked for\n",
        },
    )
    target = tmp_path / "kb"
    target.mkdir()

    written, _ = template.copy_extras(name, target)

    assert {path.relative_to(target).as_posix() for path in written} == {
        "README.md",
        "eval/questions.yaml",
    }
    assert not (target / "UNDECLARED.md").exists()
    assert (target / "README.md").read_text(encoding="utf-8") == "the template's readme\n"


def test_a_files_entry_naming_the_version_archive_is_refused(
    synthetic_template: Callable[..., str], tmp_path: Path
) -> None:
    """The property that moved here from T1, where it could not fail.

    While `copy_extras` iterated a hardcoded pair, no `_versions/` path was reachable whatever the
    archive held, so an assertion there was satisfied by the hardcoding rather than by any rule.

    **Asserted on the archive rule's own words, not merely on a raise.** Containment would let this
    entry through — it lands *inside* the target — so a test satisfied by any `TemplateError` would
    stay green under an implementation that has no archive rule at all.
    """
    name = synthetic_template(
        "archived",
        versions={"1.0": MINIMAL_MANIFEST},
        current="1.0",
        files=["_versions/1.0/README.md"],
    )
    target = tmp_path / "kb"
    target.mkdir()

    with pytest.raises(TemplateError) as exc_info:
        template.copy_extras(name, target)

    assert "_versions/1.0/README.md" in exc_info.value.message
    assert "version archive" in exc_info.value.message
    assert not (target / "_versions").exists()


def test_a_template_file_entry_that_escapes_the_target_is_refused(
    synthetic_template: Callable[..., str], tmp_path: Path
) -> None:
    """The lexical case: an entry that walks out of the KB with `..`.

    **The symlink case is a separate test below, and the mutation pass is why.** Both cases lived
    here at first. Removing the destination check then turned this test red on its *first*
    assertion — `../../evil.md` escapes the template as well as the target, so the source-side check
    caught it with a different message — and the run stopped before the symlink case, the one only
    the destination check can catch, ever executed. A test whose later half never runs under the
    mutation it exists to detect is not holding that half.
    """
    lexical = synthetic_template(
        "lexical-escape",
        versions={"1.0": MINIMAL_MANIFEST},
        current="1.0",
        files=["../../evil.md"],
        extras={"README.md": "unused\n"},
    )
    target = tmp_path / "kb"
    target.mkdir()

    with pytest.raises(TemplateError) as exc_info:
        template.copy_extras(lexical, target)

    assert "../../evil.md" in exc_info.value.message
    assert "outside the KB" in exc_info.value.message


def test_a_symlinked_directory_in_the_target_is_refused(
    synthetic_template: Callable[..., str], tmp_path: Path
) -> None:
    """The case only the destination check can catch, and the one a real KB presents.

    No `..`, no absolute path — the escape exists only on disk. It is not exotic: `copy_extras`
    runs against whatever directory is being adopted, and the entry it declares is a perfectly
    ordinary relative path that the template really owns, so the source-side check passes it.
    """
    outside = tmp_path / "outside"
    outside.mkdir()

    symlinked = synthetic_template(
        "symlinked-target",
        versions={"1.0": MINIMAL_MANIFEST},
        current="1.0",
        files=["escape/evil.md"],
        extras={"escape/evil.md": "the template's own copy\n"},
    )
    adopted = tmp_path / "adopted"
    adopted.mkdir()
    (adopted / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(TemplateError) as exc_info:
        template.copy_extras(symlinked, adopted)

    assert "escape/evil.md" in exc_info.value.message
    assert "outside the KB" in exc_info.value.message
    assert not (outside / "evil.md").exists(), "the write happened before the refusal"


def test_a_template_file_entry_that_reads_outside_the_template_is_refused(
    synthetic_template: Callable[..., str], tmp_path: Path
) -> None:
    """The read side, which the write-side check cannot catch — it is a second layer.

    A symlinked directory in the *template* tree lands its destination perfectly inside the KB;
    what escapes is the source. The file it names is then copied **into** the KB and published with
    it, which for a repo meant to be committed is the more expensive direction of the two.
    """
    secret = tmp_path / "elsewhere"
    secret.mkdir()
    (secret / "id_rsa").write_text("not the template's to give away\n", encoding="utf-8")

    name = synthetic_template(
        "reads-out",
        versions={"1.0": MINIMAL_MANIFEST},
        current="1.0",
        files=["borrowed/id_rsa"],
    )
    root = template._root(name)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(root, Path), "the fixture must build a real directory for a symlink to exist"
    root.joinpath("borrowed").symlink_to(secret, target_is_directory=True)

    target = tmp_path / "kb"
    target.mkdir()

    with pytest.raises(TemplateError) as exc_info:
        template.copy_extras(name, target)

    assert "borrowed/id_rsa" in exc_info.value.message
    assert "outside the template" in exc_info.value.message
    assert not (target / "borrowed").exists()
