"""The pure half of the money machinery (I6a, docs/DESIGN.md §5): estimation, per-call and
per-document reservation, and ledger-window aggregation. No I/O, no `anthropic` import — reading
`ledger.jsonl` and actually spending are I6b's job. Money is `Decimal` end to end.
"""
