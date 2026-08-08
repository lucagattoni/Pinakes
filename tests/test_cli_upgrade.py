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
    tight: bool = False,
    budget_note: str = "caps on the paid extractor.",
    max_tokens: str = "510",
    final_k: str = "8",
    adjacent_k: str | None = None,
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
    | `tight` | the blank line before `[budget]` | pure **deletion** of a line the file repeats |
    | `budget_note` | a **comment** inside `[budget]` | replacement moving no money |
    | `max_tokens` | one `[chunking]` value | replacement of a key the index was built under |
    | `final_k` | one `[retrieval]` value | replacement, neither money nor index-invalidating |
    | `adjacent_k` | a key `[retrieval]` did not have | pure addition **of a key**, not a comment |

    `tail_note` is the one that looks redundant beside `pdf_note` and is not: with nothing after
    the added lines, the hunk's *before* image (its context alone) is still present once the change
    has been applied, so both placement predicates match and their order decides the answer.

    **`budget_note` is T4's counterpart to it, and it defaults to *on*.** The shipped template's
    only `[budget]` drift (M3) rewrote three comment lines *as well as* two caps, so a `[budget]`
    hunk carrying comments is the ordinary case and not a corner. It defaults on so that every
    money test runs against that shape rather than against a bare `key = value` pair — and changing
    it *alone* produces the one hunk that is inside `[budget]`, applies cleanly, and moves nothing.

    **`adjacent_k` is a real manifest key, deliberately.** `--apply` re-parses what it wrote through
    `manifest.load`, and an unknown key is a hard error there, so a fixture inventing a key would
    exercise the rollback path while claiming to test the recommendation.
    """
    sources = ["[sources]", 'roots   = ["docs/"]', 'include = ["**/*.md", "**/*.txt"]']
    sources.append('exclude = ["**/drafts/**"]')
    if pdf_note:
        sources.append(PDF_NOTE)

    retrieval = [
        "[retrieval]",
        "candidates_per_source = 50",
        'fusion                = "rrf"',
        "fusion_top_k          = 20",
        f"final_k               = {final_k}",
        'rerank                = "local"',
        'vector_tier           = "auto"',
    ]
    if adjacent_k is not None:
        retrieval.append(f"adjacent_k            = {adjacent_k}")

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
        f"max_tokens = {max_tokens}",
        "overlap    = 64",
        "",
        "\n".join(retrieval),
        "",
        CONFIDENCE_BLOCK.replace("0.31", low_below),
        "",
        "[rerank]",
        'provider = "{{ rerank_provider }}"',
        'model    = "{{ rerank_model }}"',
        *([] if tight else [""]),
        "[budget]",
        f"# {budget_note}",
        "confirm_above_eur = 0.01",
        f"per_operation_eur = {per_operation}",
        "monthly_eur       = 5.00",
        'timezone          = "UTC"',
        'on_exceed         = "abort"',
    ]
    if tail_note:
        body.append("# Written by a later template version, at the very end of the file.")
    return "\n".join(body) + "\n"


def _stamp(
    root: Path,
    name: str,
    version: str,
    *,
    records: str | None = None,
    provider: str = "sentence-transformers",
) -> Path:
    """Write the KB that `pnk init` from *version* would have written.

    *provider* is the real backend name by default, because that is what a stamped KB carries and
    every test here reads only text. One test runs the **whole** `pnk doctor` report and must not:
    `sentence-transformers` would load model weights, and its `FutureWarning` is an error under
    this suite's `filterwarnings`. A provider no backend registers keeps that report offline and
    instant, and the check under test does not read it.

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
        "embedding_provider": provider,
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "embedding_dim": 384,
        "rerank_provider": provider,
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
    """Every `(placement, section, header)` the human listing carries, flattened to the first and
    last, in order."""
    found: list[tuple[str, str]] = []
    for line in output.splitlines():
        match = re.match(r"\s+(applies cleanly|already applied|conflicts)\s+(.*?)(@@ .*@@)$", line)
        if match:
            found.append((match.group(1), match.group(3)))
    return found


def _listed(output: str) -> list[tuple[str, str]]:
    """Every `(placement, section)` pair — what the listing *names*, not what the diff contains.

    `"[budget]" in out` is not that assertion: the diff body carries `[budget]` as a context line,
    so a listing that named no section at all would satisfy it. That is how `_section` came to be
    entirely untested while a test appeared to cover it.
    """
    found: list[tuple[str, str]] = []
    for line in output.splitlines():
        match = re.match(r"\s+(applies cleanly|already applied|conflicts)\s+(.*?)\s*@@ .*@@$", line)
        if match:
            found.append((match.group(1), match.group(2)))
    return found


