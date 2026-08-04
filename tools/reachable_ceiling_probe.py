"""The channel-reachable ceiling, measured in memory before any schema bumps (G2).

**What this answers, and why the answer is not "how many questions fail".** G5's gate needs
improvements, and an improvement can only come from a question that fails *today*. But failing is
necessary and nowhere near sufficient: a question is only *liftable* if the evidence its failing
hop needs lies within 2 logical hops of that hop's fused seeds, in the edge set G3 would derive.
With `mentions` cut (decision 6) every surviving structural edge connects things already near each
other, and the golden set's own authoring rule — evidence split across two documents with no shared
vocabulary — actively selects for pairs those edges cannot bridge. A failure count alone can pass
with zero reachable questions, bump `schema_version`, force every KB in existence to rebuild, and
only then reveal that the gate was unreachable.

**Two numbers, and only one of them binds.** Reachability is computed **with** and **without**
authored edges. A corpus reachable only through links its own author wrote cannot tell you whether
*derived* structure helps — the "1.00 by construction" shape decision 14 cut cross-KB questions
over. The without-authored figure is the precondition; the with-authored figure is recorded and
licenses nothing.

**In memory, at `schema_version` 2.** Nothing here writes a table, and the point is the ordering:
if the ceiling is not there, G3 must not have bumped the schema to find out.

**This is throwaway measurement code, not the G3 deriver.** It is the probe's reading of
APPROACH §3 and §4A, and G5's implementation is the authority if the two ever disagree:

* A **logical hop** is a chunk-or-doc → chunk-or-doc transition. Hub nodes (directory, tag,
  heading) and membership edges are transit, not distance, so `doc → dir-hub → doc` is one hop.
* `parent`/`child` are read as *intra-document* hierarchy. `heading_path` prefixes compared across
  documents would make every document sharing a heading title adjacent, which is exactly the
  global-hub failure APPROACH scopes heading nodes per document to avoid.
* A hub expands **once globally** (visited-edge dedup) and yields at most `adjacent_k` chunks,
  ranked by cosine against the hop's own query — because a hub node carries no content embedding
  and contributes its member chunks, query-ranked, like any others.
* Same-document chunks reachable **only** through their own document's membership edge are dropped
  before the `adjacent_k` cut, so they consume no fan-out budget either.

The generosity is deliberate and stated: this is a *ceiling*. A document that survives the fan-out
cut is counted reachable even though the channel would still have to out-rank everything else to
change the answer. A ceiling that is already too low is decisive; a ceiling that is high proves
only that the gate is not impossible.

**The probe must be shown to fail.** `--drop co-located` (or any edge kind) re-runs with that kind
removed; if the reachable count does not move, the probe is measuring something other than the edge
set and its output means nothing. `tests/test_eval.py` pins that.

**A golden set it cannot measure is refused, never absorbed** (`check_measurable`). The failure
class, which is the reason this section exists: a malformed question used to be turned into a
plausible verdict and counted, so the output looked exactly as valid as a correct one — the worst
thing a measurement tool can do, because nobody re-derives a number that already looks fine. Every
shape below is refused by name, before a backend is even loaded:

* a hop whose `expect` names a path the index does not hold — it resolved to no document at all
  and was counted failing-and-unreachable, so one typo deflated the ratio the precondition binds
  on;
* a hop whose `expect` names a document the index holds with **no chunks**. Every node the channel
  walks is built from the `chunks` table, so such a document can neither be retrieved nor reached:
  the same corrupted verdict, from a path that is spelled correctly;
* a `multi-hop` question with fewer than `MIN_HOPS` hops. With none it yielded no verdict while
  still counting in the denominator, so it could never be `failing` and vanished from every other
  figure; with one it is measured as a single search and moves `liftable` **upward**, which is the
  dangerous direction — the precondition is a floor;
* a hop with an empty `query`, which fails on its own terms rather than the corpus's;
* a question whose `filters` admit no document, or do not admit its own last hop's `expect`. They
  are applied to the last hop, so they decide whether it can land at all. Measured on demo-kb
  under the fake backend (9 failing / 3 liftable): one unmatched tag took `failing` to 10 and left
  `liftable` at 3; the same tag on every multi-hop question took the run to 18 failing / 0
  liftable, in silence;
* two identical hops in one question — one retrieval written twice, clearing the `MIN_HOPS`
  floor while asking a single question;
* a golden set with no `multi-hop` question at all, whose every figure would be a zero
  indistinguishable from a measured one.

All of them are likely on a real corpus rather than hypothetical: a converted question set is
hand-written, and `hops` is the part of the schema a reader can miss.

**Every output names the three inputs the numbers are a function of** — the corpus (root path,
absolute and resolved, plus kb-ulid and when its index was built), the golden set (path, sha256,
how many questions and how many of them multi-hop), and the pipeline (embedding, reranker and
retrieval settings, each down to the model and revision that select the weights). Two runs
otherwise produce artifacts that cannot be told apart, and every one of the three has been
measured moving a figure while the other two stayed identical: a different corpus, a rewritten
golden set, a swapped reranker. `failing` is `expect` in the top `final_k` after fusion and
reranking — the corpus's name alone does not identify a measurement.

One exception, and it is `--fake`'s alone: that path syncs its copy at a fixed clock, so
`index_built_at` is a constant there and `kb_root` is a temporary directory. Edit `tests/demo-kb`
and a `--fake` artifact moves its figures while every identifying field but the temp path stays
equal. `--fake` exists to prove the mechanism offline, and its numbers are labelled `fake_backend`
for that reason; a measurement that decides anything is a `--kb` run, where `pnk sync` writes a
fresh `built_at` for every corpus edit that could move a figure.

Usage:
    python3 tools/reachable_ceiling_probe.py                    # real models, the measurement
    python3 tools/reachable_ceiling_probe.py --kb path/to/kb    # another corpus
    python3 tools/reachable_ceiling_probe.py --fake             # offline, for tests
    python3 tools/reachable_ceiling_probe.py --drop co-located  # prove the number moves
    python3 tools/reachable_ceiling_probe.py --json
"""

