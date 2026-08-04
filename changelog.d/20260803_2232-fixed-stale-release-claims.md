- **Seven stale "unreleased" claims corrected across the docs, and the release procedure now
  catches the class.** The paid Claude-vision extractor shipped in 0.3.0, but `docs/GUIDE.md` and
  `docs/MANIFEST.md` still said "in no release yet" — the troubleshooting table sent a scanned-PDF
  user to a release it claimed did not exist, and now gives the remedy (`pinakes[pdf,claude]`,
  `--extract=claude-vision`). G4 (0.6.0) and I8/I9 (0.4.0) were still "unreleased" in
  `docs/KB-UPDATES.md` and `docs/STATUS.md`'s ledger; STATUS's header said 0.4.1 with 0.7.1 in its
  own tables. `docs/RELEASING.md`'s sweep now names the header line and ends with a grep for
  release-falsified claims, because a checklist of sections missed this class four releases running.
