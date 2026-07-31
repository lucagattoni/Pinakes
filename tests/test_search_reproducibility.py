"""Is the golden-set evaluation reproducible? (G1, decision 15.)

The graph release's gate is an exact per-question sign test: a handful of questions flipping decides
whether a schema bump and a new retrieval channel ship at all. That only means something if a
question flips because retrieval changed and not because the index happened to be rebuilt. This
module is where that assumption stops being an assumption.

**What was measured, 20260801 00:35, before anything was changed.** The golden set was run against
`tests/demo-kb`, a document was edited, the index re-synced incrementally, then rebuilt, then built
again from scratch; per-question outcomes were compared at each step.

| Comparison | Real `[light]` models | A 64-dimensional hashing fake |
|---|---|---|
| the same index, evaluated twice | identical | identical |
| an incremental sync vs a `--rebuild` | identical | **1 of 41 questions differed** |
| a `--rebuild` vs a from-scratch sync | identical | identical |

So the shipped pipeline was reproducible **on this corpus, with this model, by luck**:
384-dimensional cosines rarely tie exactly, and *every* tiebreak underneath them resolved to
`chunks.id` — the rowid, which `store.py`'s own schema comment says has no identity across
rebuilds. A gate resting on "the model does not usually tie" is not a gate, so ordering was made
total on `(documents.path, chunks.ordinal)` at the three sites that decide it.

**Two levels of test, because neither is sufficient alone.** The end-to-end tests state the property
G5 actually needs, over the real corpus and the committed questions — but they can only observe a
tie the corpus happens to contain, which is why the defect survived three releases until a
low-dimensional fake went looking. The site tests below them are the mutation targets: each drives
one ordering decision directly, with a corpus built so rowid order and corpus order disagree.
`docs/STATUS.md` carries the measurement; `plans/links-and-graph.md` G1 is the increment.
"""

import shutil
import sqlite3
import zlib
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest

from pinakes import store
from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.eval import Outcome, evaluate, load_questions
from pinakes.manifest import load
from pinakes.search import _hydrate, _lexical  # pyright: ignore[reportPrivateUsage]
from pinakes.sync import SyncOptions, sync

DEMO = Path(__file__).parent / "demo-kb"

#: Chosen by measurement against the pre-fix code, because the intuitive answer was wrong. "Fewer
#: dimensions, more ties" suggested eight; at eight *and* at sixteen the end-to-end tests below pass
#: against the unfixed pipeline, because the corpus collapses into too few distinct similarity
#: values for the ordering underneath to reach the top-k. Thirty-two is where the defect becomes
#: observable — the full sweep is recorded in `tools/eval_reproducibility_gate.py`, which ran it.
#:
#: The site tests further down do not depend on this: they construct exact ties directly, and each
#: is mutation-verified against the line it covers.
DIM = 32

#: Appended to one document so the incremental path has to re-chunk and re-embed it. What it says
#: does not matter: what matters is that both sides of every comparison index the *same* bytes, so
#: any difference in outcome is the index's construction and nothing else.
APPENDED = "\n\nA sentence appended so this document has to be re-chunked.\n"


class TyingBackend:
    """Deterministic and deliberately tie-heavy: integer word counts, no decay, few dimensions.

    `crc32`, never `hash()`: Python randomises `hash()` of a `str` per process unless
    `PYTHONHASHSEED` is set, and nothing here can set it — it is read before the interpreter
    starts. A fake that is not itself reproducible cannot measure reproducibility.
    """

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows: list[Vectors] = []
        for text in texts:
            vector = np.zeros(DIM, dtype=np.float32)
            for word in text.lower().split():
                vector[zlib.crc32(word.strip(".,:;()").encode("utf-8")) % DIM] += 1.0
            rows.append(vector)
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "tying", "v1", DIM, 512)


class CoarseReranker:
    """Whole-number scores, so the rerank sort ties as readily as the retrievers do."""

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        terms = set(query.lower().split())
        return [float(len(terms & set(passage.lower().split()))) - 3.0 for passage in passages]

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "coarse-reranker", "v1", 0, 512)


# --------------------------------------------------------------------------------------------
# The property: per-question outcomes over the committed golden set.
# --------------------------------------------------------------------------------------------