import argparse
import hashlib
import json
import posixpath
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence, Set
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pinakes import store
from pinakes.embed import (
    EmbeddingBackend,
    ModelInfo,
    Reranker,
    Vectors,
    load_backend,
    load_reranker,
    register_embedding_backend,
    register_reranker,
)
from pinakes.eval import Question, load_questions
from pinakes.manifest import Manifest, load
from pinakes.search import Filters, fused_candidates, search, unit_vectors
from pinakes.sync import SyncOptions, sync

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "tests" / "demo-kb"

STRUCTURAL_KINDS = ("sibling", "parent-child", "in-section", "co-located", "shared-tag")
AUTHORED = "authored"
ALL_KINDS = (*STRUCTURAL_KINDS, AUTHORED)

DEPTH = 2
"""APPROACH §4A's expansion depth, in logical hops. Not a knob: the gate is defined here."""

FAR_DEPTH = 6
"""Used only to separate "unreachable" from "reachable, but further than the channel looks"."""

FAKE_DIM = 64


# --------------------------------------------------------------------------------------------
# The in-memory edge set


@dataclass(frozen=True, slots=True)
class Chunk:
    id: int
    doc: str
    ordinal: int
    heading_path: str | None


@dataclass
class Graph:
    """Every node the channel could walk, derived from a `schema_version` 2 index and nothing else.

    Hubs are `dict[hub key, member list]` rather than materialised pairwise edges, which is the
    whole point of APPROACH §3's hub model: a tag on 30 documents is 30 spokes, not 435 edges.
    """

    chunks: dict[int, Chunk]
    chunk_kinds: set[str] = field(default_factory=set[str])
    """Which chunk ↔ chunk kinds this graph was derived with — `sibling`, `parent-child`, or
    neither. They materialise no hub, so unlike every other kind they cannot be read off the
    structures below, and `--drop sibling` would otherwise silently do nothing."""

    by_doc: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    doc_path: dict[str, str] = field(default_factory=dict[str, str])
    dir_hub: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    tag_hub: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    heading_hub: dict[tuple[str, str], list[int]] = field(
        default_factory=dict[tuple[str, str], list[int]]
    )
    authored: dict[str, set[str]] = field(default_factory=dict[str, set[str]])

    def hubs_of_doc(self, doc: str) -> list[tuple[str, str]]:
        hubs: list[tuple[str, str]] = []
        directory = posixpath.dirname(self.doc_path[doc])
        if directory in self.dir_hub:
            hubs.append(("co-located", directory))
        for tag, members in self.tag_hub.items():
            if doc in members:
                hubs.append(("shared-tag", tag))
        return hubs


def derive(connection: sqlite3.Connection, kb_id: str, *, kinds: Sequence[str]) -> Graph:
    """G3's edge set, in memory, from the tables that already exist.

    `kinds` is what makes the with/without-authored split and `--drop` possible at all: an edge
    kind absent from it is never derived, so nothing downstream can reach through it.
    """
    documents = {
        str(row["id"]): str(row["path"])
        for row in connection.execute(
            "SELECT id, path FROM documents WHERE state = 'active' ORDER BY path"
        )
    }
    chunks: dict[int, Chunk] = {}
    graph = Graph(
        chunks=chunks,
        chunk_kinds={k for k in kinds if k in {"sibling", "parent-child"}},
        doc_path=documents,
    )

    rows = connection.execute(
        "SELECT c.id, c.doc_id, c.ordinal, c.heading_path FROM chunks c "
        "JOIN documents d ON d.id = c.doc_id WHERE d.state = 'active' "
        "ORDER BY d.path, c.ordinal"
    )
    for row in rows:
        chunk = Chunk(
            id=int(row["id"]),
            doc=str(row["doc_id"]),
            ordinal=int(row["ordinal"]),
            heading_path=None if row["heading_path"] is None else str(row["heading_path"]),
        )
        chunks[chunk.id] = chunk
        graph.by_doc.setdefault(chunk.doc, []).append(chunk.id)
        if "in-section" in kinds and chunk.heading_path is not None:
            graph.heading_hub.setdefault((chunk.doc, chunk.heading_path), []).append(chunk.id)

    if "co-located" in kinds:
        for doc, path in documents.items():
            graph.dir_hub.setdefault(posixpath.dirname(path), []).append(doc)

    if "shared-tag" in kinds:
        for row in connection.execute(
            "SELECT d.id, j.value AS tag FROM documents d, json_each(d.metadata, '$.tags') j "
            "WHERE d.state = 'active' ORDER BY d.path"
        ):
            graph.tag_hub.setdefault(str(row["tag"]), []).append(str(row["id"]))

    if AUTHORED in kinds:
        # Only a *local* document has a `doc` node (G3), so an edge with either end in another KB
        # resolves to nothing and never enters the channel — in both directions.
        for row in connection.execute("SELECT * FROM links"):
            src_kb, dst_kb = str(row["src_kb_id"]), str(row["dst_kb_id"])
            src, dst = str(row["src_doc_id"]), str(row["dst_doc_id"])
            if src_kb != kb_id or dst_kb != kb_id or src not in documents or dst not in documents:
                continue
            graph.authored.setdefault(src, set()).add(dst)
            graph.authored.setdefault(dst, set()).add(src)

    return graph


