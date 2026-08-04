## A green `./check.sh` only proves the worktree's own venv is green (20260804 13:30)

**MEDIUM — `test_estimate_only_stamps_utc_not_local_under_a_non_utc_timezone` shipped with no
`pinakes[pdf]` skip marker, and `./check.sh` was green anyway, because this worktree had `[pdf]`
installed.** The test writes a real `baseline-1p.pdf` and calls `page_count` on it for real (its
own docstring already said so), which needs `pypdfium2`. The planner's worktree did not have the
extra installed and hit `AttributeError: module 'pypdfium2' has no attribute 'PdfDocument'` at
merge time — same commit, same script, different venv. CI's `check` job runs a three-leg matrix
over `[light]`, `[light,pdf]` and `[light,pdf,claude]` specifically because core stays torch- and
pypdfium2-free by design (`CLAUDE.md` § Tooling); this would have gone red on the `[light]` leg
*after* merge, which the merge-time worktree-mismatch is what actually caught here.

**The rule this earns:** a green `./check.sh` run proves the *worktree's own* dependency set is
green, not the matrix — `pytest` silently skips whatever the installed extras cannot exercise
rather than failing loudly, so a test that forgot its `@pytest.mark.skipif(not
pdf_extraction_runnable(), ...)` marker doesn't skip *or* fail locally when the extra happens to be
present; it just runs, passes, and says nothing about the leg where it can't. **Before landing any
test that touches a PDF fixture, the `claude` extractor, or a real embedding backend
(`sentence-transformers`/`fastembed`), check which `pdf_runnable()`/`pdf_extraction_runnable()`/
`paid_runnable()` predicate (`tests/conftest.py`) it needs and mark it — and separately, run at
least the affected file with the relevant extra uninstalled** (`uv sync --extra light --frozen`,
run, then `uv sync --extra light --extra pdf --extra claude --frozen` to restore), because that is
the only way `./check.sh` passing locally actually predicts the `[light]` CI leg rather than just
restating the worktree it ran in.
