"""`pnk init` — stamp a new KB from a template.

The whole job is to produce a directory that is already correct: a manifest whose ids are permanent,
a `docs/` to put things in, and a `.gitignore` that keeps `.pinakes/` out of the repository. That
last one matters more than it looks — publishing a KB publishes every sidecar, and the index and
ledger must never leave the machine (docs/DESIGN.md §4.7).
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pinakes import template
from pinakes.ci import WORKFLOW_PATH, write_workflow
from pinakes.errors import InitError
from pinakes.ids import KbId, mint_kb_id
from pinakes.manifest import MANIFEST_NAME

GITIGNORE = """\
# Generated index, spend ledger and caches. Disposable: `pnk sync --rebuild` recreates them.
# Keeping this ignored is what stops an index or a ledger ever leaving your machine.
.pinakes/
"""

DEFAULT_EMBEDDING = ("sentence-transformers", "BAAI/bge-small-en-v1.5", 384)
DEFAULT_RERANK = ("sentence-transformers", "BAAI/bge-reranker-base")


@dataclass(frozen=True, slots=True)
class InitResult:
    root: Path
    kb_id: KbId
    template: str
    created: list[Path]
    workflow: Path | None = None
    """The GitHub Actions workflow `--ci` wrote, or `None`. Returned rather than merely created so
    the CLI can say, in one line, that it forces the free extractor (§6.3)."""
    adopted: list[Path] = field(default_factory=list[Path])
    """Files `init` would have written that were already there, and were **left exactly as they
    are**. Adopting a directory that has content is the point (a repo has a `README.md` and a
    `.gitignore` before it is ever a KB), and overwriting either would be destroying the user's
    work to make room for a template's."""
    gitignore_unprotected: bool = False
    """An existing `.gitignore` that does not mention `.pinakes/`.

    Reported loudly rather than fixed: `.gitignore` is the one skipped file whose *absence of
    content* has a consequence — an index and a spend ledger that can leave the machine. Appending
    to it would be editing a file this tool does not own, so the CLI names the line to add
    instead.
    """


def init(
    root: Path,
    *,
    name: str | None = None,
    template_name: str = template.DEFAULT_TEMPLATE,
    now: str | None = None,
    ci: bool = False,
) -> InitResult:
    info = template.describe(template_name)
    root = root.resolve()
    _check_target(root, ci=ci)

    stamp = now or datetime.now().strftime("%Y%m%d %H:%M")
    kb_id = mint_kb_id()
    provider, model, dim = DEFAULT_EMBEDDING
    rerank_provider, rerank_model = DEFAULT_RERANK

    rendered = template.render_manifest(
        template_name,
        {
            "name": name or root.name,
            "kb_id": kb_id,
            "template": info.reference,
            "created": stamp,
            "embedding_provider": provider,
            "embedding_model": model,
            "embedding_dim": dim,
            "rerank_provider": rerank_provider,
            "rerank_model": rerank_model,
        },
    )

    root.mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    manifest_path = root / MANIFEST_NAME
    manifest_path.write_text(rendered, encoding="utf-8")

    adopted: list[Path] = []
    gitignore = root / ".gitignore"
    gitignore_unprotected = False
    if gitignore.exists():
        adopted.append(gitignore)
        gitignore_unprotected = ".pinakes/" not in gitignore.read_text(encoding="utf-8")
    else:
        gitignore.write_text(GITIGNORE, encoding="utf-8")

    extras, extras_adopted = template.copy_extras(template_name, root)
    adopted.extend(extras_adopted)

    created = [manifest_path, root / "docs", *extras]
    if gitignore not in adopted:
        created.insert(1, gitignore)
    workflow = write_workflow(root) if ci else None
    if workflow is not None:
        created.append(workflow)
    return InitResult(
        root=root,
        kb_id=kb_id,
        template=info.reference,
        created=created,
        workflow=workflow,
        adopted=adopted,
        gitignore_unprotected=gitignore_unprotected,
    )


def _check_target(root: Path, *, ci: bool = False) -> None:
    if (root / MANIFEST_NAME).exists():
        raise InitError(
            f"{root} is already a KB.",
            remedy="A KB's id is permanent; re-initialising would mint a new one and orphan "
            "every inbound link.",
        )
    if root.exists() and not root.is_dir():
        raise InitError(f"{root} is not a directory.", remedy="Choose another path.")
    # **No emptiness test.** It refused every real adoption — create the repo, clone it, `init`
    # inside it — because a `.git`, a `README.md` and a `pyproject.toml` are already "not empty",
    # and *"clear this one first"* is an alarming thing to read about a directory holding the
    # documents you meant to index. Hit three times independently before it was changed
    # (20260805). What replaces it is narrower and stronger: `init` never overwrites a file that
    # is already there, so there is nothing left for an emptiness test to protect.
    #
    # The accepted cost, stated when the decision was taken: a typo in the path now creates a KB
    # in a directory full of unrelated files rather than refusing. That is recoverable — delete
    # `pinakes.toml` — where overwriting a README is not.
    #
    # **`--ci` is the one file that is refused rather than adopted, and it is checked here rather
    # than where it is written.** `write_workflow` already refuses to overwrite a hand-edited
    # workflow, but it runs *after* `pinakes.toml` exists — so without this the refusal would
    # leave a half-made KB that the next `pnk init` rejects as "already a KB", with no way
    # forward but deleting a manifest the user did not ask for. Skipping it silently is not the
    # alternative: `--ci` is an explicit request, and honouring it by doing nothing is worse than
    # refusing.
    if ci and (root / WORKFLOW_PATH).exists():
        raise InitError(
            f"{root / WORKFLOW_PATH} already exists.",
            remedy="Delete it first if you want the generated workflow; it is never overwritten. "
            "Nothing has been created — re-run without `--ci` to initialise the KB and keep your "
            "workflow.",
        )