# --------------------------------------------------------------------------------------------
# Expansion


def reachable_docs(
    graph: Graph,
    seeds: Sequence[int],
    similarity: dict[int, float],
    *,
    adjacent_k: int,
    depth: int,
    exclude_membership: bool = True,
) -> set[str]:
    """Documents within `depth` logical hops of `seeds`, under the channel's two bounding rules."""
    root_docs = {graph.chunks[c].doc for c in seeds if c in graph.chunks}
    frontier_chunks = {c for c in seeds if c in graph.chunks}
    frontier_docs = set(root_docs)
    expanded_hubs: set[tuple[str, object]] = set()
    reached: set[str] = set()

    for _ in range(depth):
        found: set[int] = set()

        # Chunk-level structure: sibling and intra-document hierarchy, both direct chunk ↔ chunk.
        for chunk_id in frontier_chunks:
            chunk = graph.chunks[chunk_id]
            for sibling in graph.by_doc.get(chunk.doc, ()):
                other = graph.chunks[sibling]
                if "sibling" in graph.chunk_kinds and abs(other.ordinal - chunk.ordinal) == 1:
                    found.add(sibling)
                if (
                    "parent-child" in graph.chunk_kinds
                    and chunk.heading_path
                    and other.heading_path
                    and _is_prefix(chunk.heading_path, other.heading_path)
                ):
                    found.add(sibling)
            if chunk.heading_path is not None:
                key = (chunk.doc, chunk.heading_path)
                if key in graph.heading_hub and ("in-section", key) not in expanded_hubs:
                    expanded_hubs.add(("in-section", key))
                    found.update(graph.heading_hub[key])

        # Document-level structure: every shared-value relation goes through its hub, and each hub
        # expands once globally — a popular tag or a big directory is not re-walked per encounter.
        for doc in frontier_docs:
            for kind, key in graph.hubs_of_doc(doc):
                if (kind, key) in expanded_hubs:
                    continue
                expanded_hubs.add((kind, key))
                members = graph.dir_hub[key] if kind == "co-located" else graph.tag_hub[key]
                found.update(
                    _rank_hub_members(
                        graph,
                        members,
                        similarity,
                        adjacent_k=adjacent_k,
                        drop_docs=root_docs if exclude_membership else set(),
                        already=found,
                    )
                )
            for neighbour in graph.authored.get(doc, ()):
                found.update(graph.by_doc.get(neighbour, ()))

        frontier_chunks = found
        frontier_docs = {graph.chunks[c].doc for c in found}
        reached |= frontier_docs
        if not found:
            break
    return reached


def _is_prefix(a: str, b: str) -> bool:
    return a != b and (b.startswith(a + " > ") or a.startswith(b + " > "))


def _rank_hub_members(
    graph: Graph,
    members: Sequence[str],
    similarity: dict[int, float],
    *,
    adjacent_k: int,
    drop_docs: set[str],
    already: set[int],
) -> list[int]:
    """A hub carries no embedding: it contributes its member chunks, query-ranked and capped.

    `drop_docs` are the roots' own documents. Their chunks are reachable here only through their
    own document's membership edge, which APPROACH §3 excludes from the channel's output **and**
    from its fan-out budget — so they are dropped *before* the cut, never counted against it.
    """
    candidates = [
        chunk_id
        for doc in members
        if doc not in drop_docs
        for chunk_id in graph.by_doc.get(doc, ())
        if chunk_id not in already
    ]
    candidates.sort(key=lambda c: (-similarity.get(c, 0.0), graph.doc_path[graph.chunks[c].doc], c))
    return candidates[:adjacent_k]


# --------------------------------------------------------------------------------------------
# What the probe refuses to measure


class UnmeasurableGoldenSet(SystemExit):
    """The golden set holds a question this probe cannot turn into an honest verdict.

    A `SystemExit` subclass, so the run stops with its reasons on stderr and exit 1 — a named
    failure a reader cannot miss, rather than a diagnostic line they have to notice. Every
    problem it can find *deflates* a count that decides whether a release is built, and a count
    that is quietly wrong is worse than no count: nothing about the output says so.
    """


def active_documents(connection: sqlite3.Connection) -> dict[str, str]:
    """Path → document id, active documents only — exactly the population `derive` walks.

    Inactive rows are excluded deliberately: a golden set naming a deleted document is broken in
    the same way as one naming a document that was never there, and a hop expecting one could
    never land whatever the edge set held.
    """
    return {
        str(row["path"]): str(row["id"])
        for row in connection.execute("SELECT id, path FROM documents WHERE state = 'active'")
    }


