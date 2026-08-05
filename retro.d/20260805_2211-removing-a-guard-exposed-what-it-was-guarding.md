## Removing a blanket guard exposed what it had been incidentally protecting (20260805 22:11)

**MEDIUM — and the finding came from an existing test, not from reading the diff.** `pnk init`'s
emptiness check was removed so a directory with content could be adopted. `test_ci.py` then failed:
it asserted that an existing `.github/workflows/pinakes.yml` is refused, and its evidence was the
string `"not empty"`.

The obvious read is "update the assertion". The real finding is that **the emptiness check had been
holding a second job nobody had written down.** `write_workflow` does refuse to overwrite a
hand-edited workflow — but it runs *after* `pinakes.toml` has been written. With the emptiness check
gone, that refusal would leave a half-made KB: a manifest the user never asked for, and a re-run
that now fails with *"already a KB"*, whose only way forward is deleting a file `init` created
itself.

Moved to `_check_target`, before any write, with the failure mode in the comment. The test now
asserts `"already exists"` — more precise than `"not empty"`, and it names the only thing actually
in the way.

**A second decision was refined in the same pass, and it is recorded rather than quietly taken.**
The decision as written said *"add a refusal naming any file `init` would write that already
exists"*. Implemented literally, that refuses on `README.md` and `.gitignore` — which a real
repository always has — so **adoption would still have been impossible in exactly the case the item
exists for**. The intent was "do not destroy the user's files"; the implementation honours it by
never overwriting and *reporting*, which is strictly safer than refusing and actually achieves the
goal. `--ci` is the one exception, because it is an explicit request rather than a side effect.

**Generalisable:** a coarse guard removed is not one behaviour removed. Before deleting one, ask
what else has been quietly standing behind it — and take the failing test that follows as evidence
about the system, not as a chore.
