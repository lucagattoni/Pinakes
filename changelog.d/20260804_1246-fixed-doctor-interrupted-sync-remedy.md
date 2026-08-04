- **`pnk doctor` no longer tells an interrupted first sync to `--rebuild`.** The embedding identity
  keys are written to `meta` only after the document loop finishes, so a first sync killed mid-run
  left them entirely absent — and the model-coherence check read that the same as a genuine model
  change, reporting `FAIL` with a remedy that discards every embedding the interrupted sync already
  wrote. Absent identity keys now report their own `WARN sync completeness`, remedy `pnk sync`
  (incremental, keeps the work already done); keys present but different from the manifest still
  `FAIL model coherence` with `--rebuild`, unchanged; a partially-written `meta` — some keys present,
  some absent — still falls to the `FAIL` side, never the benign branch.