def _tree(root: Path) -> dict[str, object]:
    """Every path under the KB — files **and** directories — with its bytes and its mtime.

    Three things are compared, because "writes nothing" is a claim about the whole directory and
    each of the three is blind to a different write:

    | Compared | Catches | Blind to |
    |---|---|---|
    | the path set | a file or directory created or removed | a rewrite in place |
    | the bytes | a file whose contents changed | **a rewrite of identical content** |
    | `st_mtime_ns` | a rewrite of identical content, and a directory a new entry touched | — |

    **The first version of this helper compared only the bytes of only the files, and its docstring
    had the reasoning inverted** — it said an mtime comparison passes for a rewrite of identical
    content, when the opposite is true. The plan's own named mutation (`plan()` opens the manifest
    for writing) survived it, as did `mkdir(".pinakes")`. Both die now.
    """
    return {
        str(path.relative_to(root)): (
            path.read_bytes() if path.is_file() else None,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
    }


def test_a_current_kb_prints_up_to_date_and_writes_nothing(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "2.0")
    before = _tree(root)

    code, out = _run(root)

    assert code == 0
    assert out.startswith("up to date: synth@2.0")  # docs/CLI.md publishes this line verbatim
    assert "@@" not in out, "there is no diff to print when the versions agree"
    # Not merely "no hunks": the whole diff scaffolding belongs to the drifted branch, and routing
    # an up-to-date KB through it prints two empty section headings and a bare "." beneath them.
    assert "what the template changed" not in out
    assert "how it fits" not in out
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
    # Recorded → installed, in that order. "both strings appear" is order-blind, and a reversed
    # headline tells the user their KB is on the newer of the two.
    assert "synth@1.0 → synth@2.0" in out


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
    # A conflict has four possible causes and this command cannot know which — the trailer says so
    # rather than telling the user they edited something.
    assert "A conflict is not a fault" in out
    assert "you have edited" not in out
    # The *listing* names the region, which `"[budget]" in out` does not assert: the diff body
    # carries that string as a context line whatever the listing says.
    assert ("conflicts", "[budget]") in _listed(out)
    assert ("applies cleanly", "[sources]") in _listed(out)


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


def test_an_already_applied_hunk_matching_twice_is_a_conflict_too(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Uniqueness binds **both** branches of the predicate, not just the clean one.

    Found by mutation testing rather than by reading: relaxing the *already applied* branch from
    "at exactly one position" to "somewhere" killed no test at all, while the same relaxation on
    the clean branch was caught immediately. The sibling below covered one half of the rule and
    read as though it covered the rule.

    The shape is a user who adopted the change **and** kept a second copy of the block. Two places
    the hunk could belong is not one, and the command does not pick.
    """
    name = _two_versions(synthetic_template, old=_source(), new=_source(low_below="0.35"))
    root = _stamp(tmp_path / "kb", name, "2.0", records="synth@1.0")
    path = root / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    adopted = CONFIDENCE_BLOCK.replace("0.31", "0.35")
    assert body.count(adopted) == 1, "the fixture is meant to start already applied, exactly once"
    path.write_text(body + "\n" + adopted + "\n", encoding="utf-8")

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
    # docs/CLI.md and docs/GUIDE.md both promise the report says so in as many words.
    assert "Nothing was written" in out
    # The summary counts read as nouns. Reusing the listing's verb phrase gives "2 applies cleanly".
    assert "2 clean" in out


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
    # Which side is which. Flattening `(*removed, *added)` — as the invariance test does, for its
    # own reasons — cannot see the two swapped, and a consumer that applied them would undo the
    # template's change instead of adopting it.
    budget = payload["hunks"][1]
    assert budget["removed"] == ["per_operation_eur = 0.05"]
    assert budget["added"] == ["per_operation_eur = 0.30"]
    # And the `diff` field is a diff, headers included — not a bag of lines `patch` cannot read.
    assert payload["diff"].startswith("@@")


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
    assert "what the template changed" not in out
    # The remedy is the whole value of this outcome: it says where the change *did* land.
    assert "README" in out and "golden set" in out
    # The human line rides on `detail`, so `Outcome.SAME_MANIFEST` -> `UP_TO_DATE` changes nothing
    # a reader sees and everything a JSON consumer sees. Only this assertion notices.
    assert json.loads(_run(root, "--json")[1])["outcome"] == Outcome.SAME_MANIFEST.value


def test_an_unarchived_recorded_version_refuses_with_a_remedy(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The remedy is the part a user acts on, and `cannot compare` alone does not prove one was
    printed. It must also promise nothing a release *cannot* keep: an unarchived version's
    content is gone, not pending."""
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0", records="synth@0.9")

    code, out = _run(root)

    assert code == 3
    assert "cannot compare" in out and "synth@0.9" in out
    assert "compare it by hand" in out.replace("\n", " ")
    assert "there will not be a later one" in out.replace("\n", " ")
    # The wrapper swaps the spaces inside a `code span` for a private-use codepoint so `textwrap`
    # cannot break the span, then swaps them back. Losing the restore leaks U+E000 into the one
    # message every KB in existence prints.
    assert "\ue000" not in out
    # On the **raw** output, because `.replace("\n", " ")` undoes exactly the damage the wrapper
    # exists to prevent. This holds today because the remedy's spans happen not to straddle the
    # wrap column; `::test_a_code_span_is_never_broken_across_two_lines` is what pins the
    # mechanism, since a reworded remedy could make this assertion true either way.
    assert "`pnk init` on a throwaway directory" in out
    # "stamped from X **or later**" must name the **oldest** archived version. Naming the newest
    # reads as a promise excluding every version between: true while one version is archived, and
    # user-facing nonsense from the next bump onward. This fixture archives two.
    assert "A KB stamped from synth@1.0 or later" in out.replace("\n", " ")


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
    assert out.startswith(
        "cannot compare:"
    )  # ...including on the shipped template, the path every real KB takes


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
    assert out.startswith("cannot compare:")  # docs/CLI.md publishes this opening for every cause


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
    # `docs/CLI.md` promises every `3` opens with this, so one match finds the whole class. It is a
    # published contract, and it was a bare sentence outside that family until the review.
    assert out.startswith("cannot compare:")


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
    assert out.startswith("cannot compare:")  # ...and on the one cause that arrives as an exception


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


# --- What the adversarial review found missing, each with the mutant it kills -------------------


def test_a_removed_line_the_manifest_repeats_does_not_block_already_applied(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The *already applied* test asks about the hunk's **before image**, not about its removed
    lines on their own — and the difference is a misclassification, not a nicety.

    `tight` deletes the blank line before `[budget]`. A blank line occurs a dozen times in any
    manifest, so "do the removed lines appear anywhere in the file" is always *yes* and the user
    who adopted this change by hand was told **conflicts** — under a later `--apply`'s
    all-or-nothing rule, that refuses the whole run for them. The same holds for a hunk removing a
    bare `#`, which a comment-dense template also repeats.

    Found by review, not by mutation: nothing was wrong with the *code path*, only with which
    question it asked.
    """
    name = _two_versions(synthetic_template, old=_source(), new=_source(tight=True))
    root = _stamp(tmp_path / "kb", name, "2.0", records="synth@1.0")

    code, out = _run(root)

    assert code == 0
    assert [placement for placement, _ in _placements(out)] == ["already applied"]


def test_a_deletion_not_yet_applied_is_clean_not_already_applied(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The control for the test above, and the reason the second half of the predicate exists.

    Deleting that half entirely makes *this* KB — which still has the line the template dropped —
    report `already applied`, and a later `--apply` would skip a change the user has not got.

    **The deletion has to be at the end of the file, and the first version of this test missed
    that.** With trailing context (the `tight` variant), removing a line breaks the *after* image's
    contiguity in `theirs` on its own, so the first half of the predicate already answers and the
    second is never consulted — the test passed under the mutant. At the end of the file there is
    no trailing context: the after image is the leading context alone, which is still present, so
    only the before-image half can tell "not yet applied" from "already applied".
    """
    name = _two_versions(synthetic_template, old=_source(tail_note=True), new=_source())
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out = _run(root)

    assert code == 0
    assert [placement for placement, _ in _placements(out)] == ["applies cleanly"]


def test_the_printed_diff_is_a_real_unified_diff(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Every `@@ -a,b +c,d @@` header, against `difflib`'s own.

    `hunks()` re-implements unified-diff range formatting by hand (a one-line range prints bare, an
    empty range points at the line before the gap). **No test asserted a single one of those
    numbers**: three independent mutants of `_range` survived the first mutation run, and the diff
    is the part of this command a user may paste into `patch`.

    Asserted against the library rather than against literals, so it cannot drift with the fixture.
    """
    import difflib

    from pinakes.upgrade import hunks

    for old, new in (
        (_source(), _source(pdf_note=True, per_operation="0.30")),
        (_source(), _source(tight=True)),
        (_source(), _source(tail_note=True)),
        (_source(tail_note=True), _source()),
        ("only one line\n", "only one other line\n"),
        ("a\nb\nc\n", "x\na\nb\nc\n"),
        ("a\nb\nc\n", ""),
    ):
        mine = "\n".join(
            line for hunk in hunks(old, new, "") for line in (hunk.header, *hunk.lines)
        )
        theirs = "\n".join(
            difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=3)
        )
        # `unified_diff`'s first two lines are the `---`/`+++` file headers, which this command has
        # no filenames to fill in and deliberately does not print.
        assert mine == "\n".join(theirs.splitlines()[2:]), f"{old!r} -> {new!r}"


def test_the_listing_names_the_table_each_hunk_falls_in(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`_section` was entirely untested — returning `None` for everything, reading `ours` instead of
    `base`, and dropping the column from the listing all survived — because the assertion that
    looked like it covered this was `"[budget]" in out`, satisfied by the diff's own context line.
    """
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out = _run(root)

    assert code == 0
    assert _listed(out) == [("applies cleanly", "[sources]"), ("applies cleanly", "[budget]")]


def test_which_line_counts_as_the_table_a_hunk_falls_in() -> None:
    """`_section` as a unit, because the end-to-end fixture could not fail.

    The first version of this test wrapped `include` over three lines and asserted the section was
    `[sources]` — but a wrapped array of *strings* has continuation lines opening with `"`, so the
    loose pattern it was written to reject returned `[sources]` too. It passed under both. The
    shape that discriminates is an array element that is itself an array.

    The two rows after it are the other half, and they are why tightening a pattern needs its own
    test: `[[links.kb]]` is a table any linked KB has, and `[budget]  # caps` is legal TOML. A
    pattern tight enough to reject an array element and no tighter labels a hunk in either of those
    with the *preceding* table, which is wrong without looking wrong.
    """
    from pinakes.upgrade import hunks

    def section_of(base: str, ours: str) -> list[str | None]:
        return [hunk.section for hunk in hunks(base, ours, "")]

    nested = '[sources]\nmatrix = [\n  ["p", "q"],\n  ["r", "s"],\n]\ntail = 1\nmore = 2\n'
    assert section_of(nested, nested.replace('["r", "s"],', '["r", "t"],')) == ["[sources]"]

    for header in ("[[links.kb]]", "[budget]  # caps on the one thing that can spend", "  [a.b]"):
        body = f"[first]\nx = 1\ny = 2\nz = 3\n{header}\nkey = 4\nlast = 5\n"
        assert section_of(body, body.replace("key = 4", "key = 9")) == [header.strip()], header

    # The **last** element of a wrapped array closes without a trailing comma, so its shape is a
    # bracketed thing on a line of its own — indistinguishable from a header by brackets alone. The
    # comma inside is what separates them.
    #
    # **The comma-less element has to be in `base`, and the change below it.** `_section` reads
    # `base` and never `ours`, so a fixture that puts the interesting line on the other side tests
    # nothing — the first version of this assertion did exactly that, which is the same defect the
    # retro records for the test before it.
    closing = '[sources]\nmatrix = [\n  ["p", "q"],\n  ["r", "s"]\n]\ntail = 1\nmore = 2\n'
    assert section_of(closing, closing.replace("tail = 1", "tail = 9")) == ["[sources]"]

    # A key whose *value* opens a bracket is not a header either, and neither is an element that
    # only looks like one — both need the end-of-line anchor as well as the comma rule.
    anchored = "[t]\nq = [\n  1,\n  2\n]\n[budget] = 1\nr = 3\ns = 4\n"
    assert section_of(anchored, anchored.replace("r = 3", "r = 9")) == ["[t]"]

    # And with no table above the first changed line at all, there is no section to name — even
    # when a table exists further down. Naming *that* one would attribute a change to a table it
    # sits above.
    headless = "x = 0\ny = 0\nz = 0\nw = 0\n"
    assert section_of(headless, headless.replace("x = 0", "x = 1")) == [None]
    later = "x = 0\ny = 0\nz = 0\n[t]\np = 0\n"
    assert section_of(later, later.replace("x = 0", "x = 1")) == [None]

    # And when the *same hunk* also changes a line that does sit under a table, the answer is still
    # the first changed line's — the search stops there rather than walking on to whichever table
    # some later change happens to fall in. Both changes must be inside one hunk for this to
    # discriminate, which three lines of context between them guarantees.
    two = later.replace("x = 0", "x = 1").replace("p = 0", "p = 1")
    assert section_of(later, two) == [None]

    # An insertion changes nothing in `base`, so the scan starts one line earlier: text landing
    # *before* a table header belongs to the table above it, not to the one it is about to open.
    spaced = "[first]\na = 1\nb = 2\nc = 3\n[second]\nd = 4\ne = 5\nf = 6\n"
    assert section_of(spaced, spaced.replace("[second]", "new = 0\n[second]")) == ["[first]"]

    # A hunk that **renames** a table header is inside that table, not the one above it — the same
    # offset the insert case moves back by, which must not move back here.
    assert section_of(spaced, spaced.replace("[second]", "[segundo]")) == ["[second]"]


def test_doctor_and_upgrade_say_the_same_thing_about_an_unarchived_version(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """One fact, one wording. The two surfaces carried byte-identical copies of this message for one
    increment with nothing to notice if either were reworded — which is the *"two surfaces
    disagreeing about one KB"* defect the module's own docstring says it exists to prevent."""
    from pinakes.doctor import diagnose
    from pinakes.manifest import load
    from pinakes.upgrade import plan

    # The provider is deliberately one nothing registers. `diagnose()` runs every check, and with
    # the real `sentence-transformers` name it loads model weights on any checkout carrying
    # `pinakes[st]` — three seconds, and a `FutureWarning` that this suite's `filterwarnings =
    # ["error"]` turns into a failure. CI never installs `[st]`, so it would have been green there
    # and red on a contributor's machine.
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0", records="synth@0.9", provider="no-such-backend")

    report = plan(load(root))
    check = next(c for c in diagnose(load(root)).checks if c.name == "template")

    assert report.detail == check.detail
    assert report.remedy == check.remedy
    assert "cannot compare" in check.detail


def test_the_json_payload_is_a_wire_contract_written_out_in_full(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Every key and every string value, as literals — **not** derived from the enums that produce
    them.

    Three earlier assertions compared `payload["outcome"]` against `Outcome.X.value` and the
    listing labels against `Placement(...).value`. Those are self-referential: renaming both sides
    together keeps them green, and a consumer's parser breaks. Eight mutants lived in that gap —
    every outcome and placement string renameable, `recorded`/`installed` swappable, `section` and
    `template` droppable to `None`, `detail` blankable, and two of the three `counts` keys
    removable.

    Written out here once, for one drifted report, so a rename is a visible diff in a test rather
    than a silent break in somebody's script.
    """
    name = _two_versions(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    payload = json.loads(_run(root, "--json")[1])

    assert set(payload) == {
        "outcome",
        "detail",
        "remedy",
        "template",
        "recorded",
        "installed",
        "diff",
        "hunks",
        "counts",
        # T4's three. `spend` is on **every** payload, `--apply` or not: a consumer must be able to
        # ask *would this move money* without parsing a heading out of prose, and a key that
        # appears only sometimes is one every consumer has to guard.
        "spend",
        "applied",
        "refused",
    }
    assert payload["applied"] is None and payload["refused"] is None, (
        "a report that was not asked to write has nothing to say about writing"
    )
    assert payload["spend"] == [
        {"key": "budget.per_operation_eur", "before": "0.05", "after": "0.30"}
    ]
    assert payload["outcome"] == "drifted"
    assert payload["template"] == "synth"
    assert payload["recorded"] == "synth@1.0"
    assert payload["installed"] == "synth@2.0"
    assert payload["detail"] == "synth@1.0 → synth@2.0"
    assert payload["remedy"] is None
    assert payload["counts"] == {"clean": 2, "already-applied": 0, "conflict": 0}
    assert [hunk["section"] for hunk in payload["hunks"]] == ["[sources]", "[budget]"]
    assert [hunk["placement"] for hunk in payload["hunks"]] == ["clean", "clean"]
    assert set(payload["hunks"][0]) == {"header", "section", "placement", "removed", "added"}

    refusal = json.loads(
        _run(_stamp(tmp_path / "old", name, "1.0", records="synth@0.9"), "--json")[1]
    )
    assert refusal["outcome"] == "no-baseline"
    assert refusal["hunks"] == [] and refusal["diff"] == ""
    assert refusal["counts"] == {"clean": 0, "already-applied": 0, "conflict": 0}


def test_the_help_line_says_the_command_writes_nothing_without_apply() -> None:
    """The one-line help is where most users meet this command's contract, and T4 changed it.

    Rewording it to *"Apply what your template changed"* left the whole suite green — a promise
    reversed in the place it is most read, with nothing to notice. **T4 makes the promise
    conditional rather than dropping it**, and the qualifier is the load-bearing half: a help line
    still reading *writes nothing*, flat, is now false for the flag printed directly beneath it.
    """
    import contextlib
    import io

    from pinakes.cli import build_parser

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.suppress(SystemExit):
        build_parser().parse_args(["--help"])
    assert "writes nothing without --apply" in captured.getvalue()


def test_no_line_of_the_report_runs_past_the_wrap(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The remedy is wrapped for a terminal, and dropping `textwrap.fill` entirely left the suite
    green. A diff line may be any length — it is content, and wrapping one would corrupt it — so
    the bound is asserted over the prose the command writes itself."""
    from pinakes.upgrade import WRAP

    name = _two_versions(synthetic_template)
    refusal = _run(_stamp(tmp_path / "kb", name, "1.0", records="synth@0.9"))[1]

    assert refusal.splitlines()
    assert max(len(line) for line in refusal.splitlines()) <= WRAP


def test_a_code_span_is_never_broken_across_two_lines() -> None:
    """`_fill` as a unit, at the width where the break actually happens.

    Asserting this through a real report does not work and the reason is worth stating: whether a
    span straddles the wrap column depends on every word before it, so the assertion is green under
    a broken wrapper whenever the current remedy's wording happens to be kind. The property is
    about the wrapper, so it is tested against the wrapper — with an input built so that plain
    `textwrap` provably splits the span, which the second assertion checks rather than assumes.
    """
    import textwrap

    from pinakes.upgrade import WRAP, fill

    text = "x" * (WRAP - 6) + " `pnk sync --rebuild` finishes the job"

    assert "`pnk sync --rebuild`" in fill(text)
    assert "`pnk sync --rebuild`" not in textwrap.fill(text, width=WRAP, break_long_words=False), (
        "the fixture must be one plain textwrap actually breaks, or this test proves nothing"
    )
    assert "\ue000" not in fill(text)

    # A span **longer than the wrap column** is the case `break_long_words=False` exists for:
    # glued into one unbreakable token, the default would cut it in half rather than let the
    # line run over. A command a reader is meant to copy is worth an over-long line.
    long_span = "`pnk sync " + "--force " * 20 + "--rebuild`"
    assert long_span in fill(f"before it {long_span} after it")


def test_a_report_with_no_conflict_does_not_explain_conflicts(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The trailer that says a conflict is not a fault is printed **only** when there is one.

    Its guard was unpinned, and an explanation attached to a report that has nothing to explain is
    how a reader learns to skip the paragraph that will one day matter — the same argument T4's
    plan makes for the `[budget]` heading it must print exactly when money moves.
    """
    name = _two_versions(synthetic_template)

    clean = _run(_stamp(tmp_path / "clean", name, "1.0"))[1]
    assert "applies cleanly" in clean
    assert "A conflict is not a fault" not in clean
    # ...and the summary names only the outcomes that occurred.
    assert "0 conflicting" not in clean and "0 already applied" not in clean


# --- T4: `--apply` ------------------------------------------------------------------------------
#
# **Every positive path here runs against a synthetic template, for the reason in this module's
# docstring**, and every one of them writes: these are the only tests in the suite that let a
# command touch a `pinakes.toml`. The shipped `notes` reaches exactly one of them — the
# cannot-compare refusal — and that one is here deliberately, because it is what 100% of real KBs
# get today.


def _run2(root: Path, *flags: str) -> tuple[int, str, str]:
    """`_run`, plus stderr — which is where a refusal's message goes.

    A refusal is a `PinakesError` caught in `cli.main`, so a test that captured only stdout would
    assert the *report* printed before the write and call that the refusal message. The two are
    different strings and only one of them names which guard fired.
    """
    import io
    from contextlib import redirect_stderr, redirect_stdout

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["upgrade", "--kb", str(root), *flags])
    return code, out.getvalue(), err.getvalue()


def _backup(root: Path) -> Path:
    return root / "pinakes.toml.orig"


def _manifest(root: Path) -> Path:
    return root / "pinakes.toml"


def _spend_pair(synthetic_template: Callable[..., str]) -> str:
    """The default drift, whose `[budget]` hunk moves exactly one cap: `0.05 → 0.30`."""
    return _two_versions(synthetic_template)


def test_apply_writes_only_the_cleanly_applying_hunks(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The rule in the one shape that can tell it from *apply everything*: a KB that already has
    one of the two changes.

    A writer with no notion of *already applied* re-inserts the comment block the user adopted by
    hand, and the manifest ends up carrying it twice. Asserting the count — not merely presence —
    is what makes that visible; `PDF_NOTE in text` is true either way.
    """
    name = synthetic_template(
        "synth",
        versions={
            "1.0": _source(),
            "1.5": _source(pdf_note=True),
            "2.0": _source(pdf_note=True, per_operation="0.30"),
        },
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.5", records="synth@1.0")

    code, out, err = _run2(root, "--apply")
    text = _manifest(root).read_text(encoding="utf-8")

    assert code == 0, err
    assert "1 applied, 1 already applied and skipped." in out
    assert text.count("to `include` above to index PDFs") == 1, "the skipped hunk was re-applied"
    assert "per_operation_eur = 0.30" in text
    assert '\ntemplate = "synth@2.0"' in text


def test_apply_refuses_entirely_when_any_hunk_conflicts(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """All-or-nothing, asserted on all three of the things that make it all-or-nothing.

    The `.orig` assertion is not tidiness: a backup left by a refused run makes the **next** run
    refuse on the `.orig` rule instead of on the conflict, which is a non-zero exit delivered by
    the wrong guard, and the user never learns why the first one stopped.

    The clean `[budget]` hunk in this fixture is what the byte-identity assertion is really about.
    D-10 B has no exception and the conflict rule is all-or-nothing, so the correct outcome is that
    the cap does **not** move either.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    edited = (
        _manifest(root)
        .read_text(encoding="utf-8")
        .replace('exclude = ["**/drafts/**"]', 'exclude = ["**/drafts/**"]  # mine')
    )
    _manifest(root).write_text(edited, encoding="utf-8")
    before = _manifest(root).read_bytes()

    code, _out, err = _run2(root, "--apply")

    assert code == 1
    assert _manifest(root).read_bytes() == before
    assert "per_operation_eur = 0.05" in before.decode("utf-8")
    assert not _backup(root).exists()
    # The region, named **on the same line as the word**. Two greps that each pass on a different
    # line of a diff that prints `[sources]` anyway establish nothing.
    naming = [line for line in err.splitlines() if "conflict" in line.lower()]
    assert naming and any("[sources]" in line for line in naming), err


def test_apply_leaves_an_orig_and_refuses_to_overwrite_an_existing_one(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """D-5 A, and the half that matters: the backup holds the state **before** the write.

    A backup written after the change would satisfy "a file exists" and be worthless — it is the
    only way a user who did not want a raised cap gets the old numbers back without an editor and
    a memory, which is exactly what D-10 makes it responsible for.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    original = _manifest(root).read_bytes()

    assert _run2(root, "--apply")[0] == 0
    assert _backup(root).read_bytes() == original
    assert "per_operation_eur = 0.05" in _backup(root).read_text(encoding="utf-8")
    assert "per_operation_eur = 0.30" in _manifest(root).read_text(encoding="utf-8")

    # A second KB, drifted, with a `.orig` already beside it. Never a re-run of the first: that KB
    # now records the installed version, so it is *up to date* and never reaches the guard at all.
    second = _stamp(tmp_path / "kb2", name, "1.0")
    _backup(second).write_text("something the user is keeping\n", encoding="utf-8")
    untouched = _manifest(second).read_bytes()

    code, _out, err = _run2(second, "--apply")

    assert code == 1
    assert "pinakes.toml.orig" in err
    assert _backup(second).read_text(encoding="utf-8") == "something the user is keeping\n"
    assert _manifest(second).read_bytes() == untouched


def test_apply_prints_that_the_orig_is_untracked(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`init` writes a `.gitignore` covering `.pinakes/` only, so in a KB under git the backup shows
    up in `git status` and can be committed by accident. The printed line is the whole mitigation —
    a `.gitignore` line added at `init` time would help no KB that already exists."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    out = _run2(root, "--apply")[1]

    assert "pinakes.toml.orig" in out
    assert "git status" in out and "nothing ignores it" in out


def test_apply_refuses_while_the_sync_lock_is_held(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Read the lock, never claim it — and the assertion that the check left no trace is the point.

    Claiming it would write a file under `.pinakes/`, which contradicts this command's own
    never-touches-`.pinakes/` rule. So the check is `read_holder`, it is advisory and racy, and
    what it converts is the common case: a sync running right now goes from silent corruption to a
    message naming who holds it.
    """
    import json as json_module

    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    state = root / ".pinakes"
    state.mkdir()
    (state / "sync.lock").write_text(
        json_module.dumps({"pid": 4242, "host": "somewhere", "started": "20260808 04:00"}),
        encoding="utf-8",
    )
    before_state = _tree(state)
    before_manifest = _manifest(root).read_bytes()

    code, _out, err = _run2(root, "--apply")

    assert code == 1
    assert "4242" in err and "somewhere" in err
    assert _manifest(root).read_bytes() == before_manifest
    assert not _backup(root).exists()
    assert _tree(state) == before_state, "reading the lock must leave `.pinakes/` untouched"


def test_a_write_that_produces_an_unloadable_manifest_is_rolled_back(
    tmp_path: Path, synthetic_template: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-parse guard, driven at `apply` rather than through the CLI — deliberately.

    `cli.run_upgrade` calls `manifest.discover`, which calls `manifest.load`; monkeypatching `load`
    before the command runs would make it fail on the *read*, and the test would pass while the
    rollback it names never executed. So the report is built first, with the real loader, and only
    the loader `apply` reaches afterwards is replaced.
    """
    from pinakes import manifest as manifest_module
    from pinakes import upgrade
    from pinakes.errors import ManifestError, UpgradeError

    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    loaded = manifest_module.load(root)
    report = upgrade.plan(loaded)
    original = _manifest(root).read_bytes()

    def refuse(root_: Path) -> object:
        raise ManifestError(root_ / "pinakes.toml", table=None, message="invented, for this path")

    monkeypatch.setattr(manifest_module, "load", refuse)

    with pytest.raises(UpgradeError) as raised:
        upgrade.apply(loaded, report)

    assert _manifest(root).read_bytes() == original, "the bad write survived the rollback"
    assert not _backup(root).exists(), "a rollback that leaves a backup blocks the next run"
    assert "would not load" in raised.value.message


def test_the_template_key_is_rewritten_only_inside_the_kb_table() -> None:
    """`_restamp` as a unit, because the corrupting case is **unreachable through the product**.

    A whole-file `^template =` substitution corrupts a `template = …` line in a later table — and no
    manifest can carry one, since an unknown key is a hard error in `manifest.load`. So the fixture
    is fed to the function directly rather than through a KB that could not exist. That is the
    honest form of this test; driving it end to end would silently assert nothing.

    The second half is reachable and is asserted beside it: a **commented** `template =` line
    inside `[kb]` must not be counted as the key, or an ordinary annotated manifest is refused for
    occurring twice.
    """
    from pinakes.upgrade import restamp

    content = [
        "[kb]",
        '# template = "synth@0.1"  # what it used to be',
        'template = "synth@1.0"  # stamped at init',
        "",
        "[elsewhere]",
        'template = "not this one"',
    ]

    out = restamp(content, "synth@2.0")

    assert out[2] == 'template = "synth@2.0"  # stamped at init', "alignment or comment destroyed"
    assert out[1] == content[1], "a commented-out line was rewritten"
    assert out[5] == content[5], "a `template =` line in a later table was rewritten"


def test_restamp_refuses_rather_than_appending_a_key_it_cannot_find() -> None:
    """Guessing where a key belongs in a file the user owns is the thing this command exists not to
    do, so an absent or duplicated `[kb] template` is a refusal and never an append."""
    from pinakes.errors import UpgradeError
    from pinakes.upgrade import restamp

    with pytest.raises(UpgradeError, match="occurs 0 times"):
        restamp(["[kb]", 'name = "x"', "", "[sources]"], "synth@2.0")

    with pytest.raises(UpgradeError, match="not a quoted value"):
        restamp(["[kb]", "template = 3", "", "[sources]"], "synth@2.0")


# --- D-10's consent path: four tests that only work as a set ------------------------------------
#
# Each of the first three is satisfiable by something other than the property it names unless the
# negative controls are there too. A heading printed unconditionally passes every positive
# assertion anyone can write about it — which is this project's recurring defect shape, with money
# attached.


def _index(out: str, needle: str) -> int:
    for number, line in enumerate(out.splitlines()):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} is in no line of the output — the assertion would be void")


def test_a_budget_hunk_is_applied_like_any_other_hunk(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """D-10 B, stated as an assertion: the cap **moves**.

    The applier has no `[budget]` predicate, no exclusion and no second flag, and this is the test
    that fails if a later reader adds one. Assert the **value**, never the key's presence:
    `per_operation_eur` is in every manifest ever written.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    assert _run2(root, "--apply")[0] == 0
    assert "per_operation_eur = 0.30" in _manifest(root).read_text(encoding="utf-8")


@pytest.mark.parametrize("flags", [(), ("--apply",)])
def test_a_budget_change_is_printed_with_both_values(
    tmp_path: Path, synthetic_template: Callable[..., str], flags: tuple[str, ...]
) -> None:
    """Both values, under a heading that names spending — in **both** commands.

    The report is where a user decides, so it must not be the weaker of the two outputs; the
    parametrisation is the whole assertion, not a convenience.

    **What the old value rules out, and what it does not.** It rules out an implementation that
    printed only the resulting state, only the new value, or a bare list of changed keys. It does
    **not** rule out writing before printing — the diff carries the old value whenever it is
    printed at all — and claiming otherwise would be this project's recurring defect committed
    inside the test meant to prevent it. Ordering is the next test's job.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    out = _run2(root, *flags)[1]
    heading = out.splitlines()[_index(out, "spending cap")]
    under = out[out.index(heading) + len(heading) :]

    assert "spending cap" in heading
    # Under the heading, not merely somewhere in the output: the diff body carries both numbers on
    # its own `-`/`+` lines, so an output-wide assertion is satisfied by a heading with nothing
    # beneath it at all.
    assert "per_operation_eur: 0.05 → 0.30" in under


def test_the_budget_heading_precedes_the_first_write(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Ordering by line position, not membership.

    "Both strings appear" is equally true of an implementation that writes first and explains
    afterwards. The write anchor is the `.orig` path and **not** a word like *applied*: that word
    also names the *already applied* outcome further up, so anchoring on it compares against
    whichever line happened to use it first.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    out = _run2(root, "--apply")[1]

    assert _index(out, "spending cap") < _index(out, "pinakes.toml.orig")


def test_no_budget_heading_when_no_hunk_touches_budget(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """**The one that makes the other three mean anything.**

    Without it, a heading printed unconditionally passes every positive assertion above. The
    negative is asserted on `spending cap` and never on the word `budget`: the diff prints
    `[budget]` as a table header whatever else happens, so a negative on that fails for a reason
    with nothing to do with the heading.
    """
    name = synthetic_template(
        "synth",
        versions={"1.0": _source(), "2.0": _source(final_k="4")},
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert "final_k               = 4" in _manifest(root).read_text(encoding="utf-8")
    assert "spending cap" not in out


def test_no_budget_heading_when_the_budget_hunk_is_already_applied(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """No money moves, because the KB already carries the value. A heading here announces a change
    that is not happening — and a user trained to skip it skips the one that matters."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "2.0", records="synth@1.0")

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert "already applied" in out
    assert "spending cap" not in out


def test_no_budget_heading_when_the_run_refuses_on_a_conflict(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The `[budget]` hunk here applies cleanly and is still not written: the rule is
    all-or-nothing. Nothing moves, so nothing is announced — in the report **and** under
    `--apply`, since the predicate is one predicate."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    _manifest(root).write_text(
        _manifest(root)
        .read_text(encoding="utf-8")
        .replace('exclude = ["**/drafts/**"]', 'exclude = ["**/drafts/**"]  # mine'),
        encoding="utf-8",
    )

    assert "spending cap" not in _run2(root)[1]
    assert "spending cap" not in _run2(root, "--apply")[1]


def test_no_budget_heading_when_the_budget_hunk_changes_only_comments(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The fourth near-miss, which the plan's positional predicate does not exclude.

    The shipped template's own `[budget]` drift (M3) rewrote three comment lines beside the two
    caps, so a hunk *inside* `[budget]` that moves no key is the ordinary case rather than a
    corner. Under a purely positional rule it prints a spending-cap heading with nothing under it.
    """
    name = synthetic_template(
        "synth",
        versions={
            "1.0": _source(budget_note="caps on the paid extractor."),
            "2.0": _source(budget_note="caps on the one thing that can spend."),
        },
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert _listed(out) == [("applies cleanly", "[budget]")], "the fixture must place in [budget]"
    assert "one thing that can spend" in _manifest(root).read_text(encoding="utf-8")
    assert "spending cap" not in out


# --- D-11: the recommendation, and the operands that are easy to get wrong ----------------------


def test_requires_pinakes_is_never_written(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """D-11 A in its strongest form: run `--apply` over a bump that **does** add a key, and assert
    the key is absent from the **file**. Absence from the diff would not be it — a write that
    appended `requires_pinakes` outside every hunk is exactly what this forbids."""
    name = synthetic_template(
        "synth",
        versions={"1.0": _source(), "2.0": _source(adjacent_k="2")},
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, _out, err = _run2(root, "--apply")

    assert code == 0, err
    assert "requires_pinakes" not in _manifest(root).read_text(encoding="utf-8")


def test_a_key_adding_hunk_prints_a_requires_pinakes_recommendation(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The positive half. Assert the printed line **names the added key**, not merely that the
    string `requires_pinakes` appears: that word is in `docs/MANIFEST.md`, in `--help` and
    plausibly in the diff, so its presence alone discriminates nothing."""
    name = synthetic_template(
        "synth",
        versions={"1.0": _source(), "2.0": _source(adjacent_k="2")},
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.0")

    out = _run2(root, "--apply")[1]

    assert "retrieval.adjacent_k" in out
    assert "requires_pinakes" in out
    # No number is suggested and none is written: nothing in the repository maps a manifest key to
    # the release that introduced it (D-11 option C), so a printed floor would be a guess.
    assert ">=" not in out.split("requires_pinakes")[1]


def test_no_recommendation_when_no_applied_hunk_adds_a_key(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The negative control, and **today it is the only case a real template can reach**: no
    template change has ever added a key (F2)."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    assert "requires_pinakes" not in _run2(root, "--apply")[1]


def test_a_key_carried_only_by_a_skipped_hunk_is_not_recommended(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The operand test — `parse(base + applied)` minus `parse(base)`, never `parse(ours)` minus
    `parse(base)`. The natural wrong implementation passes both tests above and fails only this one.

    **Renamed from the plan's `…_by_a_conflicting_hunk_…`, because that form cannot discriminate.**
    Under the all-or-nothing rule a conflicting run refuses and prints no recommendation at all, so
    both operand choices produce the same observable: nothing. The case that actually separates
    them is an **already applied** hunk — skipped, its key already in the file, and therefore not
    something this run introduced.
    """
    name = synthetic_template(
        "synth",
        versions={
            "1.0": _source(),
            "1.5": _source(adjacent_k="2"),
            "2.0": _source(adjacent_k="2", per_operation="0.30"),
        },
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.5", records="synth@1.0")

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert "already applied and skipped" in out, "the fixture must produce a skipped hunk"
    assert "adjacent_k" not in out.split("applied")[-1]
    assert "requires_pinakes" not in out


def test_an_existing_requires_pinakes_is_left_byte_identical(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """It is a key the user owns and `--apply` has no opinion about it — not raised, not lowered,
    not reformatted.

    **Only the lower-floor direction is reachable, and the higher one needs no test.** A floor above
    the running build makes the manifest unreadable to it, so `pnk upgrade` fails at `discover`
    before `--apply` exists as a question. That is a stronger guarantee than being left alone, and
    it is `manifest.py`'s to hold, not this command's.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    line = 'requires_pinakes = ">=0.6.0"   # mine, do not touch'
    _manifest(root).write_text(
        _manifest(root)
        .read_text(encoding="utf-8")
        .replace('created  = "20260725 09:14"', f'created  = "20260725 09:14"\n{line}'),
        encoding="utf-8",
    )

    code, _out, err = _run2(root, "--apply")

    assert code == 0, err
    assert line in _manifest(root).read_text(encoding="utf-8")


# --- What `--apply` must leave alone, and the endings it must preserve ---------------------------


def test_apply_names_the_rebuild_when_an_applied_hunk_changes_an_index_invalidating_key(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Refusing to sync without saying so leaves the user holding exactly the state they cannot
    search — `::test_apply_does_not_run_a_sync` would otherwise pin that as correct. The pair is
    the point; neither test is honest on its own."""
    name = synthetic_template(
        "synth",
        versions={"1.0": _source(), "2.0": _source(max_tokens="480")},
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert "chunking.max_tokens" in out
    assert "pnk sync --rebuild" in out


def test_apply_writes_nothing_under_docs_or_pinakes_state(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`docs/` belongs to the user and `.pinakes/` is disposable by invariant. `--apply` writes the
    manifest and its backup, and a snapshot of both trees is what says so — `_tree` compares the
    path set, the bytes **and** the mtimes, because each is blind to a different write."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    (root / "docs" / "note.md").write_text("mine\n", encoding="utf-8")
    (root / ".pinakes").mkdir()
    (root / ".pinakes" / "keep.json").write_text("{}\n", encoding="utf-8")
    docs_before, state_before = _tree(root / "docs"), _tree(root / ".pinakes")

    assert _run2(root, "--apply")[0] == 0

    assert _tree(root / "docs") == docs_before
    assert _tree(root / ".pinakes") == state_before


def test_apply_does_not_run_a_sync(tmp_path: Path, synthetic_template: Callable[..., str]) -> None:
    """A changed `include` means new documents exist to index, and that is `pnk sync`'s job. This
    test is only honest alongside the rebuild-naming test above; on its own it pins the state a
    user cannot search."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    assert _run2(root, "--apply")[0] == 0

    assert not (root / ".pinakes" / "index.db").exists()
    assert sorted(path.name for path in root.iterdir()) == [
        "docs",
        "pinakes.toml",
        "pinakes.toml.orig",
    ]


def test_the_comment_the_template_added_is_present_after_apply(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The end-to-end case, and the one that proves the mechanism addresses the drift that exists.

    Asserted by **content** and never by a line count. A key-level implementation — one that
    reconciled `key = value` pairs instead of applying text — fails it, which is the point: F2
    measured that no template change has ever added or removed a key, so the entire drift history
    of the shipped template is comments and two values.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    assert _run2(root, "--apply")[0] == 0

    assert "to `include` above to index PDFs" in _manifest(root).read_text(encoding="utf-8")


def test_a_crlf_manifest_keeps_its_line_endings(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`Path.read_text` opens in universal-newline mode, so a CRLF manifest is already `\\n`-only by
    the time the placement predicate sees it — correct for a *report*, and silently wrong for a
    write, which would put LF lines into a CRLF file and leave the endings mixed.

    Asserted on the whole file rather than on the changed lines: a writer that preserved the
    convention only where it spliced would pass a narrower check and still produce a mixture.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    original = _manifest(root).read_bytes().replace(b"\n", b"\r\n")
    _manifest(root).write_bytes(original)

    code, _out, err = _run2(root, "--apply")
    written = _manifest(root).read_bytes()

    assert code == 0, err
    assert written.count(b"\r\n") == written.count(b"\n"), "an LF line was written into a CRLF file"
    assert b"per_operation_eur = 0.30" in written
    assert b"to `include` above to index PDFs" in written
    assert _backup(root).read_bytes() == original, "the backup must be the bytes that were there"


def test_a_manifest_with_mixed_line_endings_is_refused(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Refuse rather than repair, which is the fork this open correction left to T4.

    A mixed-ending manifest is already the product of two tools disagreeing, and picking one for
    the user silently rewrites lines they did not ask to be touched — in the one file every other
    rule in Pinakes exists not to touch. The **report** still works, because reporting reads.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    mixed = _manifest(root).read_text(encoding="utf-8").replace("[budget]", "[budget]\r", 1)
    _manifest(root).write_text(mixed, encoding="utf-8", newline="")
    before = _manifest(root).read_bytes()

    assert _run2(root)[0] == 0, "a report reads, so it works on any file that parses"

    code, _out, err = _run2(root, "--apply")

    assert code == 1
    assert "line ending" in err
    assert _manifest(root).read_bytes() == before
    assert not _backup(root).exists()


# --- Exit codes: `--apply` adds `1` and changes neither `0` nor `3` ------------------------------


def test_a_conflict_is_zero_as_a_report_and_one_under_apply(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The same finding, two codes, and the discriminator is whether a write was asked for.

    A report has nothing to fail at, so a conflicting report exits `0` and stays usable beside
    `pnk doctor` in one script. Once `--apply` is passed the command was asked to do something it
    could not do, and *something is wrong and it is yours to fix* is exactly what `1` already means
    everywhere else in this CLI.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    _manifest(root).write_text(
        _manifest(root)
        .read_text(encoding="utf-8")
        .replace('exclude = ["**/drafts/**"]', 'exclude = ["**/drafts/**"]  # mine'),
        encoding="utf-8",
    )

    assert _run2(root)[0] == 0
    assert _run2(root, "--apply")[0] == 1


def test_cannot_compare_under_apply_still_exits_three_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """Against the shipped `notes`, because this is what a real KB gets today and will get forever:
    `notes@1.0` is unarchived by decision, so there is no baseline to apply anything against.

    `3` means *the comparison could not be made and no action of yours would make it possible* —
    `--apply` does not change that, and turning it into `1` would tell 100% of users that something
    of theirs is broken.
    """
    from pinakes.init import init

    root = init(tmp_path / "kb", now="20260725 09:14").root
    edited, count = re.subn(
        r'^template = ".+"$',
        'template = "notes@1.0"',
        _manifest(root).read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1, "the manifest's template line has changed shape"
    _manifest(root).write_text(edited, encoding="utf-8")
    before = _manifest(root).read_bytes()

    code, out, _err = _run2(root, "--apply")

    assert code == 3
    assert "cannot compare" in out
    assert _manifest(root).read_bytes() == before
    assert not _backup(root).exists()


def test_up_to_date_under_apply_writes_nothing(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The shape the free-path run exercises: a KB `pnk init` just created records the installed
    reference, so `--apply` takes the *up to date* path. It proves the flag imports and parses on
    the free path — it does **not** exercise the writer, and a later reader who assumes it does
    will delete a test that matters."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "2.0")
    before = _tree(root)

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert out.startswith("up to date: synth@2.0")
    assert _tree(root) == before


# --- `--json --apply`: one document, whatever happened ------------------------------------------


def test_json_apply_emits_one_document_carrying_the_result(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """Two JSON documents on one stdout is not JSON, so the report is not printed separately under
    `--json --apply`. Nothing is lost: the ordering the consent path needs is a property of the
    human output, where a person is the one deciding."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")

    code, out, err = _run2(root, "--json", "--apply")
    payload = json.loads(out)

    assert code == 0, err
    assert payload["refused"] is None
    assert payload["applied"] == {
        "written": 2,
        "skipped": 0,
        "backup": str(_backup(root)),
        "template": "synth@2.0",
        "invalidates": [],
        "introduced": [],
    }
    assert payload["spend"] == [
        {"key": "budget.per_operation_eur", "before": "0.05", "after": "0.30"}
    ]


def test_json_apply_emits_the_refusal_as_json_rather_than_a_traceback(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """A caller who asked for machine-readable output should not have to parse a message off stderr
    to learn that nothing was written."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    _manifest(root).write_text(
        _manifest(root)
        .read_text(encoding="utf-8")
        .replace('exclude = ["**/drafts/**"]', 'exclude = ["**/drafts/**"]  # mine'),
        encoding="utf-8",
    )

    code, out, _err = _run2(root, "--json", "--apply")
    payload = json.loads(out)

    assert code == 1
    assert payload["applied"] is None
    assert "[sources]" in payload["refused"]["message"]
    assert payload["spend"] == [], "nothing is written, so no money moves"


# --- What the first adversarial pass found, each with the mutant it kills ------------------------


def test_a_manifest_with_a_unicode_line_separator_is_refused_rather_than_rewritten(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The report and the writer split lines differently, and this is where that bites.

    `hunks()` reaches `str.splitlines()`, which breaks on a form feed, `\\x85`, `\\u2028` and half a
    dozen more; the writer's `split("\\n")` breaks on none of them. A manifest carrying one — legal
    inside a TOML comment — is a **different list of lines** on each side, so a hunk the report
    called unique can match elsewhere here, or nowhere. Rejoining on `\\n` would turn that character
    into a newline in a file the user owns, so it is refused instead.
    """
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    _manifest(root).write_text(
        _manifest(root).read_text(encoding="utf-8").replace("[budget]", "# a\u2028b\n[budget]", 1),
        encoding="utf-8",
    )
    before = _manifest(root).read_bytes()

    assert _run2(root)[0] == 0, "the report reads, so it still works"

    code, _out, err = _run2(root, "--apply")

    assert code == 1
    assert "breaks lines on" in err
    assert _manifest(root).read_bytes() == before
    assert not _backup(root).exists()


def test_a_symlinked_manifest_is_written_through_not_replaced(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`os.replace` onto a symlink destroys the link and leaves a regular file, with the real
    manifest untouched somewhere else still holding the old text — the user's own arrangement
    dismantled silently. `sidecar.write` learned this first; this is the same resolve."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    elsewhere = tmp_path / "shared" / "pinakes.toml"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(_manifest(root).read_bytes())
    _manifest(root).unlink()
    _manifest(root).symlink_to(elsewhere)

    code, _out, err = _run2(root, "--apply")

    assert code == 0, err
    assert _manifest(root).is_symlink(), "the link was replaced by a regular file"
    assert "per_operation_eur = 0.30" in elsewhere.read_text(encoding="utf-8"), (
        "the real manifest was left holding the old text"
    )


def test_apply_keeps_the_manifests_own_permissions(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """`mkstemp` creates its file `0600`, so renaming it into place would silently narrow a manifest
    the user had made group- or world-readable. The mode is copied from the file being replaced,
    which is the only place the intended value exists."""
    import stat

    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    _manifest(root).chmod(0o644)

    assert _run2(root, "--apply")[0] == 0

    assert stat.S_IMODE(_manifest(root).stat().st_mode) == 0o644


def test_a_dotted_key_is_named_in_full_not_by_its_first_segment() -> None:
    """A dotted key parses to nested tables, so reading the single top-level name reports
    `budget.monthly_eur = 30.00` as a key called `budget` — and the spending-cap heading would name
    a table rather than the cap that moved.

    Driven at `changes()` because that is the unit: no template ships a dotted key today, so a
    fixture-driven test would assert nothing about the branch it claims to cover.
    """
    from pinakes.upgrade import Hunk, Placement, changes

    hunk = Hunk(
        header="@@ -1,3 +1,3 @@",
        section=None,
        lines=(" # caps", "-budget.monthly_eur = 5.00", "+budget.monthly_eur = 30.00"),
        placement=Placement.CLEAN,
    )

    assert [(change.key, change.before, change.after) for change in changes(hunk)] == [
        ("budget.monthly_eur", "5.00", "30.00")
    ]


def test_a_table_added_inside_a_hunk_moves_the_section_from_there_on() -> None:
    """`hunk.section` is the table the hunk *starts* in, read backwards out of `base` — so a hunk
    that adds a whole new table carries keys belonging to a table `base` does not have.

    Attributing those to the preceding table is not a cosmetic mislabel. The fixture here adds a
    table directly after `[budget]`; under the old attribution every one of its keys was a
    **spending cap**, announced under the heading whose entire job is naming what money is moving.
    The same mistake in `[chunking]`'s neighbourhood invents an index rebuild.
    """
    from pinakes.upgrade import Hunk, Placement, changes

    hunk = Hunk(
        header="@@ -40,4 +40,7 @@",
        section="[budget]",
        lines=(
            " monthly_eur       = 30.00",
            '-timezone          = "UTC"',
            '+timezone          = "CET"',
            "+",
            "+[extraction]",
            '+backend = "pdfium"',
        ),
        placement=Placement.CLEAN,
    )

    assert [(change.path, change.after) for change in changes(hunk)] == [
        ("budget.timezone", '"CET"'),
        ("extraction.backend", '"pdfium"'),
    ]


def test_splices_refuses_two_hunks_that_land_on_top_of_each_other() -> None:
    """`difflib` yields hunks disjoint in `base`; nothing makes their **placements in `theirs`**
    disjoint, and overlapping edits have no defined result — which is what a conflict is.

    Driven at `splices` because no fixture reaches it: `_placement` classifies each hunk on its own,
    so producing two clean hunks that collide needs a `theirs` built for the purpose. The guard
    would otherwise ship untested, and an untested refusal is a refusal nobody has seen fire.
    """
    from pinakes.errors import UpgradeError
    from pinakes.upgrade import Hunk, Placement, Report, splices

    content = ["a", "b", "c", "d"]
    overlapping = Report(
        outcome=Outcome.DRIFTED,
        detail="x",
        hunks=(
            Hunk("@@ 1 @@", None, (" a", " b", "+x"), Placement.CLEAN),
            Hunk("@@ 2 @@", None, (" b", " c", "+y"), Placement.CLEAN),
        ),
    )

    with pytest.raises(UpgradeError, match="land on top of each other"):
        splices(overlapping, content)

    # ...and the control: the same two hunks over regions that do not touch are planned, not
    # refused. A guard that fires on everything passes the assertion above just as well.
    apart = Report(
        outcome=Outcome.DRIFTED,
        detail="x",
        hunks=(
            Hunk("@@ 1 @@", None, (" a", "+x"), Placement.CLEAN),
            Hunk("@@ 2 @@", None, (" d", "+y"), Placement.CLEAN),
        ),
    )
    assert [(one.start, one.stop) for one in splices(apart, content)] == [(0, 1), (3, 4)]


def test_splices_refuses_a_hunk_that_no_longer_places_uniquely() -> None:
    """Unreachable through the command — `_placement` established uniqueness over the same text a
    moment earlier — and pinned anyway, because the alternative to refusing is writing at a guessed
    position in a file the user owns."""
    from pinakes.errors import UpgradeError
    from pinakes.upgrade import Hunk, Placement, Report, splices

    twice = Report(
        outcome=Outcome.DRIFTED,
        detail="x",
        hunks=(Hunk("@@ 1 @@", None, (" a", "+x"), Placement.CLEAN),),
    )

    with pytest.raises(UpgradeError, match="single position"):
        splices(twice, ["a", "b", "a"])


def test_same_manifest_under_apply_writes_nothing(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """A version bump that leaves the manifest byte-identical has no hunks, so `--apply` has nothing
    to apply and writes nothing — **including the `[kb] template` restamp**.

    That is the plan's reading taken literally rather than extended: `--apply` is specified in terms
    of hunks. The consequence is real and is recorded in `plans/20260731_1202-open-corrections.md`
    rather than silently fixed — a KB on this path keeps reporting drift with no way to record the
    new reference, and deciding otherwise is a change to what the command does, not a detail.
    """
    name = synthetic_template(
        "synth",
        versions={"1.0": _source(), "2.0": _source()},
        current="2.0",
    )
    root = _stamp(tmp_path / "kb", name, "1.0")
    before = _tree(root)

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert "stamp an identical pinakes.toml" in out
    assert _tree(root) == before


def test_the_backup_is_named_by_its_full_path_when_it_leaves_the_kb(
    tmp_path: Path, synthetic_template: Callable[..., str]
) -> None:
    """The backup is written beside the file it backs up, so a symlinked `pinakes.toml` puts it in
    another directory. Printing the bare filename then sends the user looking in their KB for a file
    that is not there — the output would be true of the ordinary case and misleading in the one
    where finding it actually takes work."""
    name = _spend_pair(synthetic_template)
    root = _stamp(tmp_path / "kb", name, "1.0")
    elsewhere = tmp_path / "shared" / "pinakes.toml"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(_manifest(root).read_bytes())
    _manifest(root).unlink()
    _manifest(root).symlink_to(elsewhere)

    code, out, err = _run2(root, "--apply")

    assert code == 0, err
    assert str(elsewhere.parent.resolve() / "pinakes.toml.orig") in out
    assert (elsewhere.parent / "pinakes.toml.orig").exists()
    assert not _backup(root).exists()
