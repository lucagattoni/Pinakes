"""`pnk upgrade` — the report, its placement predicate, and its exit codes (T3).

**Every positive path here runs against a synthetic two-version template, never `notes`.** D-2b
leaves the shipped template with exactly one archived version, so the only outcome `notes` can
reach is *cannot compare* — one test below runs against it deliberately, because that is the path
100% of real KBs take, and the rest build the template they need. A suite that quietly exercised
only the reachable path would report green over a feature nobody had run.

**The synthetic template is a *valid* manifest template, not a sketch.** `pnk upgrade` reads the
KB's own `pinakes.toml` as the third input, so the fixture has to be a file `manifest.load` accepts
— and the KB's manifest has to be what that template actually stamps, or every hunk conflicts for
the wrong reason. `_stamp` renders it through the product's own `render_archived`, so a difference
in rendering settings cannot open a gap between the fixture and the thing under test.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from pinakes import template
from pinakes.cli import main
from pinakes.ids import mint_kb_id
from pinakes.upgrade import Outcome, Placement

# The four-line comment block M3 records as the template's real drift: a **pure addition**, no key
# and no value. Its shape is the point — a pure-addition hunk is what makes the order of the
# placement predicate load-bearing — not its wording.
PDF_NOTE = (
    '# Add "**/*.pdf" to `include` above to index PDFs. Left out rather than commented\n'
    "# into place because `init` cannot see whether the extractor is installed: PDF\n"
    '# ingest needs `uv add "pinakes[pdf]"`, and a glob stamped without it turns every\n'
    "# PDF into a failed document."
)

# A commented-out block, because the shipped template ships one and both of its awkward shapes come
# from that: a **calibrated** KB has uncommented it, so a hunk touching those lines cannot be
# placed; and a comment block is the one region a user may legally keep **twice**.
#
# Seven lines, not five, and the count is load-bearing: a hunk carries three lines of context each
# side, so a change in the middle of this block has a window that is *entirely* comments. With five
# lines the window would reach `[rerank]` — a table nobody may duplicate — and the twice-matching
# case would be unbuildable.
CONFIDENCE_LINES = (
    "# Uncomment once `pnk calibrate` has fitted your reranker to your corpus:",
    "# [retrieval.confidence]",
    '# fitted_for = "BAAI/bge-reranker-base@abc123"',
    "# low_below  = 0.31",
    "# high_above = 0.62",
    "# Both are fitted numbers, and nothing infers them for you.",
    "# `pnk calibrate` measures them against your own corpus.",
)
CONFIDENCE_BLOCK = "\n".join(CONFIDENCE_LINES)

# What `pnk calibrate` leaves behind: the table uncommented, the prose around it left alone. Valid
# TOML — which the whole block uncommented would not be, and that is not a detail the test may skip
# past, because an invalid manifest exits `1` and would satisfy "not zero" for the wrong reason.
CALIBRATED_BLOCK = "\n".join(
    line.removeprefix("# ") if 1 <= index <= 4 else line
    for index, line in enumerate(CONFIDENCE_LINES)
)


def _source(
    *,
    pdf_note: bool = False,
    per_operation: str = "0.05",
    low_below: str = "0.31",
    tail_note: bool = False,
) -> str:
    """A manifest template shaped like the shipped one: identity block, rendered values, literals.

    Every default is v1. Each keyword moves exactly one thing, so a test names the drift it is
    about and inherits nothing else:

    | Keyword | The drift it introduces | Hunk shape |
    |---|---|---|
    | `pdf_note` | four comment lines under `[sources]` | pure addition, mid-context |
    | `per_operation` | one `[budget]` value | replacement |
    | `low_below` | one line inside a *commented-out* block | replacement, in comments |
    | `tail_note` | a comment at the end of the file | pure addition, **no trailing context** |

    `tail_note` is the one that looks redundant beside `pdf_note` and is not: with nothing after
    the added lines, the hunk's *before* image (its context alone) is still present once the change
    has been applied, so both placement predicates match and their order decides the answer.
    """
    sources = ["[sources]", 'roots   = ["docs/"]', 'include = ["**/*.md", "**/*.txt"]']
    sources.append('exclude = ["**/drafts/**"]')
    if pdf_note:
        sources.append(PDF_NOTE)

    body = [
        "[kb]",
        'name     = "{{ name }}"',
        'id       = "{{ kb_id }}"',
        'template = "{{ template }}"',
        'created  = "{{ created }}"',
        "",
        "\n".join(sources),
        "",
        "[embedding]",
        'provider = "{{ embedding_provider }}"',
        'model    = "{{ embedding_model }}"',
        "dim      = {{ embedding_dim }}",
        "",
        "[chunking]",
        'strategy   = "structural"',
        "max_tokens = 510",
        "overlap    = 64",
        "",
        "[retrieval]",
        "candidates_per_source = 50",
        'fusion                = "rrf"',
        "fusion_top_k          = 20",
        "final_k               = 8",
        'rerank                = "local"',
        'vector_tier           = "auto"',
        "",
        CONFIDENCE_BLOCK.replace("0.31", low_below),
        "",
        "[rerank]",
        'provider = "{{ rerank_provider }}"',
        'model    = "{{ rerank_model }}"',
        "",
        "[budget]",
        "confirm_above_eur = 0.01",
        f"per_operation_eur = {per_operation}",
        "monthly_eur       = 5.00",
        'timezone          = "UTC"',
        'on_exceed         = "abort"',
    ]
    if tail_note:
        body.append("# Written by a later template version, at the very end of the file.")
    return "\n".join(body) + "\n"


def _stamp(root: Path, name: str, version: str, *, records: str | None = None) -> Path:
    """Write the KB that `pnk init` from *version* would have written.

    *records* overrides what `[kb] template` says, which is how the two interesting shapes are
    built: a KB stamped from an old version (the ordinary case), and a KB carrying the **new**
    version's text while still recording the old reference — a user who read `pnk doctor` and
    adopted the change by hand. Both sides of the comparison render the *recorded* reference, so
    `[kb]` is byte-identical on both and can never produce a hunk of its own.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    context = {
        "name": "research",
        "kb_id": str(mint_kb_id()),
        "template": records or f"{name}@{version}",
        "created": "20260725 09:14",
        "embedding_provider": "sentence-transformers",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "embedding_dim": 384,
        "rerank_provider": "sentence-transformers",
        "rerank_model": "BAAI/bge-reranker-base",
    }
    (root / "pinakes.toml").write_text(
        template.render_archived(name, version, context), encoding="utf-8"
    )
    return root


