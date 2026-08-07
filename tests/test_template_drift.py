"""`tools/template_drift_gate.py`, driven as a subprocess — one test per leg it can fail.

A subprocess rather than an import, for the reason `tests/test_status_header_gate.py` gives: it
exercises the same artifact `check.sh` and CI run, argument parsing included. `--templates` exists
so every mutation is written to a temp copy and the real `src/pinakes/templates/` is never touched.

**The fixtures never compute a content hash themselves — they ask the gate for it**, through its
`--print-hash` flag. A fixture that re-implemented the hash would drift from the gate, the gate
would win, and the failure would surface as an unrelated red test in an unrelated increment. Asking
over a command line rather than importing keeps the house rule above intact: no `sys.path` surgery,
and nothing here that a type checker cannot follow.

**Every failing branch asserts which leg reported, never merely that the gate exited non-zero.**
Seven legs run over the same tree, so "the gate failed" is evidence for none of them in particular
— and the recurring defect in this family of gates is a leg that fires for the wrong reason and
looks correct from the exit code.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
TOOL = REPO / "tools" / "template_drift_gate.py"
REAL_TEMPLATES = REPO / "src" / "pinakes" / "templates"

PDF_COMMENT = '# Add "**/*.pdf" to `include` above to index PDFs.'


def run(templates: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--templates", str(templates), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def content_hash(directory: Path) -> str:
    """The gate's own hash, over its own command line — never a second implementation."""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--print-hash", str(directory)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def ledger_row(name: str, version: str, directory: Path) -> str:
    return (
        f'\n[[template]]\nname    = "{name}"\nversion = "{version}"\n'
        f'sha256  = "{content_hash(directory)}"\n'
    )


def copy_real(tmp_path: Path) -> Path:
    """The shipped templates, copied so a mutation never reaches the repository."""
    destination = tmp_path / "templates"
    shutil.copytree(REAL_TEMPLATES, destination)
    return destination


def two_versions(tmp_path: Path) -> Path:
    """A synthetic `demo` template with **two** archived versions.

    D-2b leaves `notes` with exactly one archived version, so every leg that compares two versions
    — (ii), and (iii)/(vi) reported against a version that is not the live one — is unreachable
    from the shipped template. It is reachable here. `demo` starts as a copy of a real template so
    that it renders; `1.0` is `1.1` minus the PDF-glob comment and with the older `[budget]` caps,
    which is the shape of the real drift this release exists to report.
    """
    templates = copy_real(tmp_path)
    demo = templates / "demo"
    shutil.copytree(templates / "notes", demo, ignore=shutil.ignore_patterns("_versions"))
    demo.joinpath("template.toml").write_text(
        'name = "demo"\nversion = "1.1"\ndescription = "synthetic"\n', encoding="utf-8"
    )
    new = demo.joinpath("pinakes.toml.j2").read_text(encoding="utf-8")
    old = new.replace("per_operation_eur = 0.30", "per_operation_eur = 0.05")
    old = "".join(line for line in old.splitlines(keepends=True) if "**/*.pdf" not in line)
    for version, body in (("1.0", old), ("1.1", new)):
        archived = demo / "_versions" / version
        shutil.copytree(demo, archived, ignore=shutil.ignore_patterns("_versions"))
        archived.joinpath("pinakes.toml.j2").write_text(body, encoding="utf-8")
        archived.joinpath("template.toml").write_text(
            f'name = "demo"\nversion = "{version}"\ndescription = "synthetic"\n', encoding="utf-8"
        )
    ledger = templates / "_versions.toml"
    ledger.write_text(
        ledger.read_text(encoding="utf-8")
        + "".join(ledger_row("demo", v, demo / "_versions" / v) for v in ("1.0", "1.1")),
        encoding="utf-8",
    )
    return templates


