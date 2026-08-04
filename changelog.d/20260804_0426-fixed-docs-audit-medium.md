- **Six more documentation corrections from the same audit.** `CLAUDE.md` named the links-and-graph
  plan as *the* build order without saying that plan is closed — an executor doc pointing an agent
  at increments its own first line says are unbuildable. `docs/MANIFEST.md` still called traversal
  "the links release" and `docs/STATUS.md` still carried that name in two capability rows, after the
  name left the unbuilt-work table at 0.6.0; both rows also said "built" where the file's own
  preamble reserves that word for *released*. `docs/DESIGN.md`'s risk register quoted a false-abstain
  rate of 0.03 superseded on 20260801 (now 0.015, with the models and question count corrected), and
  `docs/GUIDE.md` still hedged the spend ledger as something that does not exist yet — it shipped in
  0.3.0 and `CLAUDE.md` treats it as an invariant.