def documents_with_chunks(connection: sqlite3.Connection) -> set[str]:
    """Document ids the index holds at least one chunk for — the only ones a hop can ever land.

    `derive` builds every node it walks from the `chunks` table, so a document with no chunks is
    in `documents` and in no graph: neither retrieval nor expansion can produce it, whatever the
    edge set holds. Accepting one reproduces the unknown-path defect exactly — `lands=False,
    reachable=False`, for a reason that has nothing to do with the channel. A blank file, a note
    that is only front matter, or a PDF whose free extraction yielded nothing all have this shape,
    and none of them looks wrong in a golden set.
    """
    return {
        str(row["doc_id"])
        for row in connection.execute(
            "SELECT DISTINCT c.doc_id FROM chunks c JOIN documents d ON d.id = c.doc_id "
            "WHERE d.state = 'active'"
        )
    }


def documents_selected_by(
    connection: sqlite3.Connection, filters: Filters, *, path: str | None = None
) -> int:
    """How many active documents a hop's `filters` admit — optionally, whether they admit `path`.

    Built through `search`'s own `_filter_sql`, private and imported anyway on purpose: a second
    hand-written copy of the filter semantics would validate something the measurement does not
    use, and would go stale the moment `Filters` grows a field — it already carries
    `modified_after`/`modified_before`, which no golden set here uses yet.

    Imported inside the function, the way `tests/test_search_reproducibility.py` reaches for
    `_vector`: it is the one private name this file needs, and it stays visible at its use.
    """
    from pinakes.search import _filter_sql  # pyright: ignore[reportPrivateUsage]

    where, parameters = _filter_sql(filters)
    sql = f"SELECT COUNT(*) AS n FROM documents d WHERE {where}"
    if path is not None:
        sql += " AND d.path = ?"
        parameters = [*parameters, path]
    return int(connection.execute(sql, parameters).fetchone()["n"])


MIN_HOPS = 2
"""What `kind: multi-hop` claims: the answer needs at least two retrievals.

A one-hop `multi-hop` question is measured as a single search and counted in the class anyway —
and unlike the absorptions below it can move `liftable` *upward*, which is the one direction that
matters: the precondition is a floor, so over-counting licenses a `schema_version` bump that
under-counting could only block. A hand conversion that scripts hops for the first evidence
document and stops produces exactly this.
"""