def repoint(templates: Path, name: str, version: str) -> None:
    """Rewrite one ledger row to the archive's *current* hash.

    Used only by tests aimed at a leg **after** (iii): without it the tampered archive fails the
    ledger check first and the intended leg never runs.
    """
    directory = templates / name / "_versions" / version
    ledger = templates / "_versions.toml"
    lines = ledger.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(f'version = "{version}"'):
            for offset in range(index, len(lines)):
                if lines[offset].startswith("sha256"):
                    lines[offset] = f'sha256  = "{content_hash(directory)}"\n'
                    ledger.write_text("".join(lines), encoding="utf-8")
                    return
    raise AssertionError(f"no ledger row for {name}@{version}")


# --------------------------------------------------------------------------------------------
# The invariant itself
# --------------------------------------------------------------------------------------------


def test_the_live_template_matches_its_own_archived_version() -> None:
    """The gate's primary predicate, with no flags — the run `check.sh` performs."""
    result = run(REAL_TEMPLATES)
    assert result.returncode == 0, result.stderr
    assert "all legs green" in result.stdout


def test_the_gate_says_which_history_mode_it_ran_in() -> None:
    """ "The gate passed" and "the gate skipped its only history-dependent leg" must never be the
    same observation. Whichever mode leg (vii) ran in, it is named on stdout."""
    result = run(REAL_TEMPLATES)
    assert result.returncode == 0, result.stderr
    assert "history leg" in result.stdout


def test_the_gate_says_leg_two_is_vacuous_against_the_shipped_template() -> None:
    """D-2b leaves `notes` with one archived version, so leg (ii) has nothing to compare. A gate
    reporting a clean pass for a leg that has never run is the defect this release exists to fix,
    reproduced in the gate itself — so it says so instead."""
    result = run(REAL_TEMPLATES)
    assert result.returncode == 0, result.stderr
    assert "leg (ii)" in result.stdout
    assert "vacuous" in result.stdout


# --------------------------------------------------------------------------------------------
# Leg (i) — the live files against their own archived copy
# --------------------------------------------------------------------------------------------


def test_editing_a_consumed_file_without_bumping_the_version_fails_the_gate(tmp_path: Path) -> None:
    """F1: the drift that shipped ten times under one version number, caught."""
    templates = copy_real(tmp_path)
    manifest = templates / "notes" / "pinakes.toml.j2"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("final_k               = 8", "final_k = 4"),
        encoding="utf-8",
    )
    result = run(templates)
    assert result.returncode == 1
    assert "differ from archived 1.1" in result.stderr
    assert "pinakes.toml.j2 differs" in result.stderr


def test_editing_only_a_comment_fails_the_gate(tmp_path: Path) -> None:
    """D-3 option A and F2 together. The PDF-glob comment block is the entire content of the live
    gap F3 names — it is how a user learns PDFs need a glob. A gate that compared TOML keys and
    values would pass here while being blind to the one thing users are harmed by missing."""
    templates = copy_real(tmp_path)
    manifest = templates / "notes" / "pinakes.toml.j2"
    body = manifest.read_text(encoding="utf-8")
    assert PDF_COMMENT in body, "the comment this test is about moved; re-aim it"
    manifest.write_text(body.replace(PDF_COMMENT, "# " + PDF_COMMENT), encoding="utf-8")
    result = run(templates)
    assert result.returncode == 1
    assert "pinakes.toml.j2 differs" in result.stderr


def test_editing_the_template_readme_fails_the_gate(tmp_path: Path) -> None:
    """The `docs/KB-UPDATES.md` §6 correction: that document exempts `README.md` from the hash.
    `copy_extras` copies it into every KB, so it is consumed, and exempting it would let the copy
    in a user's KB drift from the template with no bump — the exact failure this gate prevents."""
    templates = copy_real(tmp_path)
    readme = templates / "notes" / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nA new line.\n", encoding="utf-8")
    result = run(templates)
    assert result.returncode == 1
    assert "README.md differs" in result.stderr


