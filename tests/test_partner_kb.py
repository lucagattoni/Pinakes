"""The two committed corpora, and the gate that keeps their authored links sparse.

The gate is driven as a **subprocess**, for the reason `tests/test_fragments.py` and
`tests/test_paid_path.py` both give: it exercises the same artifact `check.sh` and CI run, argument
parsing included, and needs no `sys.path` surgery the type checkers then cannot resolve.

Every negative case builds its own throwaway corpus. A gate whose only fixture is the real corpus
can only be tested in whichever direction that corpus happens to point — and this one exists
precisely because a corpus can drift the other way.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
import yaml

from pinakes.ids import mint_doc_id, mint_kb_id, parse_doc_id, parse_kb_id
from pinakes.manifest import load
from pinakes.sidecar import SIDECAR_SUFFIX

TOOL = Path(__file__).parent.parent / "tools" / "link_density_gate.py"
DEMO = Path(__file__).parent / "demo-kb"
PARTNER = Path(__file__).parent / "partner-kb"

MANIFEST = """\
[kb]
name     = "{name}"
id       = "{kb_id}"
template = "notes@1.0"
created  = "20260729 08:00"

[sources]
roots   = ["docs/"]
include = ["**/*.md"]

[embedding]
provider = "fastembed"
model    = "BAAI/bge-small-en-v1.5"
dim      = 384

[chunking]
strategy   = "structural"
max_tokens = 120
overlap    = 16

[retrieval]
candidates_per_source = 30
fusion                = "rrf"
fusion_top_k          = 12
final_k               = 5
rerank                = "local"
vector_tier           = "numpy"

[rerank]
provider = "fastembed"
model    = "BAAI/bge-reranker-base"
"""


def gate(*roots: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *[str(root) for root in roots]],
        capture_output=True,
        text=True,
        check=False,
    )


def corpus(root: Path, *, documents: int, links: dict[int, list[tuple[str, str]]]) -> Path:
    """A throwaway KB. `links` maps a document's index to `(target-kb-id, rel)` pairs."""
    (root / "docs").mkdir(parents=True)
    kb_id = mint_kb_id()
    (root / "pinakes.toml").write_text(
        MANIFEST.format(name=root.name, kb_id=kb_id), encoding="utf-8"
    )
    for index in range(documents):
        name = f"doc{index}.md"
        (root / "docs" / name).write_text(f"# Doc {index}\n\nText.\n", encoding="utf-8")
        body: dict[str, object] = {"id": str(mint_doc_id()), "title": f"doc {index}"}
        if index in links:
            body["links"] = [
                {"to": f"pnk://{target}/{mint_doc_id()}", "rel": rel}
                for target, rel in links[index]
            ]
        (root / "docs" / f"{name}{SIDECAR_SUFFIX}").write_text(
            yaml.safe_dump(body, sort_keys=False), encoding="utf-8"
        )
    return root


def links_of(body: dict[str, object]) -> list[dict[str, object]]:
    """The `links` entries of one sidecar, as a list the type checkers can reason about.

    `body.get("links", []) or []` reads fine and types as `object`, which is how a test that means
    to iterate links ends up iterating anything at all.
    """
    raw = body.get("links")
    if not isinstance(raw, list):
        return []
    return [
        cast(dict[str, object], entry)
        for entry in cast(list[object], raw)
        if isinstance(entry, dict)
    ]


def sidecars(root: Path) -> dict[Path, dict[str, object]]:
    return {
        path: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob(f"*{SIDECAR_SUFFIX}"))
    }


# --- The committed corpora ---------------------------------------------------------------------


def test_both_corpora_load_and_validate() -> None:
    for root, name in ((DEMO, "demo"), (PARTNER, "partner")):
        manifest = load(root)
        assert manifest.kb.name == name
        assert manifest.links, f"{name} lists no connected KB"

    # Each names the other, by ULID and not by alias — a `[[links.kb]] name` is machine-local.
    assert load(DEMO).links[0].id == load(PARTNER).kb.id
    assert load(PARTNER).links[0].id == load(DEMO).kb.id


