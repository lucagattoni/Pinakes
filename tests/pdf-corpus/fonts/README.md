# Embedded test font

`LiberationSans-Subset.ttf` is the corpus's only third-party binary asset. Every other fixture
byte is generated from scratch by `pdfwriter.py`/`generate.py` (rule 11/decision from
`plans/v0.2.md` I2). It exists to fix a real bug, not for visual polish: see the "Why embedded,
not base-14" note at the top of `pdfwriter.py` and `docs/RETROSPECTIVES.md` (20260728) for the
full diagnosis. Summary — the old fixtures referenced `/BaseFont /Helvetica` with no embedded
program, so every PDF reader substituted its own local Helvetica-equivalent. pypdfium2's
prebuilt binaries substitute a *different* font per platform, so the scanned stratum (which
rasterizes text through pdfium at fixture-generation time) baked in whatever glyphs the
generating machine's pdfium happened to substitute — deterministic per platform, but different
across macOS and `ubuntu-latest`, which is why CI failed identically on every run since I2 while
passing locally. Embedding the actual outlines removes the substitution step: every platform
rasterizes the same glyph data.

**Cost:** each text-layer fixture embeds its own copy of the ~10.5 KiB subset (not shared across
files), so every one of the sixteen text-layer fixtures grew by roughly that much. `test_byte_budget`
has ample headroom for this (well under half the 2 MiB corpus budget as of this fix) — noted here
so a future contributor adding many more text fixtures knows where that per-file cost comes from.

## Provenance

- Upstream: [liberation-fonts](https://github.com/liberationfonts/liberation-fonts) 2.1.5, via the
  Homebrew cask `font-liberation` (2.1.5,7261482) — `LiberationSans-Regular.ttf`.
- Chosen because it's metric-compatible with Helvetica/Arial by design (Red Hat built it as a
  drop-in substitute), so none of `generate.py`'s hand-placed `x`/`y` coordinates needed to change
  — verified: `pdfwriter.py`/`generate.py` position text by fixed coordinates and character-count
  wrapping only, never by measuring glyph widths, so the font swap has no positioning math to
  invalidate in the first place.
- License: **SIL Open Font License, Version 1.1** — see `LICENSE-OFL.txt` in this directory
  (copied verbatim from the upstream release; required alongside the font by OFL condition 2).
  OFL explicitly permits embedding and modifying (subsetting counts as a "Modified Version"); the
  Reserved Font Name "Liberation" is used only as the tail of the PDF's subset-tagged `/BaseFont`
  (`PNKSUB+LiberationSans`), the universal PDF convention for embedded subsets, not as a
  standalone product name.

## Regenerating the subset

The corpus only ever places ASCII 0x20-0x7E plus the `fi`/`fl` ligatures (`tests/pdf-corpus/
generate.py`'s `LIGATURE_FONT`) — confirmed by scanning every fixture's source text for
non-ASCII codepoints. If a future fixture needs a new character, re-run:

```console
$ uvx --from fonttools pyftsubset /path/to/LiberationSans-Regular.ttf \
    --output-file=tests/pdf-corpus/fonts/LiberationSans-Subset.ttf \
    --unicodes="20-7E,FB01,FB02" \
    --layout-features='' \
    --no-hinting \
    --desubroutinize \
    --name-IDs='*' \
    --notdef-outline \
    --recommended-glyphs
```

adding the new codepoint(s) to `--unicodes`, then update `pdfwriter.py`'s `_ASCII_WIDTHS`/
`_NAMED_GLYPH_WIDTHS` and `/FontDescriptor` constants from the regenerated subset:

```console
$ uvx --from fonttools python3 -c "
from fontTools.ttLib import TTFont
f = TTFont('tests/pdf-corpus/fonts/LiberationSans-Subset.ttf')
cmap, hmtx, upm = f.getBestCmap(), f['hmtx'], f['head'].unitsPerEm
scale = 1000.0 / upm
print([round(hmtx[cmap[cp]][0] * scale) for cp in range(0x20, 0x7F)])
"
```

Then regenerate the whole corpus (`python3 tests/pdf-corpus/generate.py`) and commit the new
fixture bytes alongside the subset.