def check_measurable(
    questions: Sequence[Question],
    documents: Mapping[str, str],
    *,
    chunked: Set[str],
    selected: Callable[[Filters, str | None], int],
    source: Path,
) -> None:
    """Refuse the whole run if any question would be absorbed instead of measured.

    Every problem is collected before raising, so one run names every one of them: fixing a
    question set one refusal at a time, re-syncing a corpus in between, is how a second typo gets
    found after the number has already been reported.

    `documents` is `active_documents`; `chunked` is `documents_with_chunks`; `selected` counts what
    a `Filters` admits (`documents_selected_by`). Three sources rather than one because "the index
    has this path", "a hop could land it" and "this hop's own filters admit it" are different
    questions, and the verdict depends on all three.

    Only a `multi-hop` question's *consequence* is a moved count — it is the sole kind `probe`
    measures. Problems on any other kind are still refused, because a golden set that names
    documents its index does not hold is not one to measure a release precondition against, but
    they are labelled as what they are rather than as a corrupted figure.
    """
    problems: list[str] = []
    if not any(question.kind == "multi-hop" for question in questions):
        problems.append(
            "the golden set holds no `multi-hop` question at all. There is nothing here for this "
            "probe to measure, and every figure it printed would be a zero indistinguishable from "
            "a measured one."
        )

    for question in questions:
        measured = question.kind == "multi-hop"
        # The last hop is the only one that carries the question's filters (`probe`), so it is
        # the only one whose filters can decide a verdict.
        if measured and question.hops and question.filters != Filters():
            last = question.hops[-1]
            if selected(question.filters, None) == 0:
                problems.append(
                    f"{question.id!r}: `filters` admit no active document at all. They are applied "
                    f"to the last hop, so it cannot land whatever the corpus holds: the question "
                    f"is counted failing on its own filters rather than on the corpus, and the "
                    f"count moves upward — the direction a floor reads as headroom."
                )
            elif last.expect in documents and selected(question.filters, last.expect) == 0:
                # `last.expect in documents` first, or a mistyped path would be reported twice —
                # once here, blaming a `filters:` block that is perfectly healthy, and once below
                # for what it actually is. The hop-level check owns the missing-path case.
                problems.append(
                    f"{question.id!r}: `filters` do not admit the last hop's own `expect` "
                    f"({last.expect!r}). The filtered search cannot return it, so the hop is "
                    f"counted failing for a reason that is not about the corpus."
                )
        if measured and len(question.hops) < MIN_HOPS:
            problems.append(
                f"{question.id!r}: kind `multi-hop` with {len(question.hops)} hop(s), fewer than "
                f"the {MIN_HOPS} the kind claims. With none it counts in the multi-hop "
                f"denominator, yields no verdict and so can never be counted failing — padding "
                f"one figure and vanishing from every other. With one it is measured as a single "
                f"search and can move `liftable` upward, which the precondition's floor reads as "
                f"headroom that is not there."
            )
        for path in question.expect:
            if path not in documents:
                # This probe never reads a question's own `expect` — it measures hops. Refused
                # anyway, and said plainly rather than filed under "moves the count": a golden set
                # naming a document the index does not hold is broken for `make eval`, which does
                # read it, and measuring a corpus while that is true reports a ceiling for a
                # question set nobody has checked.
                problems.append(
                    f"{question.id!r}: `expect` names {path!r}, which is not an active document "
                    f"in this index{_near_miss(path, documents)}. It moves no figure this probe "
                    f"prints — `expect` is the eval's, and the hops below are the probe's — but a "
                    f"golden set that names a document the index does not hold is not one to "
                    f"measure a release precondition against."
                )
        unreachable_for_a_non_channel_reason = (
            "The hop is recorded failing-and-unreachable for a reason that is not about the channel"
        )
        seen_hops: set[tuple[str, str]] = set()
        for index, hop in enumerate(question.hops):
            # Case-folded and whitespace-collapsed, because that is how the query reaches the
            # index: FTS5 tokenises case-insensitively and every embedding backend here splits on
            # whitespace, so `"Public Money "` and `"public money"` are one retrieval, not two.
            # No legitimate question has two hops differing only that way with the same `expect`.
            fingerprint = (" ".join(hop.query.lower().split()), hop.expect)
            if measured and fingerprint in seen_hops:
                problems.append(
                    f"{question.id!r} hop {index}: the same retrieval as an earlier hop — the same "
                    f"`expect`, and a `query` differing at most in case or spacing, which the "
                    f"index folds away. That is one retrieval written twice, so the question "
                    f"clears the {MIN_HOPS}-hop floor while asking a single question — and a hop "
                    f"repeating one already landed can move `liftable` upward, the direction a "
                    f"floor reads as headroom."
                )
            seen_hops.add(fingerprint)
            if not hop.query.strip():
                problems.append(
                    f"{question.id!r} hop {index}: an empty `query`. It retrieves nothing on its "
                    f"own terms, so it fails for the query rather than for the corpus. "
                    f"{_consequence(measured, 'That hop is counted failing')}"
                )
            if hop.expect not in documents:
                problems.append(
                    f"{question.id!r} hop {index}: `expect` names {hop.expect!r}, which is not an "
                    f"active document in this index{_near_miss(hop.expect, documents)}. It "
                    f"resolves to no document at all. "
                    f"{_consequence(measured, 'The hop is recorded failing-and-unreachable')}"
                )
            elif documents[hop.expect] not in chunked:
                problems.append(
                    f"{question.id!r} hop {index}: `expect` names {hop.expect!r}, which the index "
                    f"holds with no chunks. Every node the channel walks is built from chunks, so "
                    f"this document can neither be retrieved nor reached. "
                    f"{_consequence(measured, unreachable_for_a_non_channel_reason)} "
                    f"Re-sync, or point the hop at a document with content in it."
                )
    if not problems:
        return
    listed = "\n".join(f"  - {problem}" for problem in problems)
    raise UnmeasurableGoldenSet(
        f"unmeasurable golden set — {len(problems)} problem(s) in {source}:\n{listed}\n"
        f"Fix the golden set and re-run. Every `expect` path is matched against `documents.path` "
        f"exactly as the index stores it (KB-root-relative, forward slashes), and a `multi-hop` "
        f"question needs a `hops:` list of at least {MIN_HOPS} `query`/`expect` pairs. Refused "
        f"rather than measured: each line above is either an input that silently moves the count "
        f"this probe exists to produce, or a golden set defect that makes the corpus the wrong "
        f"one to measure — and it says which."
    )


def _consequence(measured: bool, recorded: str) -> str:
    """The half of a problem that depends on whether this probe measures the question at all.

    The whole consequence, not a trailing qualifier on one: `probe` walks `multi-hop` questions
    only, so for any other kind *nothing is recorded*, and a message that asserts the recording
    and then denies its effect contradicts itself in two sentences. Saying "the hop is recorded
    failing-and-unreachable" to the author of a `lexical` question is simply false.
    """
    if measured:
        return f"{recorded}, which moves the figures this probe prints."
    return (
        "This probe measures `multi-hop` questions only, so nothing is recorded for it and no "
        "figure printed here moves — the golden set is wrong all the same."
    )


def _near_miss(path: str, documents: Mapping[str, str]) -> str:
    """A `did you mean` when the index holds a path differing only in case, `./` or NFC/NFD.

    Never an acceptance — the lookup above stays exact, because the index's own lookup is exact.
    It exists because those three are the ways a path can be wrong while *rendering* identically
    to the right one, and a refusal naming a path that looks correct is unactionable.
    """

    def key(value: str) -> str:
        return unicodedata.normalize("NFC", value.removeprefix("./")).casefold()

    wanted = key(path)
    for candidate in documents:
        if key(candidate) == wanted:
            difference = _difference(path, candidate)
            return f" — the index holds {candidate!r}, differing only in {difference}"
    return ""


def _difference(path: str, candidate: str) -> str:
    """Which of the three invisible differences it is.

    Naming it is the point: for an NFC/NFD mismatch the hint prints a candidate that *renders
    identically* to the path just rejected, and "did you mean the same thing" is not a message
    anyone can act on.
    """
    reasons: list[str] = []
    stripped, other = path.removeprefix("./"), candidate.removeprefix("./")
    if (stripped, other) != (path, candidate):
        reasons.append("a leading `./`")
    if stripped != other:
        if stripped.casefold() == other.casefold():
            reasons.append("letter case")
        elif unicodedata.normalize("NFC", stripped) == unicodedata.normalize("NFC", other):
            reasons.append("Unicode normalisation (NFC vs NFD — the two render identically)")
        else:
            reasons.append("letter case and Unicode normalisation")
    return " and ".join(reasons) or "nothing this check can name"