def _rows(outcomes: Sequence[Outcome]) -> list[tuple[str, tuple[str, ...], str, int | None, int]]:
    """Per-question, never aggregate. Two runs can score an identical `recall@k` while disagreeing
    about half the questions — and per-question movement is exactly what G5's sign test reads."""
    return [
        (o.question.question, o.retrieved, o.confidence, o.hit_rank, o.hops_followed)
        for o in outcomes
    ]


@pytest.fixture
def corpus(tmp_path: Path) -> Iterator[Path]:
    """A copy of the committed demo KB, wired to the tying fake and synced once."""
    register_embedding_backend("fake", lambda section, offline: TyingBackend())
    register_reranker("fake", lambda section, offline: CoarseReranker())

    root = tmp_path / "demo-kb"
    # Never copy `.pinakes/`: it is generated, gitignored, and on a developer machine holds an
    # index built with the real 384-dimensional model, which the store's width check refuses.
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns(".pinakes"))

    path = root / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    for before, after in (
        ('provider = "fastembed"', 'provider = "fake"'),
        ('model    = "BAAI/bge-small-en-v1.5"', 'model    = "tying"'),
        ("dim      = 384", f"dim      = {DIM}"),
        ('model    = "BAAI/bge-reranker-base"', 'model    = "coarse-reranker"'),
    ):
        assert before in text, f"the demo manifest no longer contains {before!r}"
        text = text.replace(before, after)
    path.write_text(text, encoding="utf-8")

    sync(load(root), options=SyncOptions(), now="20260801 00:30")
    yield root


def _evaluate(root: Path) -> list[Outcome]:
    manifest = load(root)
    questions = load_questions(root / "eval" / "questions.yaml")
    connection = store.connect_ro(manifest.index_path)
    try:
        _, outcomes = evaluate(
            connection, manifest, questions, backend=TyingBackend(), reranker=CoarseReranker()
        )
    finally:
        connection.close()
    return outcomes


def test_outcomes_are_identical_across_repeated_runs(corpus: Path) -> None:
    """The weakest form of the property, and the one that must hold before the others mean much."""
    assert _rows(_evaluate(corpus)) == _rows(_evaluate(corpus))


def test_outcomes_survive_an_incremental_sync_and_rebuild(corpus: Path) -> None:
    """The same corpus reached two ways must evaluate the same way (decision 15).

    Edit a document, sync incrementally, then `--rebuild`. Both indexes describe byte-identical
    sources; only their rowids differ. Before G1 this failed on one of the 41 committed questions,
    which retrieved `catalogue-hierarchy.md` from the incremental index and `funding-sources.md`
    from the rebuilt one.
    """
    edited = corpus / "docs" / "storage-environment.md"
    edited.write_text(edited.read_text(encoding="utf-8") + APPENDED, encoding="utf-8")

    sync(load(corpus), options=SyncOptions(), now="20260801 00:31")
    incremental = _rows(_evaluate(corpus))

    sync(load(corpus), options=SyncOptions(rebuild=True), now="20260801 00:32")
    rebuilt = _rows(_evaluate(corpus))

    differing = [(a, b) for a, b in zip(incremental, rebuilt, strict=True) if a != b]
    assert not differing, (
        f"{len(differing)} of {len(incremental)} questions changed outcome between an incremental "
        f"sync and a --rebuild of the same corpus. First: {differing[0]}"
    )


def test_outcomes_survive_a_sync_from_scratch(corpus: Path) -> None:
    """A rebuild and a first sync of a fresh clone are two code paths to the same index.

    `--rebuild` replaces an existing state directory; a fresh clone has none (`.pinakes/` is
    gitignored). CI takes the second path on every run and a developer takes the first, so a
    difference between them would put the machine that measured a number into the number.
    """
    edited = corpus / "docs" / "storage-environment.md"
    edited.write_text(edited.read_text(encoding="utf-8") + APPENDED, encoding="utf-8")

    sync(load(corpus), options=SyncOptions(rebuild=True), now="20260801 00:33")
    rebuilt = _rows(_evaluate(corpus))

    shutil.rmtree(corpus / ".pinakes")
    sync(load(corpus), options=SyncOptions(), now="20260801 00:34")
    assert _rows(_evaluate(corpus)) == rebuilt