def _two_versions(
    synthetic_template: Callable[..., str], *, old: str | None = None, new: str | None = None
) -> str:
    """The default pair reproduces M3's shape: a pure addition and a `[budget]` value change."""
    return synthetic_template(
        "synth",
        versions={
            "1.0": old if old is not None else _source(),
            "2.0": new if new is not None else _source(pdf_note=True, per_operation="0.30"),
        },
        current="2.0",
    )


def _run(root: Path, *flags: str) -> tuple[int, str]:
    """`pnk upgrade` through `cli.main`, so dispatch and the exit code are under test too."""
    import io
    from contextlib import redirect_stdout

    captured = io.StringIO()
    with redirect_stdout(captured):
        code = main(["upgrade", "--kb", str(root), *flags])
    return code, captured.getvalue()


def _placements(output: str) -> list[tuple[str, str]]:
    """Every `(placement, header)` pair the human listing carries, in order."""
    found: list[tuple[str, str]] = []
    for line in output.splitlines():
        match = re.match(r"\s+(applies cleanly|already applied|conflicts)\s+(.*?)(@@ .*@@)$", line)
        if match:
            found.append((match.group(1), match.group(3)))
    return found


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under the KB, by relative path, with its bytes.

    The **path set** is compared as well as the contents, because "writes nothing" is a claim about
    the directory and a snapshot of one file would be satisfied by a command that wrote a different
    one. Bytes rather than mtimes: an mtime comparison passes for a rewrite of identical content.
    """
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_a_current_kb_prints_up_to_date_and_writes_nothing(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "2.0")
    before = _tree(root)

    code, out = _run(root)

    assert code == 0
    assert "up to date" in out
    assert "@@" not in out, "there is no diff to print when the versions agree"
    assert _tree(root) == before


def test_a_drifted_kb_prints_the_template_diff(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Assert on **content**, never on a line count. An earlier draft of the plan asserted "the six
    comment lines of M3"; two commits later that was wrong on the count, on the composition, and on
    their being comments.

    The content asserted is the whole of M3's shape: the added comment line, and **both** the old
    and the new cap — a diff showing only the new value would be a diff a user cannot judge.
    """
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out = _run(root)

    assert code == 0
    assert "to `include` above to index PDFs" in out
    assert "-per_operation_eur = 0.05" in out
    assert "+per_operation_eur = 0.30" in out
    assert "synth@1.0" in out and "synth@2.0" in out