def test_a_new_consumed_file_is_covered_without_editing_the_gate(tmp_path: Path) -> None:
    """The exclude-list choice. A template that gains a file is covered by default; an
    include-list would silently not cover it, which is the failure mode that cannot be seen."""
    templates = copy_real(tmp_path)
    (templates / "notes" / "PROMPTS.md").write_text("a new consumed file\n", encoding="utf-8")
    result = run(templates)
    assert result.returncode == 1
    assert "PROMPTS.md is live-only" in result.stderr


def test_the_archive_itself_is_outside_the_hash(tmp_path: Path) -> None:
    """`_versions/` is excluded from the live hash, or archiving version N would change the
    content hashed for version N+1 and every bump would invalidate every earlier one."""
    templates = copy_real(tmp_path)
    live = content_hash(templates / "notes")
    shutil.copytree(
        templates / "notes" / "_versions" / "1.1", templates / "notes" / "_versions" / "0.9"
    )
    assert content_hash(templates / "notes") == live


# --------------------------------------------------------------------------------------------
# Legs (ii)-(vi)
# --------------------------------------------------------------------------------------------


def test_a_bumped_version_with_no_archived_directory_fails(tmp_path: Path) -> None:
    """Leg (v) — the archive can never fall behind the version that names it."""
    templates = copy_real(tmp_path)
    declaration = templates / "notes" / "template.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace('version = "1.1"', 'version = "1.2"'),
        encoding="utf-8",
    )
    result = run(templates)
    assert result.returncode == 1
    assert "notes@1.2 is the live version but is not archived" in result.stderr


def test_a_version_bump_with_no_content_change_fails_the_gate(tmp_path: Path) -> None:
    """Leg (ii), and it is reachable **only because `template.toml` is outside the content hash**
    — re-include it and the declared version alone makes every pair of versions differ, so this
    test could never fail. Needs two archived versions; against `notes` the leg is vacuous."""
    templates = two_versions(tmp_path)
    demo = templates / "demo"
    shutil.rmtree(demo / "_versions" / "1.0")
    shutil.copytree(demo / "_versions" / "1.1", demo / "_versions" / "1.0")
    demo.joinpath("_versions", "1.0", "template.toml").write_text(
        'name = "demo"\nversion = "1.0"\ndescription = "synthetic"\n', encoding="utf-8"
    )
    repoint(templates, "demo", "1.0")
    result = run(templates)
    assert result.returncode == 1
    assert "identical content" in result.stderr
    assert "1.0" in result.stderr and "1.1" in result.stderr


