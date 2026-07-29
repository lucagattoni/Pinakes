"""Authored links in the committed corpora stay sparse — a gate, not a convention.

**Why a gate at all.** One author writes the corpus, the links across it, and (later) the questions
that traverse them. A densely linked synthetic KB would make cross-KB traversal look easy and would
make the graph release's eval look better than any real corpus will: APPROACH §3's whole premise is
that authored links are *rare*, and a fixture that quietly violates the premise the design rests on
is worse than no fixture. So sparsity is asserted here rather than remembered.

**Why the sidecars and not the index.** This runs in `check.sh`, which never builds an index. A
committed sidecar holds exactly the forward-authored links and nothing else — a reverse-scanned row
is index state and can never appear in one — so the *links* counted here are the same population
`pnk doctor` reports to a user (L7), which is what stops the number a person reads and the number CI
enforces from drifting apart.

The *document* counts are a different matter and are only expected to agree when the index is in
step: `pnk doctor` counts indexed documents, this counts files matching `[sources] include`. They
coincide on the committed corpora and nothing enforces that they must.

**Three limits, and the third is the one that is easy to miss.**

* *Density* — the share of documents carrying any authored link at all.
* *Degree* — the most links any single document may carry. Density alone permits one hub document
  wired to everything, which is a different corpus with the same headline number.
* *At least one intra-KB link per corpus* — because a cross-KB row's `src_kb_id` is foreign and
  resolves to no local node, so a corpus whose authored links are *all* cross-KB contributes no
  channel edges at all. The graph release's anti-circularity guard compares the derived edge set
  with and without authored edges; against such a corpus the two sets are identical, both runs
  return the same p-value, and the guard passes while discriminating nothing.

Run it over any number of KB roots; with none it checks the two committed corpora.
"""

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = (REPO / "tests/demo-kb", REPO / "tests/partner-kb")

MAX_DENSITY = 0.35
MAX_DEGREE = 4

SIDECAR_SUFFIX = ".pnk.yaml"
SCHEME = "pnk://"


@dataclass(frozen=True, slots=True)
class Census:
    kb: str
    documents: int
    linked: int
    degrees: dict[str, int]
    intra: int
    cross: int
    relations: Counter[str]

    @property
    def density(self) -> float:
        return self.linked / self.documents if self.documents else 0.0

    @property
    def worst(self) -> tuple[str, int]:
        if not self.degrees:
            return ("—", 0)
        return max(self.degrees.items(), key=lambda item: (item[1], item[0]))


def manifest_facts(root: Path) -> tuple[str, list[str], list[str]]:
    """`([kb] id, [sources] roots, [sources] include)`, read without `pinakes.manifest`.

    `tomllib` is stdlib. Going through the product's loader would mean a manifest change that
    breaks loading also takes the sparsity gate down with it, and this gate should still be able
    to report then.
    """
    import tomllib

    with (root / "pinakes.toml").open("rb") as handle:
        data = tomllib.load(handle)

    def table(name: str) -> dict[str, object]:
        raw: object = data.get(name)
        if not isinstance(raw, dict):
            raise SystemExit(f"{root}/pinakes.toml has no [{name}] table")
        return cast(dict[str, object], raw)

    identifier = table("kb").get("id")
    if not isinstance(identifier, str):
        raise SystemExit(f"{root}/pinakes.toml has no [kb] id")

    sources = table("sources")

    def strings(key: str, default: list[str]) -> list[str]:
        raw = sources.get(key)
        if raw is None:
            return default
        if not isinstance(raw, list):
            raise SystemExit(f"{root}/pinakes.toml: [sources] {key} is not a list")
        values = [value for value in cast(list[object], raw) if isinstance(value, str)]
        return values or default

    return identifier, strings("roots", ["docs/"]), strings("include", ["**/*.md"])


def target_kb(uri: str, *, owner: str) -> str:
    """The KB a link points at.

    `pnk://self/<doc>` is the owning KB, resolved exactly as `sidecar.read` resolves it — which is
    what keeps this count and `pnk doctor`'s the same number.
    """
    if not uri.startswith(SCHEME):
        raise SystemExit(f"link target is not a pnk:// URI: {uri!r}")
    rest = uri[len(SCHEME) :]
    head, _, _ = rest.partition("/")
    return owner if head.lower() == "self" else head


def documents_of(root: Path, roots: list[str], include: list[str]) -> list[Path]:
    """The KB's *documents*, from `[sources]` — not its sidecars.

    Counting sidecars instead was wrong in both directions and neither was theoretical: an
    orphaned sidecar (which `pnk sync` deliberately keeps) inflated the denominator and diluted
    density — 8 of 10 real documents linked read as 27% — while a document whose sidecar had not
    been minted yet was invisible, so the gate reported nonsense on any KB where sync had not run.
    """
    found: set[Path] = set()
    for name in roots:
        base = (root / name).resolve()
        if not base.is_dir():
            continue
        for pattern in include:
            for candidate in base.glob(pattern):
                if candidate.is_file() and not candidate.name.endswith(SIDECAR_SUFFIX):
                    found.add(candidate)
    return sorted(found)