def test_every_sidecar_ulid_is_wellformed_and_unique_across_both_kbs() -> None:
    """Across *both*, not within each. Two documents in different KBs sharing an id would make
    every `pnk://` link ambiguous the moment the two corpora are used together — which is the only
    way they are ever used."""
    seen: dict[str, Path] = {}
    for root in (DEMO, PARTNER):
        for path, body in sidecars(root).items():
            raw = body["id"]
            assert isinstance(raw, str)
            parse_doc_id(raw)  # raises if it is not a ULID
            assert raw not in seen, f"{path} and {seen[raw]} both claim {raw}"
            seen[raw] = path
    assert len(seen) == 51


def test_every_link_target_is_a_resolvable_uri() -> None:
    """The gate counts links; it does not parse their targets. A malformed target is a different
    failure, and one that used to be catastrophic (see `sidecar.create`)."""
    for root in (DEMO, PARTNER):
        owner = load(root).kb.id
        for path, body in sidecars(root).items():
            for entry in links_of(body):
                target = entry["to"]
                assert isinstance(target, str) and target.startswith("pnk://"), path
                head, _, doc = target[len("pnk://") :].partition("/")
                if head.lower() != "self":
                    parse_kb_id(head)
                parse_doc_id(doc)
            assert owner  # the manifest loaded, which is what makes `self` resolvable at all


def test_the_committed_corpora_pass_their_own_gate() -> None:
    result = gate(DEMO, PARTNER)
    assert result.returncode == 0, result.stderr
    assert "demo-kb:" in result.stdout and "partner-kb:" in result.stdout
    assert "intra-KB" in result.stdout and "relations:" in result.stdout


def test_the_committed_split_is_what_pnk_doctor_counts() -> None:
    """Pins the real corpora's numbers, not just that the gate is happy with them.

    The gate's count and `pnk doctor`'s must be the same population (L7) — a user reading one and
    CI enforcing the other is how they drift apart. These are the numbers `pnk doctor` reports:
    `16 links, 4 cross-KB` for demo and `13 links, 7 cross-KB` for partner, verified by running it.
    A synthetic corpus cannot pin this; only the committed one can.
    """
    result = gate(DEMO, PARTNER)
    assert "12 intra-KB + 4 cross-KB" in result.stdout, result.stdout
    assert "6 intra-KB + 7 cross-KB" in result.stdout, result.stdout
    # The partner's seventh cross-KB link is the absent-KB fixture; its `self`-form link is counted
    # intra, which is the whole reason `self` resolves to the owner here as it does in `sidecar.py`.
    assert "8 linked" in result.stdout and "6 linked" in result.stdout


# --- The fixtures L2 and L7 need, authored here rather than invented there ----------------------


def test_the_partner_corpus_carries_a_self_form_link() -> None:
    """`pnk://self/<doc>` in a *partner* sidecar is the trap L2 must not fall into: read with the
    local KB as `owner`, it resolves to the wrong KB and mints links the partner never wrote. The
    corpus carries the trap so L2's test cannot quietly build one it already knows how to
    survive."""
    found = [
        path
        for path, body in sidecars(PARTNER).items()
        for entry in links_of(body)
        if str(entry["to"]).startswith("pnk://self/")
    ]
    assert found, "no self-form link in the partner corpus"


def test_the_partner_corpus_carries_a_target_in_a_kb_nothing_provides() -> None:
    """L2's third-KB filter and L7's dangling-target WARN both need one. A well-formed ULID that
    resolves to nothing is the whole fixture — no third corpus required."""
    known = {str(load(DEMO).kb.id), str(load(PARTNER).kb.id)}
    absent = [
        str(entry["to"])
        for _path, body in sidecars(PARTNER).items()
        for entry in links_of(body)
        if not str(entry["to"]).startswith("pnk://self/")
        and str(entry["to"])[len("pnk://") :].partition("/")[0] not in known
    ]
    assert absent, "no link to an absent KB in the partner corpus"


