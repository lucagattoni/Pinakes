"""MkDocs hooks — make the site's heading anchors identical to GitHub's.

These documents are read in two places: rendered by GitHub in the repo, and rendered by MkDocs on
the docs site. Every cross-document anchor in them was written against GitHub, so the site has to
adopt GitHub's slug algorithm rather than the docs being rewritten to match the site — a rewrite
would fix the site by breaking the copy people already read.

Two slug algorithms were tried before this one and both disagree with GitHub:

* Python-Markdown's default drops the em dash *and* collapses the whitespace either side of it, so
  ``## The manifest — pinakes.toml`` becomes ``the-manifest-pinakestoml`` where GitHub keeps both
  hyphens: ``the-manifest--pinakestoml``.
* ``pymdownx.slugs.slugify`` keeps the double hyphen but strips anything angle-bracketed as an HTML
  tag, so ``# The sidecar — `<file>.pnk.yaml` `` loses the ``<file>`` entirely. GitHub slugs the
  *escaped* heading, where that code span is ``&lt;file&gt;``, and keeps ``file``.

Only the second case is left once the em dash is handled, and it is not a one-off: two headings
carry an angle-bracketed code span today and nothing stops a third. So the algorithm is matched,
not the two headings patched.

Not type-checked by pyright: its ``include`` is ``src``/``tests``/``tools`` and mkdocs is not a
project dependency — it is installed from ``requirements-docs.txt`` into an ephemeral environment.
``ruff format`` and ``ruff check`` do run over this file; ``check.sh`` passes them ``.``.
"""

import re
import unicodedata
from typing import Any

# Everything GitHub's slugger discards: any character that is not a word character (letters,
# digits, underscore), whitespace, or a hyphen. Punctuation and symbols go; `-` and `_` survive.
_DISCARDED = re.compile(r"[^\w\s-]", re.UNICODE)


def _github_slugify(text: str, separator: str) -> str:
    """GitHub's heading-anchor algorithm: strip, lowercase, drop punctuation, spaces to hyphens.

    Whitespace is *not* collapsed — that is the whole point. ``a — b`` keeps the two spaces the
    dropped em dash leaves behind and yields ``a--b``, which is what GitHub links against.
    """
    text = unicodedata.normalize("NFC", text).strip().lower()
    return _DISCARDED.sub("", text).replace(" ", separator)


def on_config(config: Any) -> Any:
    """Install the slugifier on the already-configured `toc` extension.

    Set here rather than in ``mkdocs.yml`` because a ``!!python/name:`` tag can only name a module
    on ``sys.path``, and the repo root is not on it when the ``mkdocs`` console script runs. Hooks
    are loaded by file path, so this always resolves.
    """
    config["mdx_configs"].setdefault("toc", {})["slugify"] = _github_slugify
    return config
