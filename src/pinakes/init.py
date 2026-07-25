"""`pnk init` — stamp a new KB from a template.

The whole job is to produce a directory that is already correct: a manifest whose ids are permanent,
a `docs/` to put things in, and a `.gitignore` that keeps `.pinakes/` out of the repository. That
last one matters more than it looks — publishing a KB publishes every sidecar, and the index and
ledger must never leave the machine (docs/DESIGN.md §4.7).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pinakes import template
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


def init(
    root: Path,
    *,
    name: str | None = None,
    template_name: str = template.DEFAULT_TEMPLATE,
    now: str | None = None,
) -> InitResult:
    info = template.describe(template_name)
    root = root.resolve()
    _check_target(root)

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
    gitignore = root / ".gitignore"
    gitignore.write_text(GITIGNORE, encoding="utf-8")

    created = [manifest_path, gitignore, root / "docs", *template.copy_extras(template_name, root)]
    return InitResult(root=root, kb_id=kb_id, template=info.reference, created=created)


def _check_target(root: Path) -> None:
    if (root / MANIFEST_NAME).exists():
        raise InitError(
            f"{root} is already a KB.",
            remedy="A KB's id is permanent; re-initialising would mint a new one and orphan "
            "every inbound link.",
        )
    if root.exists() and not root.is_dir():
        raise InitError(f"{root} is not a directory.", remedy="Choose another path.")
    if root.is_dir() and any(root.iterdir()):
        raise InitError(
            f"{root} is not empty.",
            remedy="Point `pnk init` at a new directory, or clear this one first.",
        )