# --------------------------------------------------------------------------------------------
# Running the golden set through it


@dataclass(frozen=True, slots=True)
class HopVerdict:
    question: str
    hop: int
    document: str
    lands_today: bool
    at_seed: bool
    reachable: bool
    reachable_far: bool
    reachable_via_membership: bool


@dataclass(frozen=True, slots=True)
class Report:
    variant: str
    kinds: tuple[str, ...]
    multi_hop: int
    failing: int
    liftable: int
    at_seed_only: int
    beyond_depth: int
    membership_only: int
    verdicts: tuple[HopVerdict, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "kinds": list(self.kinds),
            "multi_hop_questions": self.multi_hop,
            "failing": self.failing,
            "liftable": self.liftable,
            "at_seed_only": self.at_seed_only,
            "beyond_depth": self.beyond_depth,
            "membership_only": self.membership_only,
        }


def probe(
    connection: sqlite3.Connection,
    manifest: Manifest,
    questions: Sequence[Question],
    *,
    documents: Mapping[str, str],
    backend: EmbeddingBackend,
    reranker: Reranker | None,
    kinds: Sequence[str],
    variant: str,
) -> Report:
    """`documents` is `active_documents(connection)`, already through `check_measurable`.

    Passed in rather than looked up per hop, so an `expect` naming nothing has exactly one place
    it can be handled — the refusal, before this runs. A lookup here that answered `""` for an
    unknown path is what made a typo indistinguishable from a genuinely unreachable document.
    """
    graph = derive(connection, manifest.kb.id, kinds=kinds)

    chunk_ids, matrix = store.load_vectors(connection, dim=manifest.embedding.dim)
    unit = unit_vectors(matrix)

    verdicts: list[HopVerdict] = []
    multi_hop = [q for q in questions if q.kind == "multi-hop"]
    for question in multi_hop:
        for index, hop in enumerate(question.hops):
            filters = question.filters if index == len(question.hops) - 1 else Filters()
            result = search(
                connection,
                manifest,
                hop.query,
                backend=backend,
                reranker=reranker,
                filters=filters,
                limit=manifest.retrieval.final_k,
            )
            lands = hop.expect in {passage.path for passage in result.passages}

            seeds = fused_candidates(
                connection, manifest, hop.query, backend=backend, filters=filters
            ).order
            similarity = _similarity(unit, chunk_ids, backend, hop.query)
            near = reachable_docs(
                graph,
                seeds,
                similarity,
                adjacent_k=manifest.retrieval.adjacent_k,
                depth=DEPTH,
            )
            far = reachable_docs(
                graph,
                seeds,
                similarity,
                adjacent_k=manifest.retrieval.adjacent_k,
                depth=FAR_DEPTH,
            )
            through_membership = reachable_docs(
                graph,
                seeds,
                similarity,
                adjacent_k=manifest.retrieval.adjacent_k,
                depth=DEPTH,
                exclude_membership=False,
            )
            wanted = documents[hop.expect]
            seed_docs = {graph.chunks[c].doc for c in seeds if c in graph.chunks}
            verdicts.append(
                HopVerdict(
                    question=question.id,
                    hop=index,
                    document=hop.expect,
                    lands_today=lands,
                    at_seed=wanted in seed_docs,
                    reachable=wanted in near or wanted in seed_docs,
                    reachable_far=wanted in far,
                    reachable_via_membership=wanted in through_membership,
                )
            )

    return _summarise(variant, tuple(kinds), multi_hop, verdicts)


def _summarise(
    variant: str,
    kinds: tuple[str, ...],
    multi_hop: Sequence[Question],
    verdicts: Sequence[HopVerdict],
) -> Report:
    by_question: dict[str, list[HopVerdict]] = {}
    for verdict in verdicts:
        by_question.setdefault(verdict.question, []).append(verdict)

    failing = 0
    liftable = 0
    at_seed_only = 0
    beyond = 0
    membership_only = 0
    for hops in by_question.values():
        missed = [hop for hop in hops if not hop.lands_today]
        if not missed:
            continue
        failing += 1
        # A question is liftable only when *every* hop it currently misses is reachable: a hit
        # requires each hop to land its own document by its own query.
        if all(hop.reachable for hop in missed):
            liftable += 1
            # Distance zero. The document is already among the fused candidates and merely ranked
            # below the cut, so the channel would have to *re-rank* it, not reach it — no edge is
            # traversed. Counted in `liftable`, because §9 says "within 2 logical hops" and zero is
            # within two, and reported separately, because a ceiling made of these says nothing
            # about whether derived structure bridges anything.
            if all(hop.at_seed for hop in missed):
                at_seed_only += 1
        elif all(hop.reachable_far for hop in missed):
            beyond += 1
        elif all(hop.reachable_via_membership for hop in missed):
            membership_only += 1
    return Report(
        variant=variant,
        kinds=kinds,
        multi_hop=len(multi_hop),
        failing=failing,
        liftable=liftable,
        at_seed_only=at_seed_only,
        beyond_depth=beyond,
        membership_only=membership_only,
        verdicts=tuple(verdicts),
    )