def test_a_hunk_already_present_in_theirs_is_reported_as_already_applied(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Not *clean*, and not *conflict*. A user who read `pnk doctor`'s report and adopted the
    change by hand is the ordinary case this command is for: calling it clean makes a later
    `--apply` re-insert lines that are already there — duplicating a key, which is a TOML
    duplicate-key error — and calling it a conflict tells someone who did the right thing that
    they have a problem.

    **The fixture is synthetic and unconditional.** D-2b neither creates nor removes this outcome —
    it arises under every seeding answer — but it does make it unreachable from `notes`, so the
    two-version template here is not over-engineering and should not be deleted as such.
    """
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "2.0", records="synth@1.0")

    code, out = _run(root)

    assert code == 0
    assert [placement for placement, _ in _placements(out)] == [
        "already applied",
        "already applied",
    ]
    assert "applies cleanly" not in out and "conflicts" not in out


def test_a_pure_addition_already_present_is_already_applied_not_clean(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The test that pins the **order** of the placement predicate, and the only one that can.

    A hunk whose added lines sit at the end of its context — here, a comment appended to the end of
    the file — has a *before* image that is still present after the change has been applied. Both
    predicates match; whichever runs first decides. `already applied` must win, or a later
    `--apply` appends the line a second time.

    `pdf_note`'s mid-context addition cannot pin this: inserting into the middle of the context
    breaks the *before* image's contiguity, so predicate 2 fails on its own and the order never
    comes up.
    """
    name = _two_versions(synthetic_template, old=_source(), new=_source(tail_note=True))
    root = _stamp(tmp_path / "kb", name, "2.0", records="synth@1.0")

    code, out = _run(root)

    assert code == 0
    assert [placement for placement, _ in _placements(out)] == ["already applied"]


def test_a_user_edited_region_is_reported_as_a_conflict_not_applied(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """And the other hunk still places — a test where *everything* conflicts would be satisfied by
    an implementation that reported `conflict` unconditionally."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    edited, count = re.subn(
        r"^per_operation_eur = 0\.05$",
        "per_operation_eur = 0.10",
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert count == 1, "the fixture's budget line has changed shape"
    path.write_text(edited, encoding="utf-8")

    code, out = _run(root)

    assert code == 0
    assert sorted(placement for placement, _ in _placements(out)) == [
        "applies cleanly",
        "conflicts",
    ]
    assert "[budget]" in out


def test_a_kb_with_links_kb_entries_still_places_unambiguous_hunks(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`[[links.kb]]` entries are appended after `[budget]` in a real KB, which puts unrelated text
    directly after the region the budget hunk's trailing context covers. Near-universal, and a
    fixture rather than a thought experiment."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + f'\n[[links.kb]]\nname = "partner"\nid   = "{mint_kb_id()}"\npath = "../partner-kb"\n',
        encoding="utf-8",
    )

    code, out = _run(root)

    assert code == 0
    assert [placement for placement, _ in _placements(out)] == [
        "applies cleanly",
        "applies cleanly",
    ]


def test_a_kb_with_an_uncommented_retrieval_confidence_table_conflicts_on_that_region(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`pnk calibrate` writes `[retrieval.confidence]` into the region the template ships as a
    *comment*, so any hunk touching those lines conflicts for every calibrated KB. That is the
    honest answer — the lines the hunk expects are genuinely not there — and it must be reported
    rather than resolved."""
    name = _two_versions(synthetic_template, old=_source(), new=_source(low_below="0.35"))
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    assert CONFIDENCE_BLOCK in body, "the fixture's commented block has changed shape"
    path.write_text(body.replace(CONFIDENCE_BLOCK, CALIBRATED_BLOCK), encoding="utf-8")

    code, out = _run(root)

    assert code == 0, "an invalid manifest would exit 1 and satisfy a weaker assertion"
    assert [placement for placement, _ in _placements(out)] == ["conflicts"]


def test_a_user_edit_the_template_never_touched_appears_nowhere_in_the_output(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The counterpart that fails the moment `base` or `ours` is replaced by the user's own file.

    A line the user changed and the template did not is not drift, and this command has nothing to
    say about it — which is a property of `base → ours` being the only diff computed, not a filter
    applied afterwards.
    """
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    edited, count = re.subn(
        r"^final_k               = 8$",
        "final_k               = 4",
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert count == 1, "the fixture's retrieval block has changed shape"
    path.write_text(
        edited + "\n# A comment of my own, which is nobody's business but mine.\n", encoding="utf-8"
    )

    code, out = _run(root)

    assert code == 0
    assert "final_k" not in out
    assert "nobody's business" not in out


def test_a_reordered_manifest_is_a_conflict_not_a_silent_success(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Order is part of the predicate, not a refinement of it.

    The reordering here is **inside** the hunk's own window — two keys of `[budget]` swapped — so
    every line the hunk expects is present and only their order has changed. A rule that asked
    "are these lines in the file?" would report *clean* and place the hunk at an offset that means
    nothing.
    """
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    edited, count = re.subn(
        "per_operation_eur = 0.05\nmonthly_eur       = 5.00",
        "monthly_eur       = 5.00\nper_operation_eur = 0.05",
        path.read_text(encoding="utf-8"),
    )
    assert count == 1, "the fixture's budget block has changed shape"
    path.write_text(edited, encoding="utf-8")

    code, out = _run(root)

    assert code == 0
    placements = sorted(placement for placement, _ in _placements(out))
    assert placements == ["applies cleanly", "conflicts"]


def test_a_hunk_whose_context_matches_twice_is_a_conflict(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Uniqueness is part of the predicate. A manifest is comment-dense by design, so a user who
    kept a second copy of a commented-out block — legal TOML, and a plausible thing to do while
    deciding — gives a hunk two places it could go. Two is not one, and the command does not
    guess."""
    name = _two_versions(synthetic_template, old=_source(), new=_source(low_below="0.35"))
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    assert body.count(CONFIDENCE_BLOCK) == 1
    path.write_text(body + "\n" + CONFIDENCE_BLOCK + "\n", encoding="utf-8")

    code, out = _run(root)

    assert code == 0
    assert [placement for placement, _ in _placements(out)] == ["conflicts"]


def test_a_manifest_with_extra_tables_still_places_unambiguous_hunks(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The over-tightening counterpart. `[extraction]` is a table the template does not stamp and a
    real KB often has; if a later pass made every such KB a conflict, this is what would say so."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + '\n[extraction]\nbackend = "pypdfium2"\n',
        encoding="utf-8",
    )

    code, out = _run(root)

    assert code == 0
    assert [placement for placement, _ in _placements(out)] == [
        "applies cleanly",
        "applies cleanly",
    ]


def test_nothing_under_the_kb_is_written(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The whole tree, bytes and path set, before and after — on the path that has the most to say.

    A test watching `pinakes.toml` alone would be satisfied by a command that wrote a different
    file; one comparing mtimes would be satisfied by a rewrite of identical content.
    """
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    before = _tree(root)

    code, out = _run(root)

    assert code == 0
    assert "@@" in out, "a run with nothing to report would satisfy this test for the wrong reason"
    assert _tree(root) == before


def test_json_and_human_output_report_the_same_hunks(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    human_code, human = _run(root)
    json_code, raw = _run(root, "--json")
    payload = json.loads(raw)

    assert human_code == json_code == 0
    by_label = {placement.label: placement for placement in Placement}
    assert [(hunk["placement"], hunk["header"]) for hunk in payload["hunks"]] == [
        (by_label[label].value, header) for label, header in _placements(human)
    ]
    assert payload["diff"] in human
    assert payload["counts"]["clean"] == 2


def test_a_version_bump_with_no_manifest_change_says_same_manifest(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """A template version denotes four consumed files and this command reads one of them, so a bump
    that touched only the starter golden set renders two identical manifests. Printing an empty
    diff and calling it agreement is what `pnk doctor`'s fourth outcome was added to stop, and
    `pnk upgrade` inherits the situation rather than discovering it."""
    name = _two_versions(synthetic_template, old=_source(), new=_source())
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out = _run(root)

    assert code == 0
    assert "identical" in out
    assert "@@" not in out


def test_an_unarchived_recorded_version_refuses_with_a_remedy(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The remedy is the part a user acts on, and `cannot compare` alone does not prove one was
    printed. It must also promise nothing a release can keep: an unarchived version's content is
    gone, not pending."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0", records="synth@0.9")

    code, out = _run(root)

    assert code == 3
    assert "cannot compare" in out and "synth@0.9" in out
    assert "compare it by hand" in out.replace("\n", " ")
    assert "there will not be a later one" in out.replace("\n", " ")


def test_the_shipped_template_reaches_the_cannot_compare_path(tmp_path: Path) -> None:
    """Against `notes`, not a synthetic template — because under D-2b this is the path 100% of real
    KBs take and the only one `notes` can reach. `notes@1.0` is deliberately unarchived: it denotes
    eleven different template contents, and a diff computed from the wrong base is worse than no
    diff."""
    from pinakes.init import init

    root = init(tmp_path / "kb", now="20260725 09:14").root
    path = root / "pinakes.toml"
    edited, count = re.subn(
        r'^template = ".+"$',
        'template = "notes@1.0"',
        path.read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1, "the manifest's template line has changed shape"
    path.write_text(edited, encoding="utf-8")

    code, out = _run(root)

    assert code == 3
    assert "notes@1.0 is not in this build's archive" in out


def test_a_template_not_installed_here_cannot_compare(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """A KB stamped from a template this build does not carry — a third-party one, or one dropped
    from a later release. Nothing is wrong with the KB, so it is `3` and not `1`."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0", records="elsewhere@1.0")

    code, out = _run(root)

    assert code == 3
    assert "elsewhere@1.0 is not installed here" in out


def test_a_kb_recording_no_template_cannot_compare(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`[kb] template` is optional, and `pnk doctor` calls such a KB `OK`. A KB one surface calls
    healthy is not an operational failure on another."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    path = root / "pinakes.toml"
    edited, count = re.subn(
        r'^template = ".+"\n', "", path.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE
    )
    assert count == 1, "the fixture's identity block has changed shape"
    path.write_text(edited, encoding="utf-8")

    code, out = _run(root)

    assert code == 3
    assert "records no template" in out


def test_an_archived_version_this_build_cannot_render_cannot_compare(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """A `TemplateError` from the renderer would otherwise reach `cli.main` and become `1`. It is
    the same fact `pnk doctor` reports as *cannot compare*, and two surfaces disagreeing about one
    KB is worse than either wording — so it is caught, named, and exits `3`."""
    name = _two_versions(
        synthetic_template,
        old=_source() + "extra = {{ a_variable_no_build_supplies }}\n",
        new=_source(pdf_note=True),
    )
    root = _stamp(tmp_path / "kb", name, "2.0", records="synth@1.0")

    code, out = _run(root)

    assert code == 3
    assert "cannot compare" in out
    assert "a_variable_no_build_supplies" in out


def test_cannot_compare_exits_three_and_nothing_else_does(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """O-2's first obligation, written so it cannot be satisfied by a command that returns `3` for
    everything: every *other* outcome's code is asserted in the same test.

    `3` means one thing — the comparison could not be made, and no action of the user's would make
    it possible. If a later change gives it a second meaning, this is what goes red.
    """
    name = _two_versions(synthetic_template)
    up_to_date = _stamp(tmp_path / "current", name, "2.0")
    drifted = _stamp(tmp_path / "drifted", name, "1.0")
    unarchived = _stamp(tmp_path / "unarchived", name, "1.0", records="synth@0.9")

    assert _run(up_to_date)[0] == 0
    assert _run(drifted)[0] == 0
    assert _run(unarchived)[0] == 3

    # A conflict is not a failure: this command writes nothing, so it has nothing to fail at, and a
    # non-zero exit here would make `pnk upgrade` unusable beside `pnk doctor` in one script.
    path = drifted / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "per_operation_eur = 0.05", "per_operation_eur = 0.10"
        ),
        encoding="utf-8",
    )
    code, out = _run(drifted)
    assert code == 0
    assert "conflicts" in out


def test_an_operational_failure_still_exits_one(tmp_path: Path) -> None:
    """O-2's second obligation. `3` is not a replacement for `1`; a directory that is not a KB at
    all is the case that cannot be argued into *nothing is wrong here*."""
    empty = tmp_path / "not-a-kb"
    empty.mkdir()

    assert main(["upgrade", "--kb", str(empty)]) == 1


def test_the_json_refusal_is_still_json(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """A caller promised machine-readable output and handed a traceback — or a bare line of prose —
    has been given the worst of both."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0", records="synth@0.9")

    code, raw = _run(root, "--json")
    payload = json.loads(raw)

    assert code == 3
    assert payload["outcome"] == Outcome.NO_BASELINE.value
    assert payload["hunks"] == [] and payload["diff"] == ""
    assert payload["remedy"]


@pytest.mark.parametrize("flags", [(), ("--json",)])
def test_the_report_never_diffs_the_user_against_the_template(
    tmp_path: Path, synthetic_template: Callable[..., str], flags: tuple[str, ...]
) -> None:
    """The property F4 exists for, asserted on both surfaces.

    **The invariant is the set of changed lines, not the whole output, and the difference is the
    finding.** A user's edit to a *rendered* variable (`provider`) renders identically into both
    sides, so it cannot appear as a `+` or `-` line — but it does appear in a hunk's **context**,
    because the context is what their template renders to. That is correct and worth pinning: the
    context lines are theirs, the changed lines are the template's. Asserting the outputs were
    byte-identical would have demanded the wrong property, and it is what this test did first.

    A user's edit to a *literal* (`final_k`) never enters either side, because neither side is
    their file — so it appears nowhere at all, context included.
    """
    name = _two_versions(synthetic_template)
    untouched = _stamp(tmp_path / "untouched", name, "1.0")
    edited = _stamp(tmp_path / "edited", name, "1.0")
    path = edited / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace('provider = "sentence-transformers"', 'provider = "fastembed"')
        .replace("final_k               = 8", "final_k               = 4"),
        encoding="utf-8",
    )

    def _changed(output: str) -> list[str]:
        """Only the `+`/`-` lines — read from the structure each surface actually has.

        In JSON the diff is one escaped string, so a line-oriented scan over it finds nothing and
        the whole assertion passes vacuously. That is the failure mode this helper exists to avoid,
        and it is why `hunks[].removed`/`added` are read instead of the `diff` field.
        """
        if "--json" in flags:
            payload = json.loads(output)
            return [
                line for hunk in payload["hunks"] for line in (*hunk["removed"], *hunk["added"])
            ]
        return [line[1:] for line in output.splitlines() if line[:1] in ("+", "-")]

    before, after = _run(untouched, *flags)[1], _run(edited, *flags)[1]
    assert _changed(before) == _changed(after)
    assert _changed(after), "a report with no changed lines would be invariant under anything"
    assert not any("fastembed" in line for line in _changed(after))
    assert "final_k" not in after