def test_the_two_sync_paths_really_do_assign_different_rowids(corpus: Path) -> None:
    """The counter-test, without which the three above could pass by never being challenged.

    They test something only if an incremental sync and a `--rebuild` actually assign different
    rowids. If a later change to `sync.py` made rowids incidentally stable, those tests would go on
    passing while measuring nothing — the vacuous-gate failure this project keeps finding in its own
    gates. This fails loudly instead, and its remedy is to find a new way to perturb the index, not
    to delete it.
    """

    def chunk_ids() -> list[int]:
        connection = store.connect_ro(load(corpus).index_path)
        try:
            return [int(row["id"]) for row in connection.execute("SELECT id FROM chunks")]
        finally:
            connection.close()

    edited = corpus / "docs" / "storage-environment.md"
    edited.write_text(edited.read_text(encoding="utf-8") + APPENDED, encoding="utf-8")

    sync(load(corpus), options=SyncOptions(), now="20260801 00:35")
    incremental = chunk_ids()

    sync(load(corpus), options=SyncOptions(rebuild=True), now="20260801 00:36")
    assert chunk_ids() != incremental, (
        "an incremental sync and a --rebuild now assign identical rowids, so the reproducibility "
        "tests in this module no longer challenge anything. Perturb the index differently rather "
        "than deleting them."
    )


# --------------------------------------------------------------------------------------------
# The sites: each ordering decision, driven directly. These are the mutation targets.
# --------------------------------------------------------------------------------------------

TIED_TEXT = "quarantine humidity fixity quarantine humidity fixity"
"""Identical in both documents below, so BM25 and cosine both score them exactly equal and nothing
but the tiebreak can separate them."""