def census(root: Path) -> Census:
    owner, roots, include = manifest_facts(root)
    degrees: dict[str, int] = {}
    relations: Counter[str] = Counter()
    intra = cross = 0

    files = documents_of(root, roots, include)
    for document in files:
        path = document.with_name(document.name + SIDECAR_SUFFIX)
        if not path.is_file():
            continue
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise SystemExit(f"{path}: not a mapping")
        # One cast at the boundary. `yaml.safe_load` returns `Any`, and letting that leak makes
        # every later `.get` unknown to the strict checker — which is how a small script ends up
        # littered with per-line suppressions that hide the one real mistake among them.
        body = cast(dict[str, object], loaded)
        raw = body.get("links")
        if raw is None:
            continue
        if not isinstance(raw, list):
            raise SystemExit(f"{path}: `links` is not a list")
        entries = cast(list[object], raw)
        if not entries:
            continue
        # Keyed by path relative to the KB root, never by basename. Two documents sharing a
        # filename in different folders collapsed to one key and the later one *overwrote* the
        # earlier — so a degree-6 hub sat behind `docs/aaa/policy.md` while the gate reported
        # "worst degree 1 (policy.md)" and exited 0. The degree cap exists separately from density
        # precisely to catch that shape, and a basename key is the one way it cannot.
        name = document.relative_to(root).as_posix()
        degrees[name] = len(entries)
        for item in entries:
            if not isinstance(item, dict):
                raise SystemExit(f"{path}: a `links` entry is not a mapping")
            entry = cast(dict[str, object], item)
            to = entry.get("to")
            rel = entry.get("rel")
            if not isinstance(to, str) or not isinstance(rel, str):
                raise SystemExit(f"{path}: a `links` entry needs a string `to` and `rel`")
            relations[rel] += 1
            if target_kb(to, owner=owner) == owner:
                intra += 1
            else:
                cross += 1

    return Census(
        kb=root.name,
        documents=len(files),
        linked=len(degrees),
        degrees=degrees,
        intra=intra,
        cross=cross,
        relations=relations,
    )


def failures(report: Census, *, max_density: float, max_degree: int) -> list[str]:
    problems: list[str] = []
    if report.density > max_density:
        problems.append(
            f"{report.kb}: {report.linked}/{report.documents} documents carry authored links "
            f"({report.density:.0%}), above the {max_density:.0%} cap"
        )
    # Every offender, not just the worst: reporting one at a time makes a corpus with three hubs
    # take three CI runs to fix, and each run looks like a new failure.
    over = sorted(
        ((name, degree) for name, degree in report.degrees.items() if degree > max_degree),
        key=lambda item: (-item[1], item[0]),
    )
    for name, degree in over:
        problems.append(
            f"{report.kb}: {name} carries {degree} authored links, above the "
            f"degree cap of {max_degree} — density alone permits one hub wired to everything"
        )
    # `cross > 0` as well as `intra == 0`: a corpus with *no* authored links is not one whose links
    # are all cross-KB, and conflating them failed every KB from the day it was created — including
    # the demo corpus as it stood before this increment. Sparsity is a ceiling; the floor is
    # `pnk doctor`'s nudge (L7), which is advice rather than a gate.
    if report.intra == 0 and report.cross > 0:
        problems.append(
            f"{report.kb}: every authored link is cross-KB, so the corpus contributes no "
            f"same-KB edges and the graph release's with/without-authored guard cannot discriminate"
        )
    return problems


def render(report: Census, *, max_density: float, max_degree: int) -> str:
    """The caps in force are passed in, never read from the module constants.

    Printing `MAX_DENSITY` while `--max-density` was in effect made the line say "27% of the 35%
    cap" and then fail the corpus in the same breath — a report that contradicts its own verdict.
    """
    document, degree = report.worst
    histogram = ", ".join(f"{rel} {count}" for rel, count in sorted(report.relations.items()))
    return (
        f"{report.kb}: {report.documents} documents, {report.linked} linked "
        f"({report.density:.0%} of the {max_density:.0%} cap), "
        f"{report.intra} intra-KB + {report.cross} cross-KB, "
        f"worst degree {degree}/{max_degree} ({document}), relations: {histogram or 'none'}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, help="KB roots (default: both corpora)")
    parser.add_argument("--max-density", type=float, default=MAX_DENSITY)
    parser.add_argument("--max-degree", type=int, default=MAX_DEGREE)
    args = parser.parse_args(argv)

    roots: list[Path] = list(args.roots) or list(DEFAULT_ROOTS)
    problems: list[str] = []
    for root in roots:
        if not (root / "pinakes.toml").is_file():
            print(f"link-density: {root} is not a KB root", file=sys.stderr)
            return 1
        report = census(root)
        print(
            f"link-density: "
            f"{render(report, max_density=args.max_density, max_degree=args.max_degree)}"
        )
        problems.extend(failures(report, max_density=args.max_density, max_degree=args.max_degree))

    for problem in problems:
        print(f"link-density: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