def test_a_modified_archived_version_fails_against_the_ledger(tmp_path: Path) -> None:
    """Leg (iii) — an archived version cannot be edited in one file and go unnoticed.

    The tampered version is the **older** one, not the live one, so what is proved is leg (iii)
    and not leg (i): editing the live version's archive also makes the live files differ from it,
    and a gate that checked (i) first would send the reader to bump a version when a published one
    needs restoring instead.

    The tampered file is `eval/questions.yaml`, not `README.md`: the README is the subject of
    `test_editing_the_template_readme_fails_the_gate`, and sharing a vector made a mutation that
    exempted the README fail this test too — one assertion's mutant should not travel."""
    templates = two_versions(tmp_path)
    archived = templates / "demo" / "_versions" / "1.0" / "eval" / "questions.yaml"
    archived.write_text(archived.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
    result = run(templates)
    assert result.returncode == 1
    assert "demo@1.0 does not match its `_versions.toml` row" in result.stderr


def test_editing_the_live_versions_archive_is_reported_as_a_ledger_failure(tmp_path: Path) -> None:
    """The ordering, stated as its own assertion. Tampering with `_versions/<live>/` trips (iii),
    whose remedy is *restore the archive* — never (i), whose remedy is *bump the version*."""
    templates = two_versions(tmp_path)
    archived = templates / "demo" / "_versions" / "1.1" / "eval" / "questions.yaml"
    archived.write_text(archived.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
    result = run(templates)
    assert result.returncode == 1
    assert "demo@1.1 does not match its `_versions.toml` row" in result.stderr
    assert "differ from archived" not in result.stderr


def test_a_ledger_row_with_no_archived_directory_fails(tmp_path: Path) -> None:
    """Leg (iv), the direction the per-version walk cannot see: a row survives the deletion of the
    directory it describes, and nothing else in the gate iterates rows."""
    templates = copy_real(tmp_path)
    ledger = templates / "_versions.toml"
    ledger.write_text(
        ledger.read_text(encoding="utf-8")
        + '\n[[template]]\nname    = "notes"\nversion = "9.9"\nsha256  = "deadbeef"\n',
        encoding="utf-8",
    )
    result = run(templates)
    assert result.returncode == 1
    assert "no archived directory: notes@9.9" in result.stderr


def test_an_archived_version_that_no_longer_renders_fails_the_gate(tmp_path: Path) -> None:
    """Leg (vi) — archive rot. Without it the archive decays silently and the failure surfaces
    years later inside a user's `pnk upgrade`, on the one side of a diff they cannot inspect."""
    templates = two_versions(tmp_path)
    archived = templates / "demo" / "_versions" / "1.0" / "pinakes.toml.j2"
    archived.write_text(
        archived.read_text(encoding="utf-8") + "\n{{ a_variable_this_build_does_not_supply }}\n",
        encoding="utf-8",
    )
    repoint(templates, "demo", "1.0")
    result = run(templates)
    assert result.returncode == 1
    assert "demo@1.0 no longer renders" in result.stderr
    assert "a_variable_this_build_does_not_supply" in result.stderr


def test_a_missing_ledger_row_names_the_row_to_add(tmp_path: Path) -> None:
    """A gate that says only *no row* leaves the reader to recompute a SHA-256 by hand, and a
    hand-computed hash is how a fixture drifts from the gate in the first place."""
    templates = two_versions(tmp_path)
    ledger = templates / "_versions.toml"
    kept = [
        block
        for block in ledger.read_text(encoding="utf-8").split("[[template]]")
        if 'version = "1.0"' not in block
    ]
    ledger.write_text("[[template]]".join(kept), encoding="utf-8")
    result = run(templates)
    assert result.returncode == 1
    assert "demo@1.0 is archived but has no `_versions.toml` row" in result.stderr
    assert content_hash(templates / "demo" / "_versions" / "1.0") in result.stderr


# --------------------------------------------------------------------------------------------
# Leg (vii) — history, and the skip that is not a pass
# --------------------------------------------------------------------------------------------


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def published_repo(tmp_path: Path) -> Path:
    """A git repository whose archive has **shipped** — committed and on `origin/main`.

    Leg (vii) asks whether a version that already shipped has been edited, so every test below
    needs a notion of *published*. `update-ref` fakes the remote-tracking ref directly rather than
    cloning: what the gate reads is `origin/main`, and how it came to exist is not its business.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "T")
    shutil.copytree(REAL_TEMPLATES, repo / "templates")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the archive as published")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def coordinated_edit(repo: Path) -> None:
    """The three-file edit: live `.j2`, its archived copy, and the ledger row — in one commit.

    Every content leg passes afterwards: the live files match the archive, the archive matches the
    ledger, the version is unchanged and still archived. Only history can see it.
    """
    templates = repo / "templates"
    live = templates / "notes" / "pinakes.toml.j2"
    edited = live.read_text(encoding="utf-8").replace(
        "confirm_above_eur = 0.01", "confirm_above_eur = 0.02"
    )
    live.write_text(edited, encoding="utf-8")
    (templates / "notes" / "_versions" / "1.1" / "pinakes.toml.j2").write_text(
        edited, encoding="utf-8"
    )
    repoint(templates, "notes", "1.1")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "three files, one commit, version untouched")


def coordinated_edit_repo(tmp_path: Path) -> Path:
    repo = published_repo(tmp_path)
    coordinated_edit(repo)
    return repo


def test_a_three_file_edit_is_caught_by_the_history_leg(tmp_path: Path) -> None:
    """Leg (vii), and the reason it exists — caught **before** it merges.

    Asserts **which** leg reported: a test satisfied by any non-zero exit would be satisfied by
    the other six legs too, and every one of them passes on this tree — which is checked here, not
    assumed, by asserting the content legs' own failure wordings are absent."""
    repo = coordinated_edit_repo(tmp_path)
    result = run(repo / "templates", "--repo", str(repo))
    assert result.returncode == 1
    assert "edited after it shipped" in result.stderr
    assert "notes/_versions/1.1" in result.stderr
    assert "differs from origin/main" in result.stderr
    assert "differ from archived" not in result.stderr
    assert "does not match its `_versions.toml` row" not in result.stderr


def test_an_archive_edited_after_it_shipped_is_caught_once_both_commits_have_landed(
    tmp_path: Path,
) -> None:
    """The other half of leg (vii). The in-flight check above compares the working tree against
    `origin/main`; once the offending commit *is* on `origin/main` that comparison is clean, and
    only the landed-commit count can still see it."""
    repo = coordinated_edit_repo(tmp_path)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    result = run(repo / "templates", "--repo", str(repo))
    assert result.returncode == 1
    assert "edited after it shipped" in result.stderr
    assert "2 commits on origin/main" in result.stderr


def test_adding_an_archive_then_correcting_it_before_landing_is_not_an_edit(
    tmp_path: Path,
) -> None:
    """The false positive that the first version of this leg had, and it blocked the project's own
    procedure. `docs/BUILDING.md` requires a green `./check.sh` **before** review and review fixes
    in **their own commit**, so a branch that adds an archived version and then corrects it during
    review has two commits touching it — on a version that has never shipped. Counting every commit
    failed that branch and told its author the archive *"still says what the version said when it
    shipped"*, about something that had not shipped. The escape — amend or rebase — is exactly the
    operation that also defeats the leg."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "T")
    (repo / "unrelated.txt").write_text(
        "a repository that predates the archive\n", encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "before any template")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    templates = repo / "templates"
    shutil.copytree(REAL_TEMPLATES, templates)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "add the archive")

    readme = templates / "notes" / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nA review fix.\n", encoding="utf-8")
    (templates / "notes" / "_versions" / "1.1" / "README.md").write_text(
        readme.read_text(encoding="utf-8"), encoding="utf-8"
    )
    repoint(templates, "notes", "1.1")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "review fix, its own commit as BUILDING.md requires")

    result = run(templates, "--repo", str(repo))
    assert result.returncode == 0, result.stderr
    assert "history leg (vii) ran" in result.stdout
    assert "new" in result.stdout


def test_the_history_leg_skips_when_there_is_no_published_branch(tmp_path: Path) -> None:
    """A repository with history but nothing to call published cannot answer leg (vii)'s question,
    and says so rather than guessing. Falling back to counting every commit is what produced the
    false positive above."""
    repo = coordinated_edit_repo(tmp_path)
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    git(repo, "branch", "-m", "not-main")

    result = run(repo / "templates", "--repo", str(repo))
    assert result.returncode == 0, result.stderr
    assert "leg (vii) skipped: no published branch here" in result.stdout


def test_a_relative_templates_path_does_not_let_the_history_leg_claim_it_ran(
    tmp_path: Path,
) -> None:
    """The pathspec bug, pinned. `--templates` given a relative path used to leave leg (vii)
    building a pathspec relative to the *process* cwd while git resolved it against the templates
    directory: it matched nothing, `git log` returned empty, and the gate printed
    `history leg (vii) ran` over the coordinated edit below — reporting the strong mode having
    checked nothing, which is the one outcome the module docstring forbids."""
    repo = coordinated_edit_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(TOOL), "--templates", "templates", "--repo", "."],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout
    assert "edited after it shipped" in result.stderr


def test_the_gate_names_its_reason_when_it_cannot_run(tmp_path: Path) -> None:
    """The skip path, and that the skip is a **real loss of coverage** rather than a formality.

    The same three-file edit `test_a_three_file_edit_is_caught_by_the_history_leg` catches is run
    here against a tree with no git history: the gate exits 0. That is the honest degradation the
    module docstring's limit (a) describes, and a test asserting only the printed reason would not
    show that anything was lost."""
    repo = coordinated_edit_repo(tmp_path)
    shutil.rmtree(repo / ".git")

    result = run(repo / "templates", "--repo", str(repo))
    assert result.returncode == 0, result.stderr
    assert (
        "leg (vii) skipped: no git history here (shallow clone or not a checkout)" in result.stdout
    )
    assert "all legs green" in result.stdout


def test_a_shallow_clone_skips_the_history_leg_rather_than_passing_it(tmp_path: Path) -> None:
    """A shallow clone is the CI case, and it is why the skip is detected explicitly instead of
    being inferred from an empty `git log`: in a shallow clone `git log -- <path>` returns nothing
    for every path, which reads as "one commit or fewer" and would let the gate report the strong
    mode while checking nothing."""
    origin = coordinated_edit_repo(tmp_path)
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", f"file://{origin}", str(shallow)],
        check=True,
        capture_output=True,
    )
    assert (
        subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=shallow,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == "true"
    )
    result = run(shallow / "templates", "--repo", str(shallow))
    assert result.returncode == 0, result.stderr
    assert "leg (vii) skipped" in result.stdout


def test_an_uncommitted_archive_is_not_an_edit(tmp_path: Path) -> None:
    """An archive that is not committed at all is new, not frozen. The increment that *adds* one
    runs `./check.sh` before committing it, so this is the state the gate first sees."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "T")
    templates = repo / "templates"
    shutil.copytree(REAL_TEMPLATES, templates)
    (repo / "unrelated.txt").write_text("so the repository has a commit\n", encoding="utf-8")
    git(repo, "add", "unrelated.txt")
    git(repo, "commit", "-qm", "unrelated")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    result = run(templates, "--repo", str(repo))
    assert result.returncode == 0, result.stderr
    assert "history leg (vii) ran" in result.stdout


# --------------------------------------------------------------------------------------------
# The template-name hole the archive makes reachable
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["notes/_versions/1.1", "notes/../notes", "../templates/notes", "notes/eval", "_versions"],
)
def test_a_template_name_with_a_path_separator_or_dotdot_is_refused(name: str) -> None:
    """Step 6, and it fails on `main` as this increment starts.

    `_root` joined an unvalidated name onto the package root: `describe("notes/../notes")` and
    `describe("../templates/notes")` both **succeeded**, and `describe("notes/eval")` raised a bare
    `FileNotFoundError` rather than a `PinakesError` — so `cli.main` printed a traceback. Harmless
    only while every directory under the package root was a template; `_versions/` ends that,
    because `pnk init --template notes/_versions/1.1` would stamp a KB from an archived version
    nobody released."""
    from pinakes.errors import TemplateError
    from pinakes.template import describe

    with pytest.raises(TemplateError) as caught:
        describe(name)
    assert "no template named" in str(caught.value)
    assert "notes" in (caught.value.remedy or "")


def test_a_valid_template_name_still_resolves() -> None:
    """The name check refuses a shape, never the shipped template — the mutation that deletes the
    check must fail the test above, and the mutation that over-tightens it must fail this one."""
    from pinakes.template import available, describe

    assert available() == ["notes"]
    assert describe("notes").name == "notes"


# --------------------------------------------------------------------------------------------
# The two functions everything after this increment reads the archive through
# --------------------------------------------------------------------------------------------


def test_archived_versions_lists_exactly_what_is_archived() -> None:
    """D-2b, as an assertion rather than a claim: `1.0` is never archived, because it denotes
    eleven different template contents and any seed would be a guess for ten of them."""
    from pinakes.template import archived_versions, describe

    versions = archived_versions("notes")
    assert versions == [describe("notes").version]
    assert "1.0" not in versions


def test_archived_versions_sorts_by_version_not_by_string() -> None:
    from pinakes.template import version_key

    assert sorted(["1.10", "1.9", "1.2"], key=version_key) == ["1.2", "1.9", "1.10"]


def test_render_archived_renders_the_archived_manifest() -> None:
    from pinakes.init import DEFAULT_EMBEDDING, DEFAULT_RERANK
    from pinakes.template import describe, render_archived

    provider, model, dim = DEFAULT_EMBEDDING
    rerank_provider, rerank_model = DEFAULT_RERANK
    rendered = render_archived(
        "notes",
        describe("notes").version,
        {
            "name": "kb",
            "kb_id": "01JZZZZZZZZZZZZZZZZZZZZZZZ",
            "template": "notes@1.1",
            "created": "20200101 00:00",
            "embedding_provider": provider,
            "embedding_model": model,
            "embedding_dim": dim,
            "rerank_provider": rerank_provider,
            "rerank_model": rerank_model,
        },
    )
    assert 'name     = "kb"' in rendered
    assert "{{" not in rendered


def test_render_archived_refuses_a_version_that_is_not_archived() -> None:
    """The *cannot compare* path's source of truth: it names the version and what is archived,
    because a KB recording `notes@1.0` is every KB in existence and the message is what its owner
    reads."""
    from pinakes.errors import TemplateError
    from pinakes.template import render_archived

    with pytest.raises(TemplateError) as caught:
        render_archived("notes", "1.0", {})
    assert "notes@1.0 is not archived" in str(caught.value)
    assert "1.1" in (caught.value.remedy or "")


@pytest.mark.parametrize("version", ["../../notes", "..", "a/b"])
def test_an_archived_version_with_a_path_separator_is_refused(version: str) -> None:
    """The same hole as the template name, one level down — and this one is reached from a KB's
    `pinakes.toml`, a file Pinakes does not write and a user can put anything in."""
    from pinakes.errors import TemplateError
    from pinakes.template import archived_root

    with pytest.raises(TemplateError) as caught:
        archived_root("notes", version)
    assert "not a version this build can read" in str(caught.value)


# --------------------------------------------------------------------------------------------
# The hash itself
# --------------------------------------------------------------------------------------------


def test_the_declaration_is_outside_the_content_hash(tmp_path: Path) -> None:
    """The exclusion leg (ii) stands on. Hashing `template.toml` would make every bump change the
    hash by construction, and "a version bumped with no content change" could never be detected."""
    templates = copy_real(tmp_path)
    notes = templates / "notes"
    before = content_hash(notes)
    declaration = notes / "template.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace('version = "1.1"', 'version = "7.7"'),
        encoding="utf-8",
    )
    assert content_hash(notes) == before