# --- The gate's negative cases -----------------------------------------------------------------


def test_a_corpus_over_the_density_cap_fails_the_gate(tmp_path: Path) -> None:
    dense = corpus(
        tmp_path / "dense",
        documents=10,
        links={index: [(str(mint_kb_id()), "related")] for index in range(6)},
    )
    result = gate(dense)
    assert result.returncode == 1
    assert "above the 35% cap" in result.stderr


def test_a_corpus_exactly_at_the_cap_passes(tmp_path: Path) -> None:
    """The boundary, from the other side. `>` and `>=` differ by exactly this corpus, and a gate
    that rejects what it documents as permitted is as wrong as one that permits what it forbids."""
    at_cap = corpus(
        tmp_path / "at-cap",
        documents=20,
        links={
            index: [(str(mint_kb_id()), "related")] if index else [("self", "related")]
            for index in range(7)
        },
    )
    result = gate(at_cap)
    assert result.returncode == 0, result.stderr
    assert "35% of the 35% cap" in result.stdout


def test_a_corpus_with_a_hub_document_fails_the_gate(tmp_path: Path) -> None:
    """Density alone permits one document wired to everything — a different corpus with the same
    headline number, and the one shape that would make traversal look easy."""
    hub = corpus(
        tmp_path / "hub",
        documents=20,
        links={0: [("self", "related")] + [(str(mint_kb_id()), "related") for _ in range(4)]},
    )
    result = gate(hub)
    assert result.returncode == 1
    assert "above the\ndegree cap" in result.stderr.replace(" \n", "\n") or "degree cap" in (
        result.stderr
    )
    assert "doc0.md" in result.stderr


def test_a_corpus_whose_links_are_all_cross_kb_fails_the_gate(tmp_path: Path) -> None:
    """A cross-KB row's `src_kb_id` is foreign, so it resolves to no local node and contributes no
    channel edge. A corpus linked only outward makes the graph release's with/without-authored
    guard compare two identical edge sets — it passes while discriminating nothing."""
    outward = corpus(
        tmp_path / "outward",
        documents=20,
        links={index: [(str(mint_kb_id()), "related")] for index in range(3)},
    )
    result = gate(outward)
    assert result.returncode == 1
    assert "every authored link is cross-KB" in result.stderr


def test_a_corpus_with_no_links_at_all_passes(tmp_path: Path) -> None:
    """Sparsity is a ceiling, not a floor. `pnk doctor` nudges a KB with no authored links (L7);
    the gate must not, or every KB fails from the day it is created."""
    empty = corpus(tmp_path / "empty", documents=5, links={})
    assert gate(empty).returncode == 0


def test_the_gate_runs_without_an_index(tmp_path: Path) -> None:
    """It runs in `check.sh`, which never builds one — so it reads the committed sidecars, which is
    also what makes its population the same one `pnk doctor` reports to a user (L7)."""
    plain = corpus(tmp_path / "plain", documents=4, links={0: [("self", "related")]})
    assert not (plain / ".pinakes").exists()
    result = gate(plain)
    assert result.returncode == 0, result.stderr
    assert not (plain / ".pinakes").exists(), "the gate built an index"


def test_a_directory_that_is_not_a_kb_is_refused(tmp_path: Path) -> None:
    result = gate(tmp_path / "nothing-here")
    assert result.returncode == 1
    assert "is not a KB root" in result.stderr


@pytest.mark.parametrize("flag", ["--max-density", "--max-degree"])
def test_the_caps_are_settable_so_the_boundary_is_testable(tmp_path: Path, flag: str) -> None:
    """Not a feature for users — the boundary of a hard-coded constant can only be tested from one
    side, and both sides is the point."""
    kb = corpus(tmp_path / f"kb{flag}", documents=10, links={0: [("self", "related")]})
    tightened = subprocess.run(
        [sys.executable, str(TOOL), str(kb), flag, "0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tightened.returncode == 1
    assert gate(kb).returncode == 0