def _similarity(
    unit: "np.ndarray[Any, np.dtype[np.float32]]",
    chunk_ids: Sequence[int],
    backend: EmbeddingBackend,
    query: str,
) -> dict[int, float]:
    """Cosine of every stored chunk against one query — how a hub's members are ranked."""
    embedded = backend.embed([query])
    if embedded.shape[0] == 0:
        return {}
    scores = unit @ unit_vectors(embedded)[0]
    return {chunk_id: float(scores[index]) for index, chunk_id in enumerate(chunk_ids)}


# --------------------------------------------------------------------------------------------
# Fake backends, so the mechanism is testable without weights or network


class HashingBackend:
    """The same deterministic bag-of-words hash `tests/test_eval.py` uses. crc32, never `hash()`."""

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows: list[Vectors] = []
        for text in texts:
            vector_ = np.zeros(FAKE_DIM, dtype=np.float32)
            for word in text.lower().split():
                vector_[zlib.crc32(word.strip(".,:;()").encode("utf-8")) % FAKE_DIM] += 1.0
            rows.append(vector_)
        if not rows:
            return np.zeros((0, FAKE_DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "hashing", "v1", FAKE_DIM, 512)


class OverlapReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        terms = set(query.lower().split())
        return [float(len(terms & set(passage.lower().split()))) - 3.0 for passage in passages]

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "overlap-reranker", "v1", 0, 512)


def _fake_kb(destination: Path) -> Path:
    root = destination / "demo-kb"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns(".pinakes"))
    manifest_path = root / "pinakes.toml"
    text = manifest_path.read_text(encoding="utf-8")
    # The expected count is asserted, not assumed: `provider` legitimately appears twice (embedding
    # and rerank) and every other line once. A silent no-op here would leave the manifest naming
    # real weights, and the "offline" run would quietly download them.
    for old, new, occurrences in (
        ('provider = "fastembed"', 'provider = "fake"', 2),
        (
            'model    = "BAAI/bge-small-en-v1.5"',
            'model    = "hashing"\nrevision = "probe-fake-embedding-rev"',
            1,
        ),
        ("dim      = 384", f"dim      = {FAKE_DIM}", 1),
        (
            'model    = "BAAI/bge-reranker-base"',
            'model    = "overlap-reranker"\nrevision = "probe-fake-rerank-rev"',
            1,
        ),
        ('fitted_for = "BAAI/bge-reranker-base"', 'fitted_for = "overlap-reranker@v1"', 1),
    ):
        if text.count(old) != occurrences:
            raise SystemExit(f"manifest no longer contains {old!r} exactly {occurrences}x")
        text = text.replace(old, new)
    manifest_path.write_text(text, encoding="utf-8")
    sync(load(root), options=SyncOptions(), now="20260725 18:30")
    return root


# --------------------------------------------------------------------------------------------


def _tables(connection: sqlite3.Connection) -> list[str]:
    return sorted(
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    )