def test_the_hash_covers_the_path_as_well_as_the_bytes(tmp_path: Path) -> None:
    """Moving a file between two names is a change, even when every byte survives."""
    templates = copy_real(tmp_path)
    notes = templates / "notes"
    before = content_hash(notes)
    (notes / "README.md").rename(notes / "READ-ME.md")
    assert content_hash(notes) != before


# --------------------------------------------------------------------------------------------
# The gate is wired in — the omission that makes every test above worthless
# --------------------------------------------------------------------------------------------


def test_the_gate_is_invoked_by_check_sh() -> None:
    """A gate nothing runs is a gate that does not exist, and nothing else here would notice.

    Deleting the `check.sh` line and the whole CI job leaves all thirty-odd tests in this file
    green: they drive the tool directly, so they pin its behaviour and say nothing about whether
    anything calls it."""
    body = (REPO / "check.sh").read_text(encoding="utf-8")
    assert "tools/template_drift_gate.py" in body


def test_the_gate_has_its_own_ci_job_with_full_history() -> None:
    """`ci.yml` never invokes `check.sh`, so a gate in one and not the other runs on nobody's
    machine but the author's. And leg (vii) needs history: GitHub's default checkout is depth 1,
    where the gate skips the leg — so the job carrying this gate is the one checkout in the file
    that must set `fetch-depth: 0`.

    **Parsed, not grepped.** The first version of this test asserted `"fetch-depth: 0" in body`
    and could not fail: the job's own comment explains why the setting is there, so deleting the
    setting left the string behind and the test green. An assertion satisfied by the prose
    describing a configuration is the defect class this repository hunts, reproduced in the test
    written to prevent it.
    """
    import yaml

    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    job = workflow["jobs"]["template-drift"]
    steps = job["steps"]

    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout.get("with", {}).get("fetch-depth") == 0, (
        "the template-drift job's checkout must set fetch-depth: 0, or leg (vii) silently skips"
    )
    assert any("tools/template_drift_gate.py" in str(s.get("run", "")) for s in steps)