@pytest.fixture
def reversed_rowids(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """An index whose rowid order is the *reverse* of its corpus order.

    `docs/zzz.md` is written first and so takes the lower rowids. Every assertion below therefore
    distinguishes "ordered by corpus position" from "ordered by rowid" — against an index built in
    path order the two agree, and the test would pass whatever the code did.
    """
    connection = store.create(tmp_path / "index.db")
    for doc_id, path in (("D2", "docs/zzz.md"), ("D1", "docs/aaa.md")):
        connection.execute(
            "INSERT INTO documents (id, path, content_hash, mtime, source_type, title, metadata) "
            "VALUES (?, ?, 'h', 0.0, 'markdown', NULL, '{}')",
            (doc_id, path),
        )
        for ordinal in range(2):
            cursor = connection.execute(
                "INSERT INTO chunks (doc_id, ordinal, text, char_start, char_end, token_count) "
                "VALUES (?, ?, ?, 0, 10, 6)",
                (doc_id, ordinal, TIED_TEXT),
            )
            store.store_embedding(
                connection, int(cursor.lastrowid or 0), np.ones(DIM, dtype=np.float32)
            )
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _identify(connection: sqlite3.Connection) -> dict[int, tuple[str, int]]:
    return {
        int(row["id"]): (str(row["path"]), int(row["ordinal"]))
        for row in connection.execute(
            "SELECT c.id, d.path, c.ordinal FROM chunks c JOIN documents d ON d.id = c.doc_id"
        )
    }


def test_load_vectors_returns_corpus_order_not_rowid_order(
    reversed_rowids: sqlite3.Connection,
) -> None:
    """The array's row order is what breaks ties in `_vector`'s `argsort`, so it has to be stable.

    Ordered by `chunks.id` this returns `zzz` first, because `zzz` was indexed first. The rowid is
    the one thing about a chunk that a rebuild does not preserve.
    """
    chunk_ids, _ = store.load_vectors(reversed_rowids, dim=DIM)
    identity = _identify(reversed_rowids)
    assert [identity[c] for c in chunk_ids] == [
        ("docs/aaa.md", 0),
        ("docs/aaa.md", 1),
        ("docs/zzz.md", 0),
        ("docs/zzz.md", 1),
    ]


def test_the_lexical_cut_keeps_the_same_chunk_when_scores_tie(
    reversed_rowids: sqlite3.Connection,
) -> None:
    """`ORDER BY score` is not a total order, and the `LIMIT` turns that into a changed result.

    All four chunks carry identical text, so BM25 scores them identically and the limit decides
    which survive. Without the tiebreak SQLite answers in rowid order and `zzz` wins the cut.
    """
    allowed = {int(row["id"]) for row in reversed_rowids.execute("SELECT id FROM chunks")}
    identity = _identify(reversed_rowids)

    kept = _lexical(reversed_rowids, "quarantine humidity", allowed, 2)
    assert [identity[c] for c in kept] == [("docs/aaa.md", 0), ("docs/aaa.md", 1)]


def test_hydration_returns_corpus_order_whatever_order_it_is_asked_in(
    reversed_rowids: sqlite3.Connection,
) -> None:
    """`WHERE c.id IN (…)` has no inherent order, and the caller's sorts are stable.

    So this order decides every tie the fused-score and rerank sorts leave — and their `p.path`
    tiebreak cannot separate two chunks of the *same* document, which is precisely the case here.
    """
    identity = _identify(reversed_rowids)
    scrambled = sorted(identity, reverse=True)

    rows = _hydrate(reversed_rowids, scrambled)
    assert [(row.path, identity[row.id][1]) for row in rows] == [
        ("docs/aaa.md", 0),
        ("docs/aaa.md", 1),
        ("docs/zzz.md", 0),
        ("docs/zzz.md", 1),
    ]


#: Above NumPy's introsort cutover. Below roughly sixteen elements `np.argsort` runs an insertion
#: sort, which is stable whatever `kind` says — so a smaller fixture observes nothing and passes
#: against an unstable sort. The first version of the test below was written with four chunks and
#: did exactly that.
TIED_CHUNKS = 60


def _tied_index(path: Path, documents: int) -> sqlite3.Connection:
    """`documents` documents of one identically-embedded chunk each, in ascending path order."""
    connection = store.create(path)
    for index in range(documents):
        doc_id = f"D{index:03d}"
        connection.execute(
            "INSERT INTO documents (id, path, content_hash, mtime, source_type, title, metadata) "
            "VALUES (?, ?, 'h', 0.0, 'markdown', NULL, '{}')",
            (doc_id, f"docs/{index:03d}.md"),
        )
        cursor = connection.execute(
            "INSERT INTO chunks (doc_id, ordinal, text, char_start, char_end, token_count) "
            "VALUES (?, 0, ?, 0, 10, 6)",
            (doc_id, TIED_TEXT),
        )
        store.store_embedding(
            connection, int(cursor.lastrowid or 0), np.ones(DIM, dtype=np.float32)
        )
    connection.commit()
    return connection


def test_a_tied_ranking_is_unmoved_by_documents_added_elsewhere(tmp_path: Path) -> None:
    """Why the vector sort is `kind="stable"` as well as being fed a stable array.

    On a *fixed* input array NumPy's introsort is deterministic, so the stable kind changes nothing
    a repeated run can see — which is why the two halves of this fix need separate tests rather than
    one. What it does change is what happens when the array grows: quicksort partitions over the
    whole array, so adding documents reorders tied entries that neither gained nor lost anything.
    Measured directly, 20260801: over 500 random tie-heavy arrays, growing one reordered the
    original entries in 500 of 500. A stable sort cannot — ties keep the array's own order, and
    `load_vectors` makes that corpus order.

    This is the reproducibility a KB actually lives through: documents get added, and a question
    about an untouched part of the corpus should not change its answer.
    """
    from pinakes.search import _vector  # pyright: ignore[reportPrivateUsage]

    def ranking(connection: sqlite3.Connection, first: int) -> list[tuple[str, int]]:
        identity = _identify(connection)
        allowed = set(identity)
        ranked = _vector(
            connection, TyingBackend(), TIED_TEXT, allowed, dim=DIM, limit=len(identity)
        )
        return [identity[c] for c in ranked if int(identity[c][0][5:8]) < first]

    small = _tied_index(tmp_path / "small.db", TIED_CHUNKS)
    grown = _tied_index(tmp_path / "grown.db", TIED_CHUNKS + 40)
    try:
        assert ranking(grown, TIED_CHUNKS) == ranking(small, TIED_CHUNKS)
    finally:
        small.close()
        grown.close()
