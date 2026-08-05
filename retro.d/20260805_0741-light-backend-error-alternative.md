## The `[light]` backend error — a fixed test that only looked environment-independent (20260805 07:41)

**MEDIUM — the existing `test_a_missing_extra_names_the_install_command` was silently coupled to
which extras happen to be installed in the checkout running it, and this dev checkout already has
`fastembed` (a transitive dependency of some other extra) even without `[light]` explicitly
requested.** Once `BackendMissingError` started naming an installed alternative, that test's
`monkeypatch.setattr(builtins, "__import__", refuse)` — which only blocks `sentence_transformers` —
left `fastembed` genuinely importable, so `load_backend` picked it up as the alternative and the
old assertion (`'uv add "pinakes[st]"' in remedy`) started failing for the *right* reason: the new
code path executing, not a bug. A version of this test that had merely added the new assertions
without also forcing "nothing else is installed" would have been true by luck of this machine's
`site-packages`, not by construction, and would flip on a bare CI leg or a machine with no
`fastembed` at all. Fixed by monkeypatching `importlib.util.find_spec` directly in both the
"no alternative" and "alternative present" tests, so each names its precondition instead of
inheriting whatever the environment happens to have — the same discipline `docs/RETROSPECTIVES.md`
already names for tests that read like they exercise a real-clock or real-install branch but
route around it.

Confirmed by the mutation pass: forcing `_installed_alternative`'s `find_spec` check to always
report "installed" broke `test_a_missing_extra_names_the_install_command` specifically (asserting
`alternative is None`), and reverting `_import` to drop the detected alternative broke both
alternative-path tests specifically (asserting `alternative == FASTEMBED`) — each mutation failed
the test that names the property it broke, not an unrelated one.