# --------------------------------------------------------------------------------------------
# What the hash covers, and what it must not
# --------------------------------------------------------------------------------------------


def test_a_file_git_ignores_is_not_part_of_the_template(tmp_path: Path) -> None:
    """Finder and editors drop files into directories. `.DS_Store` is gitignored, does not reach
    the wheel (measured against a real hatchling build), and used to turn the whole of `check.sh`
    red on a clean checkout — telling the reader to bump the template version and archive it.

    Worse than the noise: the same stray file present while `--print-hash` generated a ledger row
    was folded into the committed sha, leaving the author's tree green and failing only on a clean
    CI checkout, with a remedy pointing at an archive nobody had touched."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    templates = repo / "templates"
    shutil.copytree(REAL_TEMPLATES, templates)

    before = content_hash(templates / "notes")
    (templates / "notes" / ".DS_Store").write_bytes(b"\x00junk")
    assert content_hash(templates / "notes") == before

    result = run(templates, "--repo", str(repo))
    assert result.returncode == 0, result.stderr


def test_an_untracked_file_git_does_not_ignore_is_still_part_of_the_template(
    tmp_path: Path,
) -> None:
    """The other direction, and why the rule is *ignored* rather than *tracked*.

    Hatchling packages the working tree (`artifacts = ["src/pinakes/templates/**"]`), so an
    untracked but un-ignored file really does publish inside the wheel. Hashing git's tracked set
    instead would hash it away and let it ship — and would give a brand-new archive the digest of
    the empty string, because the increment that adds one runs `./check.sh` before committing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    templates = repo / "templates"
    shutil.copytree(REAL_TEMPLATES, templates)

    before = content_hash(templates / "notes")
    (templates / "notes" / "pinakes.toml.j2.orig").write_text("a stray copy\n", encoding="utf-8")
    assert content_hash(templates / "notes") != before

    result = run(templates, "--repo", str(repo))
    assert result.returncode == 1
    assert "pinakes.toml.j2.orig is live-only" in result.stderr