def _render(reports: Iterable[Report]) -> str:
    lines: list[str] = []
    for report in reports:
        lines.append(
            f"{report.variant:<18} multi-hop {report.multi_hop:>3}  failing {report.failing:>3}  "
            f"liftable {report.liftable:>3} (of which at-seed {report.at_seed_only:>3})  "
            f"beyond-{DEPTH}-hops {report.beyond_depth:>3}  "
            f"membership-only {report.membership_only:>3}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Mutually exclusive, and an argparse-level error rather than a precedence rule: `--fake`
    # measures a temporary copy of the demo KB it builds itself, so a `--kb` it accepted and
    # discarded would report one corpus's numbers under another corpus's name.
    corpus = parser.add_mutually_exclusive_group()
    corpus.add_argument(
        "--kb", type=Path, default=DEMO, help="KB root to measure (default: the demo KB)"
    )
    corpus.add_argument(
        "--fake",
        action="store_true",
        help="offline hashing backend over a temporary copy of the demo KB, for tests. "
        "Not combinable with --kb, which it would otherwise have to ignore.",
    )
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        choices=list(ALL_KINDS),
        help="derive without this edge kind — the number must move, or the probe measures nothing",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as workspace:
        if args.fake:
            register_embedding_backend("fake", lambda section, offline: HashingBackend())
            register_reranker("fake", lambda section, offline: OverlapReranker())
            root = _fake_kb(Path(workspace))
        else:
            root = args.kb
        kb_root = str(Path(root).resolve())

        manifest = load(root)
        questions_path = root / "eval" / "questions.yaml"
        questions = load_questions(questions_path)
        connection = store.connect_ro(manifest.index_path)
        try:
            documents = active_documents(connection)
            # Before the backend loads: on a real run that is a model download, and a run that is
            # going to refuse should refuse in a second rather than after it.
            check_measurable(
                questions,
                documents,
                chunked=documents_with_chunks(connection),
                selected=lambda filters, path: documents_selected_by(
                    connection, filters, path=path
                ),
                source=questions_path,
            )
            backend = load_backend(manifest.embedding)
            reranker = (
                load_reranker(manifest.rerank) if manifest.retrieval.rerank == "local" else None
            )
            before = _tables(connection)
            kept = [kind for kind in ALL_KINDS if kind not in args.drop]
            reports = [
                probe(
                    connection,
                    manifest,
                    questions,
                    documents=documents,
                    backend=backend,
                    reranker=reranker,
                    kinds=[k for k in kept if k != AUTHORED],
                    variant="without-authored",
                ),
                probe(
                    connection,
                    manifest,
                    questions,
                    documents=documents,
                    backend=backend,
                    reranker=reranker,
                    kinds=kept,
                    variant="with-authored",
                ),
            ]
            after = _tables(connection)
            # The golden set's own identity, read while the file is certainly still there:
            # `--fake` measures a copy inside a temporary directory that is gone by the time the
            # payload is printed.
            golden_set_path = str(questions_path.resolve())
            digest = hashlib.sha256(questions_path.read_bytes()).hexdigest()
            multi_hop_questions = sum(1 for q in questions if q.kind == "multi-hop")
            golden_set = {
                "path": golden_set_path,
                "sha256": digest,
                "questions": len(questions),
                "multi_hop": multi_hop_questions,
            }
            meta = store.get_meta(connection)
            schema = meta.get("schema_version", "?")
            # A corpus edited since its last sync is measured as it stood then, and
            # nothing else in the artifact would say so.
            built_at = meta.get("built_at", "?")
        finally:
            connection.close()

    # Which corpus this is *and* what produced the numbers, in both formats. Every figure here is
    # meaningless without the first, and `failing` is a function of the second: `lands` asks
    # whether a hop's document is in the top `final_k` of a pipeline whose fusion, reranking and
    # candidate widths are all per-KB manifest keys. `eval.py`'s artifact header records the same
    # set for the same reason — two artifacts from two configurations are otherwise
    # indistinguishable on inspection.
    settings = manifest.retrieval
    payload = {
        "kb_root": kb_root,
        "kb_id": manifest.kb.id,
        "fake_backend": bool(args.fake),
        "schema_version": schema,
        "index_built_at": built_at,
        "tables_before": before,
        "tables_after": after,
        # The golden set is the input every figure below is computed *from*, and it is the one a
        # refuse-edit-re-run loop changes most often: rewriting the hop queries alone moved
        # demo-kb from 9 failing / 3 liftable to 18 / 9 with every other field here identical.
        # A digest, not the questions: the artifact identifies its input, it does not copy it.
        "golden_set": golden_set,
        "embedding": {
            "provider": manifest.embedding.provider,
            "model": manifest.embedding.model,
            "dim": manifest.embedding.dim,
            # The revision pins the weights as surely as the model name does, and changing it
            # needs no re-sync — so nothing else recorded here would move with it.
            "revision": manifest.embedding.revision,
        },
        # The reranker's own model, not only the mode. `lands` is `expect in` the top `final_k`
        # *after* reranking, so a different reranker is a different measurement: swapping one fake
        # for another moved demo-kb from 9 failing / 3 liftable to 18 / 12 with every other
        # recorded field identical. `eval.py`'s header carries this block for the same reason.
        "rerank": (
            {
                "provider": manifest.rerank.provider,
                "model": manifest.rerank.model,
                "revision": manifest.rerank.revision,
            }
            if settings.rerank == "local"
            else None
        ),
        "retrieval": {
            "candidates_per_source": settings.candidates_per_source,
            "fusion": settings.fusion,
            "fusion_top_k": settings.fusion_top_k,
            "final_k": settings.final_k,
            "rerank": settings.rerank,
            "vector_tier": settings.vector_tier,
            "adjacent_k": settings.adjacent_k,
        },
        "depth": DEPTH,
        "far_depth": FAR_DEPTH,
        "dropped": sorted(set(args.drop)),
        "reports": [report.as_dict() for report in reports],
    }
    reranker_named = (
        f"{manifest.rerank.provider}/{manifest.rerank.model}"
        if settings.rerank == "local"
        else settings.rerank
    )
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"kb {kb_root}  (kb-ulid {manifest.kb.id})")
        print(
            f"golden set {golden_set_path} (sha256 {digest[:12]}, "
            f"{multi_hop_questions} multi-hop of {len(questions)})"
        )
        if args.fake:
            print("measured with --fake: a temporary copy of the demo KB, hashing backend")
        print()
        print(_render(reports))
        print(
            f"\nschema_version {schema} (index built {built_at}), embedding "
            f"{manifest.embedding.provider}/{manifest.embedding.model} dim "
            f"{manifest.embedding.dim}, final_k {settings.final_k}, rerank {reranker_named}, "
            f"adjacent_k {settings.adjacent_k}, depth {DEPTH} logical hops"
        )
        print(f"tables unchanged: {before == after}")
        if args.drop:
            print(f"derived without: {', '.join(sorted(set(args.drop)))}")
        # No threshold is printed. The number these counts are read against belongs to the
        # measurement plan for the corpus in hand, and this tool measures whichever corpus `--kb`
        # names: a hardcoded ">= 7" was a claim about one KB printed under the numbers of another.
        print(
            "\nThe precondition has two clauses, both on the *without-authored* row above: enough\n"
            "multi-hop questions failing today, and enough of those liftable. Both thresholds\n"
            "belong to this corpus's measurement plan, not to this tool. The with-authored figure\n"
            "is recorded and licenses nothing: a corpus reachable only through links its own\n"
            "author wrote cannot say whether derived structure helps. `at-seed` is the part of\n"
            "`liftable` that traverses no edge at all."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
