### Fixed

- Two behaviours found in 0.5.0 after it was published, recorded here because they can only change
  in a later release. A sidecar carrying its own **`%YAML 1.1` directive** is still parsed at 1.1,
  so `country: NO` becomes `False` in the index and `false` on disk on any rewrite — the
  cross-document version leak was fixed before release and tested, this same-file case was not.
  And an **integral `!!float`** keeps its tag *and* gains quotes on rewrite (`f: !!float 3` →
  `f: !!float '3'`), against the note that the tag itself is not written back; the locking test
  asserts `!!int` and `!!seq` only.