def test_the_hash_is_the_same_where_git_cannot_answer(tmp_path: Path) -> None:
    """An sdist and a vendored copy have no git, and the ledger row still has to match. It does,
    because a file git ignores is never committed and so is not there to be skipped."""
    outside_a_repo = copy_real(tmp_path)
    assert content_hash(outside_a_repo / "notes") == content_hash(REAL_TEMPLATES / "notes")


def test_an_archived_version_without_its_declaration_fails(tmp_path: Path) -> None:
    """The module docstring's limit (b) says an archived `template.toml` has "its presence and its
    directory name checked". It said so while checking neither: an archive missing the file passed
    all seven legs."""
    templates = copy_real(tmp_path)
    (templates / "notes" / "_versions" / "1.1" / "template.toml").unlink()
    result = run(templates)
    assert result.returncode == 1
    assert "archived without a template.toml" in result.stderr


def test_an_archived_version_declaring_a_different_version_fails(tmp_path: Path) -> None:
    """The directory name and the declaration inside it must agree, or `pnk upgrade` reads back a
    version nobody archived."""
    templates = copy_real(tmp_path)
    declaration = templates / "notes" / "_versions" / "1.1" / "template.toml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace('version = "1.1"', 'version = "9.9"'),
        encoding="utf-8",
    )
    result = run(templates)
    assert result.returncode == 1
    assert "declares 9.9" in result.stderr
