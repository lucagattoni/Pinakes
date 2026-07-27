"""The one string policy both extraction backends run — pure `str -> str`, no geometry.

Decision 15 (`plans/v0.2.md`): this used to live inside `layout.py`, which made two things false at
once. It made "the paid backend bypasses `layout.py`" untrue, since the paid backend still needed
this stage; and it left this stage's own version out of the paid fingerprint, since only
`LAYOUT_VERSION` was hashed — so a ligature or whitespace policy change would have changed the
paid backend's output while its cache and §4.4's coherence check both stayed silent.
`TEXT_POLICY_VERSION` is what closes that gap: hashed into *both* backends' fingerprint inputs (as
each backend's own increment wires it in), because this is the one stage both of them actually run.

This module imports nothing from `layout.py` and no PDF library (`test_layout_is_pure` asserts the
whole import graph, this module included) — it is a pure function of a string, nothing else.

**Length-changing, which is why offsets are computed after it, never before** (`layout.assemble`):
one ligature codepoint expands to two or three characters, NFC composes, whitespace collapses. Any
span computed against pre-normalised text is wrong past the first change, by an amount that varies
per document — and the tiling and join-identity properties alone cannot see it, since a span that
tiles the *wrong* text still tiles it exactly.
"""

import re
import unicodedata

TEXT_POLICY_VERSION = 1

# U+FB00-U+FB06: the Latin ligatures NFKD decomposes to their letter sequences (ff, fi, fl, ffi,
# ffl, st, st). NFC alone does not touch them — they are compatibility decompositions, not
# canonical ones — so they are expanded by hand before NFC runs on what remains.
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}
_LIGATURE_PATTERN = re.compile("|".join(re.escape(k) for k in _LIGATURES))

# Collapse runs of horizontal whitespace to one space, keep newlines (block/page structure), and
# drop trailing whitespace on each line — never touch a single interior space, which is content.
_HORIZONTAL_WHITESPACE_RUN = re.compile(r"[^\S\n]+")
_TRAILING_LINE_WHITESPACE = re.compile(r"[^\S\n]+\n")


def normalise(text: str) -> str:
    expanded = _LIGATURE_PATTERN.sub(lambda m: _LIGATURES[m.group(0)], text)
    composed = unicodedata.normalize("NFC", expanded)
    collapsed = _HORIZONTAL_WHITESPACE_RUN.sub(" ", composed)
    return _TRAILING_LINE_WHITESPACE.sub("\n", collapsed)
