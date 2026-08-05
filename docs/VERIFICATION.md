# Verification — every promise, and the test that holds it

`plans/20260727_1543-v0.2.md` ends with a table headed *"Every row carries an increment number and a test path — a
promise in a section with no owner is a wish"*. **Sixty-one of its ninety-eight test paths did not
resolve.** Not because the properties went untested — almost all of them are tested, usually under a
better name than the plan guessed — but because the plan wrote its test names *before* the tests
existed, and implementation renamed them. A verification table whose paths cannot be resolved
verifies nothing; it is the wish it warned about, wearing the table's clothes.

So the plan keeps its predictions, as the historical record of what was intended, and **this file is
the resolved mapping**: what must be true, and the test that actually holds it, in the tree as it
stands. [`tests/test_verification.py`](https://github.com/lucagattoni/pinakes/blob/main/tests/test_verification.py) asserts every test named below
exists — so this table can go stale exactly once, in the commit that breaks it, and not silently.

A row saying **none** is a promise with no test. There are none today; if you add a row, add its
test, or write **none** and say why in the same commit.

**Two limits, stated so nobody reads this as more than it is.**

* **The gate checks that each named test *exists*, not that it asserts the property beside it.** No
  test can check that. The mapping below was resolved by reading the tests where the name did not
  make it obvious — and the I9 review still found one row mapped from a name alone, which was
  wrong (the completeness audit's). Treat a row as a strong pointer, not a proof.
* **The scope is `plans/20260727_1543-v0.2.md`'s promises**, which is what the table this replaces covered. v0.1's
  own modules — `test_chunk.py`, `test_ids.py`, `test_init.py`, `test_lock.py`, `test_pairing.py`,
  `test_uri.py`, `test_embed.py`, `test_eval.py` — are not represented here and are not unowned;
  they simply predate the table. Adding them is worth doing and nobody has.

## Packaging and the extractor registry

| What must be true | Increment | Where it is checked |
|---|---|---|
| no extractor library enters `[project.dependencies]` | I1 | `check.sh` gate + `tests/test_packaging.py::test_extractors_stay_extras` |
| `pinakes[claude]` cannot be installed without `[pdf]` | I1 | `tests/test_packaging.py::test_claude_extra_requires_pdf_extra` |
| Pillow stays dev-only — never core, never an extra | I2 | `tests/test_packaging.py::test_pillow_is_dev_only_never_core_and_never_an_extra` |
| a core-only install fails naming the extra | I1 | `tests/test_extract.py::test_a_missing_extra_names_the_install_command` |
| every backend's missing-extra error names its own extra | I1 | `tests/test_extract.py::test_backend_requirement_names_the_extra_a_user_is_told_to_install` |
| an unknown backend is rejected from the manifest | I1 | `tests/test_manifest.py::test_extraction_backend_must_be_registered` |
| …and from `--extract`, without importing anything | I1 | `tests/test_cli.py::test_unknown_extract_flag_is_rejected` |
| availability is answered without executing the backend | I1 | `tests/test_extract.py::test_is_backend_installed_locates_without_executing` |
| one unreadable PDF does not block the corpus | I1 | `tests/test_sync.py::test_a_pdf_fails_at_extraction_but_does_not_block_the_rest` |
| a sidecar that will not parse is never overwritten | fix | `tests/test_sync.py::test_an_unreadable_sidecar_is_never_overwritten` |
| ...and does not stop the other documents | fix | `tests/test_sync.py::test_an_unreadable_sidecar_does_not_stop_the_other_documents` |
| ...on the pre-commit path either | fix | `tests/test_sync.py::test_sidecars_only_refuses_the_unreadable_one_and_mints_the_rest` |
| ...and `--index-only` indexes no divergent id | fix | `tests/test_sync.py::test_index_only_neither_writes_nor_indexes_a_divergent_id` |
| minting refuses where a file already exists | fix | `tests/test_sidecar.py::test_create_refuses_to_overwrite_an_existing_sidecar` |
| ...while `write` still overwrites, for I5's merge | fix | `tests/test_sidecar.py::test_write_still_overwrites_because_a_merge_needs_it` |
| a broken sidecar on an indexed document does not abort the sync | fix | `tests/test_sync.py::test_breaking_a_sidecar_after_indexing_does_not_abort_the_whole_sync` |
| a rebuild does not overwrite one either | fix | `tests/test_sync.py::test_a_rebuild_does_not_overwrite_an_unreadable_sidecar` |
| the refusal names the parse error, not just the existence | fix | `tests/test_sync.py::test_the_refusal_names_the_parse_error_not_merely_the_existence` |
| a sidecar that arrives after the walk asks for a rerun | fix | `tests/test_sync.py::test_a_sidecar_that_appears_after_the_walk_asks_for_a_rerun` |
| a write failure is recorded, never raised, on the pre-commit path | fix | `tests/test_sync.py::test_a_write_failure_on_the_pre_commit_path_is_recorded_not_raised` |
| minting refuses a dangling symlink too | fix | `tests/test_sidecar.py::test_create_refuses_a_dangling_symlink_too` |

## The links release: the corpora, the density gate and reverse-scan (L1–L2)

Authored links are sparse by design, so the corpora are gated on it; and a reverse scan reads
someone else's KB, so every failure mode has to be named rather than swallowed.

| What must be true | Increment | Where it is checked |
|---|---|---|
| both committed corpora load and name each other by ULID | L1 | `tests/test_partner_kb.py::test_both_corpora_load_and_validate` |
| every sidecar ULID is well-formed and unique across both KBs | L1 | `tests/test_partner_kb.py::test_every_sidecar_ulid_is_wellformed_and_unique_across_both_kbs` |
| every authored link target is a resolvable URI | L1 | `tests/test_partner_kb.py::test_every_link_target_is_a_resolvable_uri` |
| authored links are sparse (the density cap) | L1 | `tests/test_partner_kb.py::test_a_corpus_over_the_density_cap_fails_the_gate` |
| ...and the cap's boundary passes from the other side | L1 | `tests/test_partner_kb.py::test_a_corpus_exactly_at_the_cap_passes` |
| no single hub document, whatever the density | L1 | `tests/test_partner_kb.py::test_a_corpus_with_a_hub_document_fails_the_gate` |
| a corpus linked only outward is refused | L1 | `tests/test_partner_kb.py::test_a_corpus_whose_links_are_all_cross_kb_fails_the_gate` |
| ...but a corpus with no links at all is not | L1 | `tests/test_partner_kb.py::test_a_corpus_with_no_links_at_all_passes` |
| the gate runs without an index, and builds none | L1 | `tests/test_partner_kb.py::test_the_gate_runs_without_an_index` |
| the gate's count is the population `pnk doctor` reports | L1 | `tests/test_partner_kb.py::test_the_committed_split_is_pinned` |
| the corpus carries L2's `self`-form fixture | L1 | `tests/test_partner_kb.py::test_the_partner_corpus_carries_a_self_form_link` |
| the corpus carries L7's dangling-target fixture | L1 | `tests/test_partner_kb.py::test_the_partner_corpus_carries_a_target_in_a_kb_nothing_provides` |
| a hub behind a shared filename still fails the gate | L1 | `tests/test_partner_kb.py::test_a_hub_hiding_behind_a_shared_filename_still_fails` |
| an orphaned sidecar does not dilute density | L1 | `tests/test_partner_kb.py::test_an_orphaned_sidecar_does_not_dilute_the_density` |
| a document with no sidecar is still counted | L1 | `tests/test_partner_kb.py::test_a_document_without_a_sidecar_is_still_counted` |
| both corpora parse through the product's own sidecar reader | L1 | `tests/test_partner_kb.py::test_both_corpora_survive_the_products_own_sidecar_reader` |
| the gate's link count agrees with the product's | L1 | `tests/test_partner_kb.py::test_the_gate_and_the_product_agree_on_the_link_count` |
| `check.sh` still invokes the link-density gate | L1 | `tests/test_check_script.py::test_check_sh_declares_the_link_density_gate` |
| CI runs it and proves it can fail | L1 | `tests/test_check_script.py::test_ci_runs_the_link_density_gate_and_proves_it_can_fail` |
| inbound rows carry the other KB's id as source | L2 | `tests/test_sync_links.py::test_inbound_rows_carry_the_other_kbs_id_as_source` |
| a partner's `self` link resolves to the partner, not to us | L2 | `tests/test_sync_links.py::test_a_self_link_in_a_partner_sidecar_resolves_to_the_partner_not_the_local_kb` |
| only links targeting this KB are recorded | L2 | `tests/test_sync_links.py::test_a_partner_link_to_a_third_kb_is_not_recorded` |
| `kb_refs` records alias, path and scan time | L2 | `tests/test_sync_links.py::test_kb_refs_records_alias_path_and_scan_time` |
| the scan reads sidecars, never the partner's index | L2 | `tests/test_sync_links.py::test_the_scan_reads_sidecars_not_the_partners_index` |
| a reverse row never overwrites an authored one | L2 | `tests/test_sync_links.py::test_a_reverse_row_never_overwrites_an_authored_row` |
| an authored row reclaims a tuple a reverse scan wrote | L2 | `tests/test_sync_links.py::test_an_authored_row_reclaims_a_tuple_a_reverse_scan_already_wrote` |
| reverse rows never enter the authored count | L2 | `tests/test_sync_links.py::test_reverse_rows_never_enter_the_authored_count` |
| a removed link removes its reverse row | L2 | `tests/test_sync_links.py::test_a_removed_link_removes_its_reverse_row` |
| the delete is scoped to the scanned KB | L2 | `tests/test_sync_links.py::test_the_delete_is_scoped_to_the_scanned_kb` |
| a delisted KB's rows and `kb_refs` entry go with it | L2 | `tests/test_sync_links.py::test_delisting_a_linked_kb_removes_its_reverse_rows_and_kb_ref` |
| a failed scan deletes nothing | L2 | `tests/test_sync_links.py::test_a_failed_scan_leaves_the_previous_reverse_rows_in_place` |
| ...and does not stamp `last_scan` | L2 | `tests/test_sync_links.py::test_a_failed_scan_does_not_stamp_last_scan` |
| a mismatched KB id writes nothing at all | L2 | `tests/test_sync_links.py::test_a_mismatched_kb_id_writes_nothing_at_all` |
| each failure mode is recorded with its reason | L2 | `tests/test_sync_links.py::test_each_failure_mode_is_recorded_with_its_reason` |
| an unreachable linked KB does not fail the sync | L2 | `tests/test_sync_links.py::test_an_unreachable_linked_kb_does_not_fail_the_sync` |
| a fresh `kb_refs` entry skips the walk | L2 | `tests/test_sync_links.py::test_a_fresh_kb_refs_entry_skips_the_walk` |
| an expired window forces a rescan | L2 | `tests/test_sync_links.py::test_an_expired_ttl_forces_a_rescan` |
| `--scan-links` forces a rescan | L2 | `tests/test_sync_links.py::test_scan_links_forces_a_rescan` |
| the window never reads uncertainty as fresh | L2 | `tests/test_sync_links.py::test_the_ttl_never_reads_uncertainty_as_fresh` |
| `--sidecars-only` does not scan | L2 | `tests/test_sync_links.py::test_sidecars_only_does_not_scan` |
| ...and refuses `--scan-links` | L2 | `tests/test_sync_links.py::test_sidecars_only_with_scan_links_is_refused` |
| a rebuild reconstructs reverse rows from sidecars alone | L2 | `tests/test_sync_links.py::test_rebuild_reconstructs_reverse_rows_from_sidecars_alone` |
| the partner is never locked, even mid-sync | L2 | `tests/test_sync_links.py::test_the_partner_is_never_locked` |
| a vanished partner root deletes nothing | L2 | `tests/test_sync_links.py::test_a_vanished_partner_root_deletes_nothing` |
| a partner's `exclude` is honoured | L2 | `tests/test_sync_links.py::test_a_partners_exclude_is_honoured` |
| a partner's bad `include` cannot crash the sync | L2 | `tests/test_sync_links.py::test_a_partners_bad_include_pattern_does_not_crash_the_sync` |
| a partner root outside its own KB is refused | L2 | `tests/test_sync_links.py::test_a_partner_root_outside_its_own_kb_is_refused` |
| a failed local run does not blame the partner | L2 | `tests/test_sync_links.py::test_a_failed_local_run_does_not_blame_the_partner` |

## The links release: traversal, `pnk links` and `pinakes_links` (L3–L5)

Depth in **logical hops**, the double cap, `frontier` and `unresolved` — the properties a
caller cannot check for itself, on both the CLI and the MCP surface.

| What must be true | Increment | Where it is checked |
|---|---|---|
| depth counts one hop per candidate | L3 | `tests/test_traverse.py::test_depth_counts_one_hop_per_candidate` |
| depth is clamped server-side | L3 | `tests/test_traverse.py::test_depth_is_clamped_to_the_server_maximum` |
| fan-out keeps the highest-ranked, not the first k | L3 | `tests/test_traverse.py::test_fanout_keeps_the_highest_ranked_neighbours_not_the_first_k` |
| fan-out is clamped server-side | L3 | `tests/test_traverse.py::test_fanout_is_clamped_to_the_server_maximum` |
| ranking without a query uses edge weight | L3 | `tests/test_traverse.py::test_ranking_without_a_query_uses_edge_weight_then_distance` |
| ranking with a query uses provider similarity | L3 | `tests/test_traverse.py::test_ranking_with_a_query_uses_provider_supplied_similarity` |
| a capped answer is reproducible | L3 | `tests/test_traverse.py::test_ranking_is_totally_ordered_so_a_capped_answer_is_reproducible` |
| the frontier carries why each neighbour was not expanded | L3 | `tests/test_traverse.py::test_a_frontier_entry_carries_the_reason_it_was_not_expanded` |
| terminal outranks fanout when both apply | L3 | `tests/test_traverse.py::test_terminal_outranks_fanout_when_both_apply` |
| a cross-KB neighbour is terminal at every depth | L3 | `tests/test_traverse.py::test_a_cross_kb_neighbour_is_frontier_terminal_at_every_depth` |
| ...and is never asked for its own neighbours | L3 | `tests/test_traverse.py::test_a_terminal_neighbour_is_never_asked_for_its_own_neighbours` |
| a hub is expanded once globally | L3 | `tests/test_traverse.py::test_a_hub_is_expanded_once_globally` |
| a cycle terminates | L3 | `tests/test_traverse.py::test_a_cycle_terminates` |
| the token budget is independent of the row cap | L3 | `tests/test_traverse.py::test_the_token_budget_sets_truncated_independently_of_the_row_cap` |
| an answer within both caps reports neither | L3 | `tests/test_traverse.py::test_an_answer_within_both_caps_reports_neither` |
| unresolved targets survive to the caller | L3 | `tests/test_traverse.py::test_unresolved_targets_survive_to_the_caller` |
| `check.sh` still invokes the traversal-cap gate | L3 | `tests/test_check_script.py::test_check_sh_declares_the_traversal_cap_gate` |
| CI runs it too | L3 | `tests/test_check_script.py::test_ci_runs_the_traversal_cap_gate` |
| every neighbour is a document | L4 | `tests/test_cli_links.py::test_every_neighbour_is_a_document` |
| a cross-KB neighbour is terminal | L4 | `tests/test_cli_links.py::test_a_cross_kb_neighbour_is_marked_terminal` |
| ...carries its KB ULID and no title | L4 | `tests/test_cli_links.py::test_a_cross_kb_neighbour_carries_its_kb_ulid_and_no_title` |
| a same-KB neighbour carries its title | L4 | `tests/test_cli_links.py::test_a_same_kb_neighbour_carries_its_title` |
| `kb_id` is a ULID, never a name | L4 | `tests/test_cli_links.py::test_kb_id_is_a_ulid_not_a_name` |
| the JSON shape is pinned | L4 | `tests/test_cli_links.py::test_json_output_shape_is_pinned` |
| depth beyond the cap is served at the cap | L4 | `tests/test_cli_links.py::test_depth_beyond_the_cap_is_served_at_the_cap` |
| ...and depth is honoured, not merely capped | L4 | `tests/test_cli_links.py::test_depth_is_honoured_not_merely_capped` |
| one query per hop, never a recursive CTE | L4 | `tests/test_cli_links.py::test_one_query_per_hop_not_a_recursive_cte` |
| a missing local target is unresolved, never a neighbour | L4 | `tests/test_cli_links.py::test_a_local_link_to_a_missing_document_is_unresolved_not_dropped` |
| a cross-KB target is never called unresolved | L4 | `tests/test_cli_links.py::test_a_cross_kb_target_is_never_called_unresolved` |
| the frontier is capped like the rest of the response | L3 | `tests/test_traverse.py::test_the_frontier_is_capped_like_the_rest_of_the_response` |
| a frontier entry is retracted when the node is reached later | L3 | `tests/test_traverse.py::test_a_frontier_entry_is_retracted_when_the_node_is_reached_later` |
| ...but `terminal` and `depth` describe accepted nodes and stay | L3 | `tests/test_traverse.py::test_an_accepted_node_may_still_be_on_the_frontier_for_terminal_or_depth` |
| the response caps are clamped server-side too | L3 | `tests/test_traverse.py::test_the_response_caps_are_clamped_server_side_too` |
| terminal outranks the response caps, not only fanout | L3 | `tests/test_traverse.py::test_terminal_outranks_the_response_caps_as_well_as_fanout` |
| two relations to one target are two rows | L3 | `tests/test_traverse.py::test_two_relations_to_one_target_are_two_rows` |
| ...while the node is still expanded once | L3 | `tests/test_traverse.py::test_a_node_reachable_two_ways_is_still_expanded_once` |
| the row cap keeps the highest-ranked across the whole hop | L3 | `tests/test_traverse.py::test_the_row_cap_keeps_the_highest_ranked_across_the_whole_hop` |
| a score says whether it came from the query | L3 | `tests/test_traverse.py::test_a_score_says_whether_it_came_from_the_query` |
| `adjacent_k` defaults to 8 | L3 | `tests/test_manifest.py::test_adjacent_k_defaults_to_eight` |
| ...and above the cap is refused, not clamped | L3 | `tests/test_manifest.py::test_adjacent_k_above_the_server_cap_is_refused_not_clamped` |
| `pinakes_links` returns `score` and `frontier` on every return | L5 | `tests/test_serve.py::test_pinakes_links_returns_score_and_frontier_on_every_return` |
| ...and `confidence: unknown` with a query and without | L5 | `tests/test_serve.py::test_pinakes_links_reports_unknown_confidence_with_and_without_a_query` |
| a neighbour outside the served KBs carries its `kb_id` and a reason | L5 | `tests/test_serve.py::test_a_neighbour_outside_the_served_kbs_returns_its_kb_id_and_a_reason` |
| a neighbour it returns is fetchable by `pinakes_get` | L5 | `tests/test_serve.py::test_pinakes_get_resolves_a_neighbour_returned_by_pinakes_links` |
| depth is capped at the documented 3 over MCP too | L5 | `tests/test_serve.py::test_depth_is_capped_server_side` |
| a cross-KB neighbour is terminal over MCP too | L5 | `tests/test_serve.py::test_a_cross_kb_neighbour_is_terminal_over_mcp_too` |
| an unknown document is refused with a remedy | L5 | `tests/test_serve.py::test_an_unknown_document_is_refused_with_a_remedy` |
| the `pinakes_search` and `pinakes_get` payloads are unchanged | L5 | `tests/test_serve.py::test_pinakes_search_and_get_payloads_are_unchanged` |
| the tool is namespaced alongside the other three | L5 | `tests/test_serve.py::test_the_tools_are_namespaced` |
| the free-path gate **invokes** it, never only lists it | L5 | `tests/test_paid_path.py::test_the_free_path_never_imports_the_paid_client` (through `tests/free_path_run.py`) |
| `direction` is per relation, not per node | L5 | `tests/test_graph_present.py::test_direction_is_per_relation_not_per_node` |
| ...and one relation written from both ends is `both` | L5 | `tests/test_graph_present.py::test_one_relation_written_from_both_ends_is_both` |
| an unknown `direction` is refused, not answered emptily | L5 | `tests/test_graph_present.py::test_an_unknown_direction_is_refused_rather_than_answered_emptily` |
| `scored_by_query` says which scale `score` is on | L5 | `tests/test_graph_present.py::test_scored_by_query_says_which_scale_the_score_is_on` |
| a score is rounded to four places | L5 | `tests/test_graph_present.py::test_a_score_is_rounded_even_when_the_raw_value_is_long` |
| ...over a real KB too | L5 | `tests/test_graph_present.py::test_a_score_is_rounded_to_four_places` |
| `truncated` reports the caps that bit | L5 | `tests/test_graph_present.py::test_truncated_reports_the_caps_that_bit` |
| a frontier entry carries the distance it was found at | L5 | `tests/test_graph_present.py::test_a_frontier_entry_carries_the_distance_it_was_found_at` |
| every direction has its own arrow, the unreachable one included | L5 | `tests/test_graph_present.py::test_every_direction_has_its_own_arrow_including_the_one_no_fixture_can_reach` |
| the CLI says *why* a walk returned nothing | L5 | `tests/test_cli_links.py::test_the_cli_says_so_when_every_link_dangles` |
| ...filter before dangling, with both true at once (CLI) | L5 | `tests/test_cli_links.py::test_a_filtered_walk_reports_the_filter_before_the_dangling_links` |
| ...and over MCP | L5 | `tests/test_serve.py::test_a_filtered_walk_reports_the_filter_before_the_dangling_links` |
| a query reaches the ranking on both surfaces | L5 | `tests/test_graph_present.py::test_a_query_reaches_the_ranking_on_both_surfaces` |
| a document whose links all dangle is not called unlinked | L5 | `tests/test_serve.py::test_a_document_whose_links_all_dangle_is_not_called_unlinked` |
| a direction does not change with `depth` | L5 | `tests/test_graph_present.py::test_a_direction_does_not_change_with_depth` |
| `present`'s key constants match the rows | L5 | `tests/test_graph_present.py::test_the_projections_key_sets_match_what_the_rows_carry` |
| every argument that can empty an answer is named | L5 | `tests/test_graph_present.py::test_is_filtered_names_every_argument_that_can_empty_an_answer` |
| each direction gets its own arrow in the human output | L5 | `tests/test_cli_links.py::test_the_human_output_names_each_direction_with_its_own_arrow` |
| a local neighbour carries a title, a cross-KB one does not | L5 | `tests/test_graph_present.py::test_a_local_neighbour_carries_a_title_and_a_cross_kb_one_does_not` |
| an unresolved row survives and carries the local `kb_id` | L5 | `tests/test_graph_present.py::test_an_unresolved_row_survives_and_carries_the_local_kb_id` |
| every row shape is pinned by literal | L5 | `tests/test_graph_present.py::test_every_row_shape_is_pinned_by_literal` |
| the CLI and MCP surfaces project the same keys | L5 | `tests/test_graph_present.py::test_the_two_surfaces_project_the_same_keys` |
| an empty answer says whether the arguments emptied it | L5 | `tests/test_serve.py::test_an_empty_answer_says_whether_the_arguments_emptied_it` |
| a neighbour in a second served KB says which KB to fetch it from | L5 | `tests/test_serve.py::test_a_neighbour_in_a_second_served_kb_says_which_kb_to_fetch_it_from` |
| an alias is resolved to a ULID before it reaches disk | L6 | `tests/test_cli_link.py::test_an_alias_is_resolved_to_a_ulid_on_write` |
| ...and so is `self` | L6 | `tests/test_cli_link.py::test_self_is_expanded_on_write` |
| all three target grammars resolve | L6 | `tests/test_cli_link.py::test_each_dst_grammar_resolves` |
| ...with `pnk://` tried before the alias form | L6 | `tests/test_cli_link.py::test_a_pnk_uri_wins_over_an_alias_that_happens_to_be_called_pnk` |
| ...and a colon in a path is still a path | L6 | `tests/test_cli_link.py::test_a_colon_in_a_path_that_is_not_a_declared_alias_stays_a_path` |
| a well-formed `pnk://` to an absent target is written | L6 | `tests/test_cli_link.py::test_a_well_formed_pnk_uri_to_an_absent_target_is_written` |
| an unresolvable target is refused with its remedy | L6 | `tests/test_cli_link.py::test_an_unresolvable_dst_is_refused_with_its_remedy` |
| ...including an alias whose KB is not on this machine | L6 | `tests/test_cli_link.py::test_an_alias_pointing_at_a_kb_that_is_not_here_is_refused` |
| ...and one whose partner declares a different `[kb] id` | L6 | `tests/test_cli_link.py::test_an_alias_whose_partner_declares_a_different_id_is_refused` |
| a source with no sidecar is refused, and none is minted | L6 | `tests/test_cli_link.py::test_a_source_with_no_sidecar_is_refused_and_none_is_minted` |
| an unreadable source sidecar is never overwritten | L6 | `tests/test_cli_link.py::test_an_unreadable_source_sidecar_is_never_overwritten` |
| a source outside the KB is refused | L6 | `tests/test_cli_link.py::test_a_source_outside_the_kb_is_refused` |
| ...and a sidecar named as the source | L6 | `tests/test_cli_link.py::test_a_sidecar_named_as_the_source_is_refused` |
| an empty `--rel` is refused before anything is read | L6 | `tests/test_cli_link.py::test_an_empty_rel_is_refused_before_anything_is_read` |
| ...and a missing one is a usage error | L6 | `tests/test_cli_link.py::test_a_missing_rel_is_a_usage_error` |
| comments survive a rewrite through `pnk link` | L6 | `tests/test_cli_link.py::test_comments_survive_a_rewrite_through_pnk_link` |
| unknown keys inside a link entry survive it | L6 | `tests/test_cli_link.py::test_unknown_keys_inside_a_link_entry_survive_through_pnk_link` |
| no line outside the `links` block changes | L6 | `tests/test_cli_link.py::test_no_line_outside_the_links_block_changes_when_a_link_is_added` |
| ...while an indented block is reindented (pinned) | L6 | `tests/test_cli_link.py::test_an_indented_links_block_is_reindented_when_a_link_is_added` |
| ...and a document-trailing comment is captured (pinned) | L6 | `tests/test_cli_link.py::test_a_document_trailing_comment_is_captured_when_the_first_link_is_appended` |
| a first link into a null `links` value does not crash | L6 | `tests/test_cli_link.py::test_a_first_link_into_a_null_links_value_does_not_crash` |
| a `rel` that looks like a boolean is quoted, on both write paths | L6 | `tests/test_cli_link.py::test_a_rel_that_looks_like_a_boolean_is_quoted`, `::test_a_rel_that_looks_like_a_boolean_is_quoted_on_a_first_link_too` |
| the source document is byte-identical afterwards | L6 | `tests/test_cli_link.py::test_the_source_document_is_byte_identical_afterwards` |
| the write is atomic under an interrupted rename | L6 | `tests/test_cli_link.py::test_the_write_is_atomic_under_an_interrupted_rename` |
| the same link twice writes nothing the second time | L6 | `tests/test_cli_link.py::test_the_same_link_twice_writes_nothing_the_second_time` |
| ...while a second relation to one target is a second entry | L6 | `tests/test_cli_link.py::test_a_second_relation_to_the_same_target_is_a_second_entry` |
| what `pnk link` writes reaches the `links` table | L6 | `tests/test_cli_link.py::test_a_link_round_trips_through_sync_into_the_links_table` |
| the grammar is reachable without the CLI | L6 | `tests/test_cli_link.py::test_resolve_target_is_reachable_without_the_cli` |
| a document cannot link to itself | L6 review | `tests/test_cli_link.py::test_a_document_cannot_link_to_itself` |
| a symlinked document inside the KB can be linked | L6 review | `tests/test_cli_link.py::test_a_symlinked_document_inside_the_kb_can_be_linked` |
| ...while `..` is still refused | L6 review | `tests/test_cli_link.py::test_a_dot_dot_escape_is_still_refused` |
| ...and a symlinked *directory* cannot carry a link out of the KB | L6 review 2 | `tests/test_cli_link.py::test_a_symlinked_directory_cannot_carry_a_link_out_of_the_kb` |
| an absolute source behind a symlinked ancestor is accepted | L6 review 2 | `tests/test_cli_link.py::test_an_absolute_source_behind_a_symlinked_ancestor_is_accepted` |
| an unreadable or over-long path is refused, not a traceback | L6 review 3 | `tests/test_cli_link.py::test_an_unreadable_directory_is_refused_rather_than_crashing` |
| ...and an unreadable *partner* KB likewise | L6 review 4 | `tests/test_cli_link.py::test_a_partner_kb_that_cannot_be_read_is_unreachable_not_a_traceback` |
| ...and a `[[links.kb]] path` that will not expand | L6 review 5 | `tests/test_cli_link.py::test_a_linked_kb_path_that_will_not_expand_is_unreachable_not_a_traceback` |
| ...and the same class inside `linkscan`, on a git hook | L6 review 5 | `tests/test_sync_links.py::test_a_linked_kb_that_raises_before_the_handling_is_still_only_an_issue` |
| a partner with a malformed `[kb] id` names the KB it came from | L6 review 5 | `tests/test_cli_link.py::test_a_partner_with_a_malformed_kb_id_names_the_kb_it_came_from` |
| a `[[links.kb]] path` naming a regular file says so | L6 review 5 | `tests/test_cli_link.py::test_a_linked_kb_path_naming_a_regular_file_says_so` |
| ...and a `pinakes.toml` that is a directory or a broken symlink says which | L6 review 9 | `tests/test_cli_link.py::test_a_pinakes_toml_that_is_not_a_regular_file_says_which` |
| a partner `include` pattern reaching outside its KB is refused | L6 review 10 | `tests/test_sync_links.py::test_a_partner_include_pattern_outside_its_own_kb_is_refused` |
| ...while a symlinked document *inside* a partner KB is still read | L6 review 10 | `tests/test_sync_links.py::test_a_symlinked_document_inside_a_partner_kb_is_still_read` |
| ...refused **before** the glob, so the walk is bounded | L6 review 11 | `tests/test_sync_links.py::test_an_escaping_include_pattern_is_refused_without_walking` |
| ...while a `..` that stays *inside* the KB is not refused | L6 review 12 | `tests/test_sync_links.py::test_a_dot_dot_pattern_that_stays_inside_the_kb_is_not_refused` |
| ...and a symlinked escape stops at the first match | L6 review 12 | `tests/test_sync_links.py::test_a_symlinked_escape_stops_at_the_first_match` |
| ...and a *leading* glob does not defeat the refusal | L6 review 13 | `tests/test_sync_links.py::test_a_leading_glob_does_not_defeat_the_static_refusal` |
| a fixed and a glob include naming one symlinked document agree | L6 review 13 | `tests/test_sync_links.py::test_a_fixed_include_naming_a_symlinked_document_agrees_with_the_glob_spelling` |
| an absolute include says it is absolute, not that it escapes | L6 review 13 | `tests/test_sync_links.py::test_an_absolute_include_says_it_is_absolute_not_that_it_escapes` |
| ...and `**` before a `..` does not defeat the refusal | L6 review 14 | `tests/test_sync_links.py::test_a_double_star_before_a_dot_dot_does_not_defeat_the_refusal` |
| one unusable include pattern does not discard the others | L6 review 14 | `tests/test_sync_links.py::test_one_unusable_include_pattern_does_not_discard_the_others` |
| the walk raising is an issue, never a traceback | L6 review 14 | `tests/test_sync_links.py::test_the_walk_raising_is_an_issue_not_a_traceback` |
| ...for a bad `include` **or** `exclude` entry, without discarding the rest | L6 review 15 | `tests/test_sync_links.py::test_one_bad_sources_entry_is_one_problem_not_the_end_of_the_partner` |
| a trailing `..` in an include is refused | L6 review 15 | `tests/test_sync_links.py::test_a_trailing_dot_dot_include_is_refused` |
| only `**` is dropped from the containment probe | L6 review 15 | `tests/test_sync_links.py::test_only_double_star_is_dropped_from_the_probe` |
| a partner document with no sidecar contributes nothing | L6 review 15 | `tests/test_sync_links.py::test_a_partner_document_without_a_sidecar_contributes_nothing` |
| a pattern escaping under one root collects under none | L6 review 16 | `tests/test_sync_links.py::test_a_pattern_that_escapes_under_one_root_collects_under_none` |
| ...and an escape matching only sidecars is still reported | L6 review 11 | `tests/test_sync_links.py::test_an_escape_matching_only_sidecars_is_still_reported` |
| one escaping pattern is one problem, however many roots | L6 review 11 | `tests/test_sync_links.py::test_one_escaping_pattern_is_one_problem_however_many_roots` |
| `exclude` matches the path the partner wrote, not the resolved one | L6 review 11 | `tests/test_sync_links.py::test_an_exclude_rule_matches_the_path_the_partner_wrote_not_the_resolved_one` |
| the boundary is the KB root, not `[sources]` (stated residual) | L6 review 3 | `tests/test_cli_link.py::test_a_document_inside_the_root_but_outside_sources_can_be_linked` |
| a `~` path is refused, not a `RuntimeError` traceback | L6 review | `tests/test_cli_link.py::test_a_home_relative_path_is_refused_rather_than_crashing` |
| an empty `tags:`/`provenance:` is not normalised by a link | L6 review | `tests/test_cli_link.py::test_an_empty_tags_or_provenance_is_not_normalised_by_adding_a_link` |
| a symlinked sidecar is written through, not replaced | L6 review | `tests/test_cli_link.py::test_a_symlinked_sidecar_is_written_through_not_replaced` |
| `<alias>:` naming no document says so | L6 review | `tests/test_cli_link.py::test_an_alias_naming_no_document_says_so` |
| ...and a manifest declaring no linked KBs says that | L6 review | `tests/test_cli_link.py::test_a_kb_declaring_no_linked_kbs_says_that_rather_than_listing_none` |
| `resolve_path` never raises, and answers an **absolute** path or `None` | L6 review 7, 8 | `tests/test_sync_links.py::test_resolve_path_never_raises_whatever_the_manifest_says` |
| ...so an unresolvable path is reported, never silently fresh-skipped | L6 review 7, 8 | `tests/test_sync_links.py::test_an_unresolvable_path_is_reported_rather_than_fresh_skipped` |
| ...and an unresolvable path is never walked from the working directory | L6 review 8 | `tests/test_sync_links.py::test_an_unresolvable_path_is_never_walked_from_the_working_directory` |
| ...nor resolved through it into a permanent link | L6 review 8 | `tests/test_cli_link.py::test_an_unresolvable_linked_kb_path_is_never_resolved_through_the_working_directory` |
| an embedded NUL in a path is refused, not a `ValueError` traceback | L6 review 7 | `tests/test_cli_link.py::test_a_path_with_an_embedded_nul_is_refused_rather_than_crashing` |

## The sidecar round-trip (L5b)

| What must be true | Increment | Where it is checked |
|---|---|---|
| an unknown key round-trips byte-identically | L5b | `tests/test_sidecar.py::test_an_unknown_key_round_trips_byte_identically` |
| comments survive a rewrite | L5b | `tests/test_sidecar.py::test_comments_survive_a_rewrite` |
| ...inside `provenance.extraction` | L5b | `tests/test_sidecar.py::test_a_comment_inside_provenance_extraction_survives_a_re_extraction` |
| ...on a `tags` entry | L5b | `tests/test_sidecar.py::test_a_comment_on_a_tags_entry_survives_a_rewrite` |
| ...and through both provenance helpers | L5b | `tests/test_sidecar.py::test_with_extraction_provenance_preserves_comments`, `::test_without_extraction_provenance_preserves_comments` |
| quoting style survives | L5b | `tests/test_sidecar.py::test_quoting_style_survives_a_rewrite` |
| block scalars and blank lines survive | L5b | `tests/test_sidecar.py::test_block_scalars_and_blank_lines_survive_a_rewrite` |
| a long spaced value is not folded | L5b | `tests/test_sidecar.py::test_a_value_with_spaces_past_eighty_columns_is_not_folded` |
| YAML 1.1 scalars are no longer corrupted | L5b | `tests/test_sidecar.py::test_yaml_1_1_scalars_are_no_longer_corrupted` |
| the user's key order is preserved | L5b | `tests/test_sidecar.py::test_the_users_key_order_is_preserved_on_rewrite` |
| ...while a minted sidecar is canonical | L5b | `tests/test_sidecar.py::test_a_minted_sidecar_still_uses_canonical_order` |
| `provenance` first appearing is appended, moving no comment | L5b | `tests/test_sidecar.py::test_provenance_first_appearing_is_appended_and_moves_no_comment` |
| links reconcile by `to`, not by position | L5b | `tests/test_sidecar.py::test_reordering_links_does_not_move_their_comments` |
| ...and a removed link takes only its own comment | L5b | `tests/test_sidecar.py::test_a_removed_link_takes_only_its_own_comment` |
| unknown per-link keys survive | L5b | `tests/test_sidecar.py::test_unknown_keys_inside_a_link_entry_survive_a_rewrite` |
| changed tags keep the surviving entries' comments | L5b | `tests/test_sidecar.py::test_changed_tags_keep_the_comments_of_the_entries_that_remain` |
| an unchanged known key is not reassigned | L5b | `tests/test_sidecar.py::test_an_unchanged_known_key_is_not_reassigned`, `::test_an_unchanged_links_block_is_not_rewritten` |
| a minted ambiguous title is quoted, read back through PyYAML | L5b | `tests/test_sidecar.py::test_a_minted_title_that_looks_like_a_boolean_is_quoted` |
| a duplicate key is refused without ruamel's suppression URL | L5b | `tests/test_sidecar.py::test_a_duplicate_key_is_refused_without_ruamels_suppression_url` |
| a JSON-unencodable value is refused with a remedy | L5b | `tests/test_sidecar.py::test_a_json_unencodable_extra_value_is_refused_with_a_remedy` |
| ...including `!!str` | L5b | `tests/test_sidecar.py::test_a_double_bang_str_value_is_refused` |
| ...while the tags that worked before still work | L5b | `tests/test_sidecar.py::test_the_standard_tags_that_worked_before_the_swap_still_work` |
| a custom-tagged mapping is accepted (documented widening) | L5b | `tests/test_sidecar.py::test_a_tagged_mapping_is_accepted_because_it_serialises` |
| a uniformly non-string-keyed mapping is a stated residual | L5b | `tests/test_sidecar.py::test_a_uniformly_non_string_keyed_mapping_is_a_stated_residual` |
| an explicit `!!` tag is stripped | L5b | `tests/test_sidecar.py::test_an_explicit_double_bang_tag_is_stripped` |
| an anchor on an empty value is destroyed | L5b | `tests/test_sidecar.py::test_an_anchor_on_an_empty_value_is_destroyed` |
| ...while one on a real value survives | L5b | `tests/test_sidecar.py::test_an_anchor_on_a_real_value_survives` |
| CRLF, BOM and `---`/`...` are not carried | L5b | `tests/test_sidecar.py::test_what_yaml_does_not_carry_is_not_carried` |
| a missing trailing newline is added | L5b | `tests/test_sidecar.py::test_a_missing_trailing_newline_is_added` |
| the AST scan catches a function-scoped import | L5b | `tests/test_packaging.py::test_the_ast_scan_catches_a_function_scoped_import` |
| the stub signature test catches a fabricated parameter | L5b | `tests/test_packaging.py::test_the_stub_signature_test_catches_a_fabricated_parameter` |
| ruamel's sequence reindentation is a documented exclusion | L5b | `tests/test_sidecar.py::test_a_two_space_indented_sequence_is_reindented` |
| two links sharing a `to` keep their own `rel` and comment | L5b | `tests/test_sidecar.py::test_two_links_sharing_a_to_keep_their_own_rel_and_comment` |
| a user key inside `provenance.extraction` survives a re-extraction | L5b | `tests/test_sidecar.py::test_a_user_key_inside_provenance_extraction_survives_a_re_extraction` |
| a document-trailing comment is captured by an appended key (pinned) | L5b | `tests/test_sidecar.py::test_a_document_trailing_comment_is_captured_by_an_appended_key` |
| reading a `%YAML` directive does not contaminate the next document | L5b | `tests/test_sidecar.py::test_reading_a_directive_does_not_contaminate_the_next_document` |
| ...nor a freshly minted sidecar | L5b | `tests/test_sidecar.py::test_a_minted_sidecar_is_not_contaminated_either` |
| a known key with a null value does not crash the writer | L5b | `tests/test_sidecar.py::test_a_known_key_with_a_null_value_does_not_crash_the_writer` |
| editing one `rel` where two links share a `to` moves neither comment | L5b | `tests/test_sidecar.py::test_editing_one_rel_where_two_links_share_a_to_moves_neither_comment` |
| a key that is not a string is reported as a key | L5b | `tests/test_sidecar.py::test_a_key_that_is_not_a_string_is_refused_as_a_key` |
| a reused anchor name is refused, not silently resolved | L5b | `tests/test_sidecar.py::test_a_reused_anchor_name_is_refused_rather_than_silently_resolved` |
| ...whatever the caller's warning filter says | L5b | `tests/test_sidecar.py::test_a_reused_anchor_is_refused_whatever_the_ambient_warning_filter_says` |
| a non-string key at the top level is refused | L5b | `tests/test_sidecar.py::test_a_non_string_key_at_the_top_level_is_refused` |
| two identical link entries both survive | L5b | `tests/test_sidecar.py::test_two_identical_link_entries_both_survive` |
| editing a `rel` updates the entry rather than replacing it | L5b | `tests/test_sidecar.py::test_editing_a_rel_updates_the_entry_rather_than_replacing_it` |
| **every committed sidecar round-trips** (the exit criterion) | L5b | `tests/test_partner_kb.py::test_every_committed_sidecar_round_trips_through_read_and_write` |
| a `self` link keeps its place, comment and unknown keys | L5b | `tests/test_sidecar.py::test_a_self_link_keeps_its_place_its_comment_and_its_unknown_keys` |
| a string field 1.2 resolves as a number is refused | L5b | `tests/test_sidecar.py::test_a_string_field_that_yaml_1_2_resolves_as_a_number_is_refused` |
| a tagged scalar in a known field is refused, without a ruamel class name | L5b | `tests/test_sidecar.py::test_a_tagged_scalar_in_a_known_field_is_refused_with_a_remedy` |
| a `rel` or tag that looks like a boolean is quoted when written | L5b | `tests/test_sidecar.py::test_a_rel_or_tag_that_looks_like_a_boolean_is_quoted_when_written` |
| ...including when the key first appears | L5b | `tests/test_sidecar.py::test_a_link_written_where_none_existed_is_quoted_too` |
| the two-resolver union covers PyYAML 1.1 | L5b | `tests/test_packaging.py::test_the_two_resolver_union_covers_pyyaml_1_1` |
| a self-referential anchor is nulled rather than refused (pinned) | L5b | `tests/test_sidecar.py::test_a_self_referential_anchor_is_nulled_rather_than_refused` |
| the deletion limitation is pinned, not fixed | L5b | `tests/test_sidecar.py::test_deleting_a_commented_key_loses_one_comment_and_misattributes_another` |
| `original` is excluded from equality | L5b | `tests/test_sidecar.py::test_the_original_document_is_excluded_from_equality` |
| an anchored or aliased boolean indexes as `true`, at every depth | L5b | `tests/test_sync.py::test_an_anchored_boolean_is_indexed_as_true_not_one` |
| `ruamel.yaml` is a core dependency | L5b | `tests/test_packaging.py::test_ruamel_yaml_is_a_core_dependency` |
| `pyyaml` is dev-only, never core, never an extra | L5b | `tests/test_packaging.py::test_pyyaml_is_dev_only_never_core_and_never_an_extra` |
| no module under `src/` imports PyYAML (AST) | L5b | `tests/test_packaging.py::test_no_module_under_src_imports_pyyaml` |
| ...nor does the free path load it (runtime) | L5b | `tests/test_paid_path.py::test_the_free_path_run_never_loads_yaml` |
| every stub symbol matches its real signature | L5b | `tests/test_packaging.py::test_every_symbol_the_ruamel_stub_declares_matches_inspect_signature` |

## The PDF corpus

| What must be true | Increment | Where it is checked |
|---|---|---|
| the text-layer corpus regenerates byte-identically | I2 | `tests/test_pdf_corpus.py::test_regeneration_is_reproducible` |
| the scanned corpus regenerates within tolerance | I2 | `tests/test_pdf_corpus.py::test_scanned_regeneration_within_tolerance` |
| the corpus cannot silently shrink or balloon | I2 | `tests/test_pdf_corpus.py::test_stratum_counts_and_page_counts_match_the_plan`, `tests/test_pdf_corpus.py::test_byte_budget` |
| the named paid twins exist and are five | I2 | `tests/test_pdf_corpus.py::test_named_paid_twins_exist` |
| every fixture has ground truth, and every ground truth a fixture | I2 | `tests/test_pdf_corpus.py::test_every_fixture_has_ground_truth_and_every_ground_truth_a_fixture` |

## Extraction: layout, the reader, quality

| What must be true | Increment | Where it is checked |
|---|---|---|
| character-to-block assembly is unit-tested, not only scored | I3a | `tests/test_extract_layout.py::test_blocks_from_chars_empty_page` and the six `test_blocks_from_chars_*` cases beside it |
| page offsets tile the extracted text exactly **and** anchor to their page's content | I3a | `tests/test_extract_layout.py::assert_extraction_properties` — the shared helper every `test_assemble_*` case asserts through |
| offsets are computed after the length-changing string policy | I3a | `tests/test_extract_layout.py::test_assemble_offsets_are_computed_after_normalise_not_before` |
| the string policy is versioned apart from layout | I3a | `tests/test_extract_layout.py::test_textpolicy_is_pure_and_does_not_import_layout` |
| the pure core imports no PDF library | I3a | `tests/test_extract_layout.py::test_layout_is_pure` |
| …and that import check can actually fail | I3a | `tests/test_extract_layout.py::test_imported_names_catches_a_name_import_of_layout` |
| the pdfium reader refuses corrupt, encrypted, zero-page and oversize files | I3b | `tests/test_extract_pdfium.py::test_corrupt_header_fixture_raises_a_named_error_not_a_crash`, `tests/test_extract_pdfium.py::test_encrypted_file_is_refused_before_any_parse`, `tests/test_extract_pdfium.py::test_zero_page_file_is_an_error_not_an_empty_success`, `tests/test_extract_pdfium.py::test_size_guard_fires_at_256mb` |
| a quality regression fails the build | I3b | `tests/test_extract_quality.py::test_compare_to_baseline_flags_a_regression_beyond_tolerance` |
| a changed exemption is a structural regression, not a quiet pass | I3b | `tests/test_extract_quality.py::test_compare_to_baseline_flags_a_changed_exemption_as_a_structural_regression` |
| a zero denominator reports `None`, never `0.0` | I3b | `tests/test_extract_quality.py::test_rate_value_is_none_not_zero_when_denominator_is_zero` |
| the one spending threshold is fitted from two real bounds, not guessed | I3b | `tests/test_extract_quality.py::test_threshold_from_fractions_is_the_midpoint_of_the_two_bounds`, `tests/test_extract_quality.py::test_threshold_from_fractions_raises_without_a_true_positive` |
| the floor reaches an installed copy, not just the repo | I3b | `tests/test_extract_quality.py::test_floors_toml_is_installed_package_data` |
| a committed floor cannot silently drift from its corpus | I3b | `check.sh`'s `pdf-eval` gate, which runs `quality.check_floor_drift` — `tests/test_check_script.py::test_check_sh_declares_the_pdf_quality_guard` asserts the gate is *invoked*, not that it fires; the firing is `tests/test_extract_quality.py::test_threshold_from_fractions_is_the_midpoint_of_the_two_bounds` on the fitting side |
| a gate that cannot run says so and still exits 0 | I3b | `tests/test_check_script.py::test_the_skip_and_continue_shape_exits_zero` |
| the floor's absence stops the paid path from spending | I7b | `tests/test_extract_pageyield.py::test_with_no_fitted_floor_the_paid_path_refuses_to_spend_at_all` |
| a healthy PDF is not paid for by accident | I7b | `tests/test_extract_pageyield.py::test_the_free_path_refuses_to_pay_for_a_healthy_pdf` |
| …and a genuinely scanned one still gets through | I7b | `tests/test_extract_pageyield.py::test_a_scanned_pdf_is_what_the_pre_check_lets_through` |

## The extraction cache

| What must be true | Increment | Where it is checked |
|---|---|---|
| a cached extraction is never re-parsed | I4 | `tests/test_extract_cache.py::test_a_second_lookup_with_the_same_key_never_calls_extract` |
| a hit never loads the backend at all, not even lazily | I4 | `tests/test_extract_cache.py::test_a_hit_never_calls_extract_at_all_not_even_lazily` |
| a corrupt or wrong-version entry misses rather than crashes | I4 | `tests/test_extract_cache.py::test_a_truncated_cache_file_misses_rather_than_crashes`, `tests/test_extract_cache.py::test_a_wrong_schema_version_misses` |
| the automatic sweep never destroys a paid entry | I4 | `tests/test_extract_cache.py::test_the_sweep_spares_paid_entries_and_reports_them` |
| a cache write failure never fails a successful extraction | I4 | `tests/test_extract_cache.py::test_a_cache_write_failure_never_fails_an_already_successful_extraction` |
| `--clear-cache` never touches `ledger.jsonl` | I4 | `tests/test_sync.py::test_clear_cache_preserves_the_ledger` |
| `--clear-cache` aborts unattended without `--yes` | I4 | `tests/test_sync.py::test_clear_cache_without_yes_and_without_a_tty_aborts` |
| `--yes` does not authorise destroying paid entries | I7c | `tests/test_cli_budget.py::test_yes_alone_cannot_destroy_paid_cache_entries_unattended` |
| `--clear-cache`'s euro figure joins real ledger lines | I7c | `tests/test_extract_claude.py::test_clear_cache_reports_spend_and_confirms` |
| staged pages are invisible to every cache sweep | I7c | `tests/test_extract_claude.py::test_staged_pages_are_invisible_to_every_cache_sweep` |

## Chunking, the index, and coherence

| What must be true | Increment | Where it is checked |
|---|---|---|
| `chunk.text == indexed_text[start:end]` for every PDF chunk | I5 | `tests/test_chunk_pdf.py::test_the_span_invariant_holds_for_every_chunk` |
| no character of an extraction is dropped | I5 | `tests/test_chunk_pdf.py::test_every_character_lands_in_at_least_one_chunk` |
| a chunk straddling a page break records both pages | I5 | `tests/test_chunk_pdf.py::test_a_hyphenation_join_across_a_page_break_produces_a_genuine_two_page_chunk` |
| a non-paged source never carries page numbers | I5 | `tests/test_chunk_pdf.py::test_markdown_and_text_chunks_never_carry_page_numbers` |
| a v0.1 index refuses to open, with a remedy | I5 | `tests/test_store.py::test_a_v1_index_refuses_to_open_and_says_rebuild` |
| a stale **free** extraction refuses the query | I5 | `tests/test_search.py::test_a_changed_free_fingerprint_refuses_the_query` |
| a stale **paid** extraction warns and marks, never refuses | I5 | `tests/test_search.py::test_a_changed_paid_fingerprint_warns_and_marks` |
| an unrecognised backend name warns rather than refusing every query | I5 | `tests/test_search.py::test_an_unrecognised_backend_name_warns_and_does_not_refuse` |
| the coherence check never imports a paid client | I5 | `tests/test_search.py::test_coherence_never_imports_a_paid_client` |
| a free run never overwrites a paid extraction, and a paid run picks up what a free one indexed | I5 | `tests/test_sync.py::test_backend_drift` (six cases) |
| a rebuild cannot destroy paid provenance | I5 | `tests/test_sync.py::test_a_rebuild_preserves_paid_provenance`, `tests/test_sync.py::test_a_rebuild_after_clear_cache_still_preserves_it` |
| a fresh clone with no local cache fails honestly, not falsely | I5 | `tests/test_sync.py::test_a_fresh_clone_with_no_local_cache_or_index_fails_honestly_not_falsely` |
| a v0.2 sidecar merge preserves every key it did not write | I5 | `tests/test_sidecar.py::test_with_extraction_provenance_merges_additively` |

## Money: the core

| What must be true | Increment | Where it is checked |
|---|---|---|
| a call that would breach any window is never made | I6a | `tests/test_budget_core.py::test_exactly_at_the_cap_proceeds_one_cent_more_does_not` |
| the reservation is never below the reconciled actual | I6a | `tests/test_budget_core.py::test_reservation_bounds_every_usage_table` |
| a pair straddling a window edge is attributed once, to its start | I6a | `tests/test_budget_core.py::test_a_pair_straddling_midnight_is_attributed_to_the_start`, `tests/test_budget_core.py::test_a_pair_straddling_a_month_end_is_attributed_to_the_start`, `tests/test_budget_core.py::test_a_pair_straddling_a_dst_transition_is_attributed_correctly` |
| a refusal names every window, not just the first to bind | I6a | `tests/test_budget_core.py::test_the_refusal_names_all_three_windows` |
| a request that cannot fit the context window is caught before the call | I6a | `tests/test_budget_core.py::test_the_context_window_precheck_names_its_limit` |
| an estimate against stale prices is refused | I6a | `tests/test_budget_core.py::test_a_stale_as_of_refuses_to_estimate_and_names_the_remedy` |
| an unaffordable document is refused before the first call | I6a | `tests/test_budget_core.py::test_an_unaffordable_document_is_refused_before_the_first_call` |
| confirmation is once per document, not once per slice | I6a | `tests/test_budget_core.py::test_confirmation_is_once_per_document_not_per_slice` |
| the budget core imports no paid client | I6a | `tests/test_budget_core.py::test_budget_module_is_pure` |
| money is `Decimal` from the manifest, never through `float` | I6a | `tests/test_manifest.py::test_budget_values_parse_as_exact_decimal_not_float` |
| the price table ships in the wheel | I6a | `tests/test_budget_core.py::test_prices_are_installed_package_data` |
| a malformed price table is a startup error, never a silent zero | I6a | `tests/test_budget_core.py::test_a_malformed_prices_toml_is_a_startup_error_not_a_silent_zero`, `tests/test_check_script.py::test_check_sh_declares_the_prices_toml_gate` |

## Money: the ledger

| What must be true | Increment | Where it is checked |
|---|---|---|
| the ledger records no query text or content | I6b | `tests/test_ledger.py::test_the_ledger_stores_no_query_text_and_no_document_content` |
| every ledger line carries its currency and FX provenance | I6b | `tests/test_ledger.py::test_every_line_carries_its_cost_and_the_conversion_that_produced_it` |
| money is quantised once, at write time | I6b | `tests/test_ledger.py::test_money_is_quantised_once_and_below_the_cent` |
| a JSON float for money is rejected rather than silently accepted | I6b | `tests/test_ledger.py::test_a_json_number_for_money_is_rejected_rather_than_silently_floated` |
| an interrupted call leaves a visible unknown outcome | I6b | `tests/test_ledger.py::test_a_process_killed_after_reserving_leaves_a_readable_unknown_outcome` |
| a call that never billed does not permanently consume budget | I6b | `tests/test_ledger.py::test_a_call_that_raises_before_a_response_is_voided_and_consumes_no_headroom` |
| a call that **did** bill is never voided to zero | I6b | `tests/test_ledger.py::test_a_call_that_raises_after_a_response_is_never_voided` |
| a void can never supersede a reconciliation | I6b | `tests/test_ledger.py::test_a_void_can_never_supersede_a_reconciliation` |
| two processes appending at once interleave no record | I6b | `tests/test_ledger.py::test_two_processes_appending_at_once_interleave_no_record` |
| the ledger survives a rebuild and a `--clear-cache` byte for byte | I6b | `tests/test_ledger.py::test_the_ledger_survives_rebuild_and_clear_cache_byte_for_byte` |
| an unresolvable unknown outcome has a documented way out | I6b | `tests/test_ledger.py::test_resolving_an_unknown_outcome_appends_and_never_edits` |
| `pnk budget --resolve` appends rather than edits | I6b | `tests/test_cli_budget.py::test_resolve_closes_an_unknown_outcome_from_the_command_line` |
| a non-interactive run never spends silently, and never aborts with nothing to confirm | I6b | `tests/test_cli_budget.py::test_a_confirmation_owed_with_no_tty_and_no_yes_aborts_with_a_remedy`, `tests/test_cli_budget.py::test_a_non_interactive_run_with_nothing_to_confirm_proceeds` |
| the month's cap stops a run the operation's cap would allow | I6b | `tests/test_cli_budget.py::test_a_kb_at_499_of_a_500_month_refuses_the_next_call` |
| spend is read back from the ledger, never tallied in memory | I6b | `tests/test_cli_budget.py::test_the_operation_window_is_read_back_from_the_ledger_not_tallied_in_memory` |
| hook-driven and CI syncs cannot reach the paid path — proved by running them | I6b | `tests/test_hooks.py::test_hooks_force_the_free_backend`, `tests/test_hooks.py::test_every_hook_and_the_ci_workflow_carry_the_free_backend_flag` |
| the generated CI workflow forces the free backend too | I6b | `tests/test_ci.py::test_the_workflow_forces_the_free_backend`, `tests/test_ci.py::test_the_workflow_and_the_hooks_cannot_disagree` |
| that workflow caches the state directory holding the ledger | I6b | `tests/test_ci.py::test_the_workflow_caches_the_state_directory_that_holds_the_ledger` |
| `pnk init --ci` never overwrites a workflow somebody wrote | I6b | `tests/test_ci.py::test_an_existing_workflow_is_never_overwritten` |

## The paid-path allowlist

| What must be true | Increment | Where it is checked |
|---|---|---|
| the allowlist cannot rot (a listed path must exist) | I7a | `check.sh` gate + `tests/test_paid_path.py::test_the_allowlist_matches_the_source_tree` |
| no paid client is imported outside the allowlist | I7a | `tests/test_paid_path.py::test_no_paid_client_outside_the_allowlist` |
| the allowlist cannot widen (an exclusion cannot exempt a directory) | I7a | `tests/test_paid_path.py::test_a_directory_entry_fails_gate_1`, `tests/test_paid_path.py::test_the_allowlist_exempts_only_the_exact_path` |
| the free path never imports the paid client | I7a | `tests/test_paid_path.py::test_the_free_path_never_imports_the_paid_client` |
| that gate can actually fail | I7a | `tests/test_paid_path.py::test_the_free_path_gate_fails_when_an_import_is_planted` |
| …and says so rather than passing when it cannot run | I7a | `tests/test_paid_path.py::test_the_free_path_gate_says_so_when_it_cannot_run` |
| the two paid-client lists agree | I7a | `tests/test_paid_path.py::test_the_two_paid_client_lists_agree` |

## The paid extractor

| What must be true | Increment | Where it is checked |
|---|---|---|
| a refusal is handled before `content` is read | I7b | `tests/test_extract_claude.py::test_a_refusal_is_handled_before_content_is_read` |
| a refusal reports what the API actually said | I7b | `tests/test_extract_claude.py::test_a_refusal_reports_the_category_and_explanation_the_api_sent` |
| a truncated response is not retried identically | I7b | `tests/test_extract_claude.py::test_a_truncated_response_is_reasked_once_at_the_raised_bound`, `tests/test_extract_claude.py::test_a_second_truncation_is_a_failure` |
| an oversize request fails hard instead of being re-paid | I7b | `tests/test_extract_claude.py::test_a_context_window_failure_is_hard_with_no_retry` |
| a transient failure is retried under a fresh reservation, and the old one is voided | I7b | `tests/test_extract_claude.py::test_a_rate_limit_is_voided_and_retried_under_a_fresh_reservation` |
| a timeout leaves an unknown outcome rather than a void | I7b | `tests/test_extract_claude.py::test_a_timeout_leaves_an_unknown_outcome_rather_than_a_void` |
| a leaked internal tag never reaches the indexed text | I7b | `tests/test_extract_claude.py::test_a_leaked_internal_tag_is_retried_never_stripped` |
| every call, including every retry, is reserved and ledgered | I7b | `tests/test_extract_claude.py::test_every_call_takes_its_own_reservation_and_ledger_pair` |
| the semantic and transport ceilings are separate counters | I7b | `tests/test_extract_claude.py::test_the_semantic_budget_refuses_a_seventh_call`, `tests/test_extract_claude.py::test_transport_attempts_are_bounded_without_consuming_a_schema_retry` |
| a short page array is caught before positional mapping | I7b | `tests/test_extract_claude.py::test_a_short_page_array_is_a_schema_failure`, `tests/test_extract_claude.py::test_parse_refuses_to_map_a_short_array_positionally` |
| the paid backend's page spans are content-anchored, not merely tiling | I7b | `tests/test_extract_claude.py::test_every_pages_own_text_lands_inside_its_own_span`, `tests/test_extract_claude.py::test_page_spans_tile_the_whole_text` |
| offsets are computed after the length-changing string policy | I7b | `tests/test_extract_claude.py::test_normalise_runs_before_offsets` |
| `--estimate-only` generates nothing | I7b | `tests/test_extract_claude.py::test_estimate_only_makes_no_generation_call` |
| the SDK's own retries are disabled — asserted without a stand-in | I7b | `tests/test_extract_claude.py::test_the_client_disables_sdk_retries` (unmarked), `tests/test_extract_claude.py::test_the_real_client_disables_sdk_retries` (`paid`) |
| the reservation is never below the actual | I7b | `tests/test_extract_claude.py::test_reservation_bounds_every_recorded_usage` |
| the reconciliation reads the response, not the reservation | I7b | `tests/test_extract_claude.py::test_the_reconciliation_supersedes_with_the_real_cost_not_the_reservation` |
| changing the model **or K** misses the cache | I7b | `tests/test_extract_claude.py::test_changing_the_model_misses_the_cache`, `tests/test_extract_claude.py::test_changing_k_misses_the_cache` |
| a short final slice is handled | I7b | `tests/test_extract_claude.py::test_a_document_whose_page_count_is_not_a_multiple_of_k` |
| the request shape is pinned, not just the responses | I7b | `tests/test_extract_claude.py::test_the_request_puts_the_document_before_the_text_and_sends_no_sampling_knobs`, `tests/test_extract_claude.py::test_thinking_is_disabled_explicitly_and_pinned_to_its_effort` |
| the recorded-fixture set covers every branch it is cited for | I7b | `tests/test_extract_claude.py::test_the_recorded_fixture_set_covers_every_branch`, `tests/test_extract_claude.py::test_the_branches_a_recording_reached_are_backed_by_one` |
| every fixture says where its bodies came from | I7d | `tests/test_extract_claude.py::test_every_fixture_declares_where_its_bodies_came_from`, `tests/test_extract_claude.py::test_a_recorded_fixture_agrees_with_the_model_it_claims` |
| a cache entry whose `per_page_provenance` is the wrong shape misses, rather than degrading the type | I7b | `tests/test_extract_cache.py::test_a_non_string_provenance_value_misses_rather_than_silently_degrading` |
| the whole wiring works, not only the pieces | I7b | `tests/test_extract_claude.py::test_a_real_sync_extracts_indexes_records_and_caches` |

## The audit, staging, and all-or-nothing commit

| What must be true | Increment | Where it is checked |
|---|---|---|
| a half-extracted document writes nothing rather than a truncated entry | I7c | `tests/test_extract_claude.py::test_a_partially_extracted_document_writes_no_complete_entry` |
| a page with no native layer is exempt, never scored zero | I7c | `tests/test_extract_audit.py::test_a_page_with_no_native_layer_is_exempt_not_zero` |
| an all-exempt document reports no median rather than zero | I7c | `tests/test_extract_audit.py::test_an_all_exempt_document_reports_no_median_rather_than_zero` |
| the audit's summary always carries its denominators | I7c | `tests/test_extract_audit.py::test_the_summary_always_carries_its_denominators` |
| a page-count mismatch refuses rather than zipping to the shorter | I7c | `tests/test_extract_audit.py::test_a_page_count_mismatch_refuses_rather_than_zipping_to_the_shorter` |
| a uniform document flags nothing — "below median" is strict | I7c | `tests/test_extract_audit.py::test_below_median_is_strict_so_a_uniform_document_flags_nothing` |
| an unparsable audit value degrades to exempt, never to a pass | I7c | `tests/test_extract_audit.py::test_an_unparsable_audit_value_degrades_to_exempt` |
| the audit survives the round trip through sidecar provenance | I7c | `tests/test_extract_audit.py::test_the_audit_round_trips_through_provenance` |
| an interrupted paid run re-pays for nothing staged | I7c | `tests/test_extract_claude.py::test_a_resumed_run_re_asks_nothing_that_was_staged` |
| a slice interrupted mid-flight is re-asked whole | I7c | `tests/test_extract_claude.py::test_a_slice_interrupted_mid_flight_is_re_asked_whole` |
| a successful document leaves no staging behind | I7c | `tests/test_extract_claude.py::test_a_successful_document_leaves_no_staging_behind` |
| `--force` alone cannot discard a paid extraction | I7c | `tests/test_sync.py::test_force_alone_without_an_explicit_extract_does_not_override` |
| `--force` widens no cap | I7c | `tests/test_extract_claude.py::test_force_does_not_widen_a_budget_cap` |
| `on_exceed = "partial"` keeps completed documents and stops cleanly | I7c | `tests/test_extract_claude.py::test_on_exceed_partial_is_corpus_level_never_page_level` |
| a corpus stops at the first cap breach rather than failing every document | I7c | `tests/test_extract_claude.py::test_a_corpus_stops_at_the_first_cap_breach_rather_than_failing_every_document` |
| every new `pnk sync` flag has a stated scope in `--help` | I7c | `tests/test_cli.py::test_every_sync_flag_documents_its_scope` |

## Page citations and the health check (I8)

| What must be true | Increment | Where it is checked |
|---|---|---|
| a table-cell word survives extraction → cache → chunk → FTS → CLI **and** MCP | I8 | `tests/test_pdf_trace.py::test_a_table_cell_word_survives_every_hop` |
| every filter dimension actually selects PDF rows when filtered on | I8 | `tests/test_pdf_trace.py::test_every_filter_dimension_resolves_for_pdfs` |
| one slice's cost survives estimate → reservation → usage → reconciliation → report | I8 | `tests/test_pdf_trace.py::test_a_paid_slice_traces_from_estimate_to_the_budget_report` |
| page provenance reaches the MCP surface, not only the CLI | I8 | `tests/test_serve.py::test_mcp_search_carries_page_spans`, `tests/test_serve.py::test_mcp_get_is_page_aware` |
| a chunk spanning two pages renders as a range | I8 | `tests/test_search.py::test_a_two_page_chunk_renders_a_range` |
| a paged citation cannot be misread as character offsets | I8 | `tests/test_search.py::test_the_page_marker_is_what_stops_a_citation_being_ambiguous` |
| a non-paged source keeps the citation it always had | I8 | `tests/test_search.py::test_a_non_paged_source_still_cites_character_offsets`, `tests/test_cli_search.py::test_a_non_paged_source_reports_null_pages_and_the_offset_citation` |
| a PDF is served as extracted text, not as its bytes | I8 | `tests/test_serve.py::test_a_pdf_is_served_as_its_extracted_text_rather_than_its_bytes` |
| a swept extraction cache is an error, never a silent re-extraction | I8 | `tests/test_serve.py::test_a_swept_extraction_cache_is_an_error_rather_than_a_silent_re_extraction` |
| a low-yield **page** is flagged inside a healthy document | I8 | `tests/test_doctor.py::test_text_yield_flags_pages_not_documents` |
| the yield floor separates empty from non-empty, and nothing finer | I8 | `tests/test_extract_pageyield.py::test_a_page_exactly_on_the_floor_is_not_below_it`, `tests/test_extract_pageyield.py::test_the_decision_is_per_document_even_though_the_floor_is_per_page` |
| an unmeasurable document is never reported as one that passed | I8 | `tests/test_doctor.py::test_a_partly_swept_cache_still_names_what_it_could_not_measure` |
| the health check does not crash on a KB it does not understand | I8 | `tests/test_doctor.py::test_an_unknown_extraction_backend_does_not_crash_the_health_check` |

## `pnk doctor`, check by check

| What must be true | Increment | Where it is checked |
|---|---|---|
| **every check `diagnose` can produce is named by a test** | I9 | `tests/test_doctor.py::test_every_doctor_check_is_exercised_by_a_test` |
| a non-OK check carries a remedy — **spot-checked on five, not enumerated** | I11 | `tests/test_doctor.py::test_every_problem_carries_a_remedy` asserts over whichever checks are non-OK in one unsynced fixture (5 of 18 there; `diagnose` produces ≥29 on a synced KB), so a new remedy-less WARN passes unless it fires in that fixture. The enumerating sibling is `tests/test_doctor.py::test_every_doctor_check_is_exercised_by_a_test` |
| the template check reports drift without applying anything | I9 | `tests/test_doctor.py::test_a_template_version_drift_is_reported_with_both_versions`, `tests/test_doctor.py::test_a_template_the_install_does_not_have_is_a_warning_not_a_failure` |
| a disabled reranker is reported as configured, not as missing | I9 | `tests/test_doctor.py::test_the_reranker_check_says_when_reranking_is_off_rather_than_loading_one` |
| the model cache check names where weights resolve | I9 | `tests/test_doctor.py::test_the_model_cache_check_names_the_directory_weights_resolve_under` |
| an unavailable extension loader says what it does *not* affect | I9 | `tests/test_doctor.py::test_the_extensions_check_explains_that_it_only_gates_an_unshipped_tier` |
| a dangling link inside the KB is a warning | I9 | `tests/test_doctor.py::test_a_dangling_link_inside_this_kb_is_a_warning_naming_how_many` |
| link coverage is the **ratio**, not the edge count | L7 | `tests/test_doctor.py::test_link_coverage_reports_the_ratio_not_the_edge_count` |
| ...counting authored links only, never reverse-scanned rows | L7 | `tests/test_doctor.py::test_link_coverage_counts_authored_links_only` |
| a KB with no authored links nudges | L7 | `tests/test_doctor.py::test_a_kb_with_no_authored_links_nudges` |
| a dangling cross-KB target warns, when its KB is here to ask | L7 | `tests/test_doctor.py::test_a_dangling_cross_kb_target_warns_with_a_reason` |
| ...and one its own KB does have is not unresolved | L7 | `tests/test_doctor.py::test_a_cross_kb_target_that_its_own_kb_does_have_is_not_unresolved` |
| ...while a KB absent from this machine is counted, not judged | L7 | `tests/test_doctor.py::test_a_cross_kb_link_into_a_kb_not_here_is_counted_but_not_called_unresolved` |
| a linked KB absent from this machine warns | L7 | `tests/test_doctor.py::test_a_linked_kb_absent_from_this_machine_warns` |
| ...one whose path resolves to nothing warns with the reason | L7 | `tests/test_doctor.py::test_a_linked_kb_path_that_resolves_to_nothing_warns_with_the_reason` |
| ...and an absolute path warns even when it resolves | L7 | `tests/test_doctor.py::test_an_absolute_linked_kb_path_warns` |
| the linked-KBs check exists even with none declared, so the coverage guard sees it | L7 | `tests/test_doctor.py::test_a_kb_declaring_no_linked_kbs_still_produces_the_check` |
| ...and runs without an index, when an absolute path matters most | L7 | `tests/test_doctor.py::test_the_linked_kbs_check_runs_without_an_index` |
| an unsynced KB says the link checks did not run | L8 | `tests/test_doctor.py::test_an_unsynced_kb_says_the_link_checks_did_not_run` |
| a soft-deleted document does not inflate the coverage ratio | L7 review | `tests/test_doctor.py::test_a_deleted_document_leaves_the_coverage_ratio_honest` |
| doctor writes nothing into a partner KB (§6.2) | L7 review | `tests/test_doctor.py::test_doctor_writes_nothing_into_a_partner_kb` |
| ...and answers from a partner with no index at all | L7 review | `tests/test_doctor.py::test_a_partner_without_an_index_still_answers` |
| a cross-KB target resolves against the partner's **own** `[kb] id` | L7 review | `tests/test_doctor.py::test_a_cross_kb_target_is_resolved_against_the_partners_own_id`, `::test_a_partner_is_found_by_its_own_id_even_when_the_manifest_declares_another` |
| an incomplete partner walk is never used as evidence of absence | L7 review | `tests/test_doctor.py::test_a_partner_whose_sidecars_cannot_all_be_read_is_not_used_as_evidence`, `::test_a_partner_whose_sources_are_unusable_is_not_used_as_evidence` |
| an internal link is not counted as cross-KB | L7 review | `tests/test_doctor.py::test_an_internal_link_is_not_counted_as_cross_kb` |
| a `~` linked-KB path is warned as absolute | L7 review | `tests/test_doctor.py::test_a_tilde_linked_kb_path_is_warned_as_absolute` |
| an unreadable linked-KB path is a warning, not a traceback | L7 review | `tests/test_doctor.py::test_an_unreadable_linked_kb_path_is_a_warning_not_a_traceback` |
| ...and an unusable partner `roots` entry likewise | L7 review 2 | `tests/test_doctor.py::test_a_partner_roots_entry_that_cannot_be_resolved_is_not_a_traceback` |

## The evaluation is reproducible (G1)

| What must be true | Increment | Where it is checked |
|---|---|---|
| the same index evaluated twice gives the same answers | G1 | `tests/test_search_reproducibility.py::test_outcomes_are_identical_across_repeated_runs` |
| an incremental sync and a `--rebuild` agree question by question | G1 | `tests/test_search_reproducibility.py::test_outcomes_survive_an_incremental_sync_and_rebuild`, and `check.sh`'s `eval-reproducibility` gate over four kinds of corpus change |
| ...and so does a first sync of a fresh clone | G1 | `tests/test_search_reproducibility.py::test_outcomes_survive_a_sync_from_scratch` |
| the two sync paths really do assign different rowids, so the rows above are not vacuous | G1 | `tests/test_search_reproducibility.py::test_the_two_sync_paths_really_do_assign_different_rowids` |
| the vector array is ordered on something a rebuild preserves | G1 | `tests/test_search_reproducibility.py::test_load_vectors_returns_corpus_order_not_rowid_order` |
| a BM25 tie is cut the same way every time | G1 | `tests/test_search_reproducibility.py::test_the_lexical_cut_keeps_the_same_chunk_when_scores_tie` |
| hydration orders two chunks of the *same* document, which the `p.path` tiebreak cannot | G1 | `tests/test_search_reproducibility.py::test_hydration_returns_corpus_order_whatever_order_it_is_asked_in` |
| adding a document does not reorder tied results elsewhere | G1 | `tests/test_search_reproducibility.py::test_a_tied_ranking_is_unmoved_by_documents_added_elsewhere` |
| two machines answer every question the same way | G1 | CI's `eval-cross-machine` and `eval-cross-machine-compare` jobs; `tests/test_check_script.py::test_ci_compares_per_question_outcomes_across_two_operating_systems` asserts both legs are still there |
| the gate is invoked, and can still fail | G1 | `tests/test_check_script.py::test_check_sh_declares_the_eval_reproducibility_gate`, `tests/test_check_script.py::test_ci_runs_the_eval_reproducibility_gate_and_proves_it_can_fail` |

## The manifest compatibility floor (G4)

| What must be true | Increment | Where it is checked |
|---|---|---|
| the floor is read **before** strict validation | G4 | `tests/test_manifest_compat.py::test_the_pre_pass_runs_before_strict_validation` |
| a KB needing a newer Pinakes names both versions | G4 | `tests/test_manifest_compat.py::test_a_manifest_requiring_a_newer_pinakes_names_the_version` |
| an absent floor is not an error | G4 | `tests/test_manifest_compat.py::test_an_absent_requires_pinakes_is_not_an_error` |
| a floor this build exactly meets is accepted | G4 | `tests/test_manifest_compat.py::test_a_floor_this_build_meets_exactly_is_accepted`, `tests/test_manifest_compat.py::test_a_shorter_floor_compares_as_the_same_version`, `tests/test_manifest_compat.py::test_a_longer_floor_of_trailing_zeros_is_the_same_version` |
| only a floor is accepted — no ceiling, no bare version | G4 | `tests/test_manifest_compat.py::test_a_floor_that_is_not_a_lower_bound_is_refused` |
| a version that is not dotted ASCII digits is refused, not compared | G4 | `tests/test_manifest_compat.py::test_a_floor_that_is_not_a_dotted_number_is_refused` |
| the field does not trip the unknown-key check it exists to explain | G4 | `tests/test_manifest_compat.py::test_the_field_does_not_trip_the_unknown_key_check` |
| the pre-pass reports one error, never a second one for the same mistake | G4 | `tests/test_manifest_compat.py::test_a_missing_or_non_table_kb_is_left_to_the_strict_validator` — asserts the strict validator's *exact* wording, because a keyword match survived a deliberately duplicated pre-pass error |
| a version component too long for `int()` is refused, not a traceback | G4 | `tests/test_manifest_compat.py::test_a_version_component_of_absurd_length_is_refused_not_a_traceback` |
| whitespace around the version is refused, as the digits already were | G4 | `tests/test_manifest_compat.py::test_whitespace_around_the_version_is_refused` |
| a leading zero compares as the number it is | G4 | `tests/test_manifest_compat.py::test_a_leading_zero_compares_as_the_number_it_is` |
| a non-string value names the TOML type, never a Python repr | G4 | `tests/test_manifest_compat.py::test_a_non_string_value_names_the_toml_type_not_a_python_repr` |
| an unparseable `__version__` skips the check instead of crashing every command | G4 | `tests/test_manifest_compat.py::test_an_unparseable_own_version_skips_the_check_rather_than_crashing` |
| `pnk init` stamps no floor | G4 | `tests/test_manifest_compat.py::test_the_template_does_not_stamp_a_floor` |

## The golden set, per question (G2)

| What must be true | Increment | Where it is checked |
|---|---|---|
| the committed golden set is well formed, and its two decisive classes are the size the plan set | G2 | `tests/test_eval.py::test_the_committed_golden_set_is_well_formed` |
| per-question outcomes exist as an artifact, and re-score to the same aggregates | G2 | `tests/test_eval.py::test_per_question_outcomes_round_trip` |
| every field a row carries reaches a metric | G2 | `tests/test_eval.py::test_a_row_carries_everything_every_metric_needs` |
| the committed artifact and the committed baseline describe one run | G2 | `tests/test_eval.py::test_the_committed_artifact_describes_the_committed_baseline` |
| growing the set moved no question already in it | G2 | `tests/test_eval.py::test_the_committed_41_score_exactly_their_pre_growth_values` |
| an unknown or absent `kind` is refused, never defaulted | G2 | `tests/test_eval.py::test_an_unknown_kind_is_refused` |
| a repeated id is refused, and an absent one is derived | G2 | `tests/test_eval.py::test_a_repeated_id_is_refused`, `tests/test_eval.py::test_an_absent_id_is_derived_from_the_question` |
| an empty question set skips with a printed reason instead of failing | G2 | `tests/test_eval.py::test_an_empty_question_set_skips_with_a_reason` |
| a file whose `questions` key is missing is still refused, so the skip cannot swallow a typo | G2 | `tests/test_eval.py::test_a_file_with_no_questions_key_is_still_refused` |
| a row missing a field is refused by name, never a bare `KeyError` | G2 | `tests/test_eval.py::test_a_row_missing_a_field_is_refused_by_name` |
| the channel-reachable ceiling is measured before the schema bumps | G2 | `tests/test_eval.py::test_the_reachable_ceiling_probe_needs_no_index_schema_change` |
| the probe answers to the edge set, rather than reporting the same number whatever the graph holds | G2 | `tests/test_eval.py::test_the_reachable_ceiling_probe_answers_to_the_edge_set` |
| a kind that derives zero edges is a key in the census at `0`, never omitted | G2 | `tests/test_eval.py::test_a_kind_that_derives_zero_edges_is_reported_not_omitted` |
| a kind dropped via `--drop` shows `0` in both the printed table and `--json`, alongside every other kind | G2 | `tests/test_eval.py::test_a_dropped_kind_shows_zero_in_both_output_formats` |
| the per-kind edge census reconciles with the `Graph` it describes, for every derived kind | G2 | `tests/test_eval.py::test_edge_census_reconciles_with_the_graph_it_describes` |
| a hop expecting a path the index does not hold refuses the run by name, instead of being counted failing-and-unreachable | G2 | `tests/test_eval.py::test_the_probe_refuses_a_hop_expecting_a_document_the_index_does_not_hold` |
| a `multi-hop` question with no `hops` refuses the run by name, instead of padding the denominator it can never fail | G2 | `tests/test_eval.py::test_the_probe_refuses_a_multi_hop_question_with_no_hops` |
| a `multi-hop` question with one hop refuses too — the shape that moves `liftable` **upward**, against a precondition that is a floor | G2 | `tests/test_eval.py::test_the_probe_refuses_a_multi_hop_question_carrying_a_single_hop` |
| a hop expecting a document the index holds **no chunks** for refuses: a correctly spelled path that can never land or be reached | G2 | `tests/test_eval.py::test_the_probe_refuses_a_hop_expecting_a_document_the_index_holds_no_chunks_for` |
| a hop with an empty `query` refuses, rather than failing on its own terms and being counted | G2 | `tests/test_eval.py::test_the_probe_refuses_a_hop_whose_query_is_empty` |
| a golden set with no `multi-hop` question refuses, rather than printing zeros that read as a measurement | G2 | `tests/test_eval.py::test_the_probe_refuses_a_golden_set_with_no_multi_hop_question_at_all` |
| `filters` that admit no document, or that exclude the last hop's own `expect`, refuse — they are applied to the hop that decides the verdict | G2 | `tests/test_eval.py::test_the_probe_refuses_filters_that_admit_nothing`, `tests/test_eval.py::test_the_probe_refuses_filters_that_exclude_the_last_hops_own_document` |
| a question-level `expect` naming nothing refuses, and the message says it moves no figure — the probe measures hops | G2 | `tests/test_eval.py::test_a_question_level_expect_that_names_nothing_is_refused_and_said_to_move_no_figure` |
| a refusal names the spelling the index holds, and which invisible difference it is — pinned on letter case and a leading `./`; the NFC/NFD branch shares the mechanism and no committed corpus can exercise it | G2 | `tests/test_eval.py::test_a_path_wrong_only_in_case_is_refused_with_the_indexed_spelling` |
| the artifact identifies all three inputs the numbers are a function of — the corpus, the golden set (path + sha256 + counts) and the pipeline down to model and revision | G2 | `tests/test_eval.py::test_the_artifact_records_the_configuration_that_produced_the_numbers` |
| a hop problem on a question the probe never measures says no figure moves, in a whole sentence | G2 | `tests/test_eval.py::test_a_hop_problem_on_a_question_the_probe_never_measures_says_so` |
| a mistyped path is reported once, and never blamed on a healthy `filters:` block | G2 | `tests/test_eval.py::test_a_mistyped_path_is_not_also_blamed_on_the_filters` |
| two hops that are the same retrieval (same `expect`, `query` differing only in case or spacing) refuse — one retrieval written twice clears the hop floor and can move `liftable` upward | G2 | `tests/test_eval.py::test_the_probe_refuses_a_question_whose_two_hops_are_identical` |
| a well-formed golden set is not refused — the control that keeps every refusal from being caused by the environment | G2 | `tests/test_eval.py::test_a_well_formed_golden_set_is_not_refused` |
| `--fake` and `--kb` cannot be combined, so no run can label one corpus's numbers with another's | G2 | `tests/test_eval.py::test_the_probe_refuses_fake_together_with_kb` |
| the output names the KB measured — pinned against a KB that is **not** the demo one, so the test can detect "always names the default" | G2 | `tests/test_eval.py::test_the_probe_names_the_kb_it_measured` |
| a `--fake` run names its own copy and records that a fake backend produced the numbers | G2 | `tests/test_eval.py::test_the_fake_run_names_its_own_copy_and_says_it_is_fake` |

## The node model and the edge set (G3)

| What must be true | Increment | Where it is checked |
|---|---|---|
| a chunk node is keyed on `<doc-ulid>:<ordinal>`, not on `chunks.id` | G3 | `tests/test_edges.py::test_a_chunk_node_is_keyed_on_the_document_ulid_and_ordinal` |
| ...and that key survives a rebuild, which the rowid does not | G3 | `tests/test_edges.py::test_a_chunk_node_key_survives_a_rebuild` |
| heading nodes are scoped per document | G3 | `tests/test_edges.py::test_a_heading_node_is_scoped_to_its_document`, `tests/test_edges.py::test_a_heading_hub_never_connects_two_documents` |
| a document at the KB root still has a directory hub | G3 | `tests/test_edges.py::test_a_document_at_the_kb_root_still_has_a_directory_hub` |
| hub edges stay linear, not quadratic | G3 | `tests/test_edges.py::test_a_shared_tag_produces_linear_not_quadratic_edges` |
| one row per spoke, hub always as `src` | G3 | `tests/test_edges.py::test_a_hub_spoke_is_stored_once_not_twice` |
| a tag repeated in one sidecar is one spoke | G3 | `tests/test_edges.py::test_a_duplicate_tag_in_one_sidecar_is_one_spoke` |
| a hub with a single member is not minted — it connects nothing | G3 | `tests/test_edges.py::test_a_hub_with_a_single_member_is_not_minted` |
| hub damping follows the corpus with no stored degree | G3 | `tests/test_edges.py::test_a_dropped_tag_lowers_the_divisor` |
| weight across a hub is the product of both spokes | G3 | `tests/test_edges.py::test_weight_across_a_hub_is_the_product_of_both_spokes` |
| a hub is entered from a member and expanded from the hub — the two halves are different queries | G3 | `tests/test_edges.py::test_a_hub_is_entered_from_a_member_and_expanded_from_the_hub` |
| `sibling` joins adjacent ordinals, stored lower→higher | G3 | `tests/test_edges.py::test_sibling_edges_join_adjacent_ordinals` |
| ...and never crosses a document | G3 | `tests/test_edges.py::test_a_sibling_edge_never_crosses_a_document` |
| hierarchy is derived by `heading_path` prefix, stored parent→child | G3 | `tests/test_edges.py::test_parent_and_child_follow_heading_path_prefixes` |
| ...on path segments, so a heading that is a string prefix is not a parent | G3 | `tests/test_edges.py::test_a_sibling_heading_that_is_a_string_prefix_is_not_a_parent` |
| `membership` runs document → chunk | G3 | `tests/test_edges.py::test_membership_runs_document_to_chunk` |
| a symmetric edge is reachable from both ends | G3 | `tests/test_edges.py::test_a_symmetric_edge_is_reachable_from_both_ends` |
| a soft-deleted document leaves no edges, and empties its hubs | G3 | `tests/test_edges.py::test_a_soft_deleted_document_leaves_no_edges` |
| an authored edge is read from `links` and never copied into `edges` | G3 | `tests/test_edges.py::test_an_authored_edge_is_read_from_links_and_never_stored_in_edges` |
| ...keeping the direction the sidecar wrote it | G3 | `tests/test_edges.py::test_an_authored_row_keeps_the_direction_the_sidecar_wrote_it` |
| ...and a cross-KB row never enters the channel, in either direction | G3 | `tests/test_edges.py::test_a_cross_kb_authored_row_never_enters_the_channel` |
| the derived kind set is selectable at read time, so G5's arms need no rebuild | G3 | `tests/test_edges.py::test_dropping_a_kind_removes_it_from_every_read`, `tests/test_edges.py::test_dropping_authored_removes_it_without_a_rederivation` |
| an unknown kind name is refused rather than dropping nothing | G3 | `tests/test_edges.py::test_an_unknown_kind_name_is_refused_rather_than_dropping_nothing` |
| every kind is a census key, even at zero | G3 | `tests/test_edges.py::test_every_kind_is_a_census_key_even_at_zero` |
| the sync report prints every kind and what deriving them cost | G3 | `tests/test_edges.py::test_the_sync_report_prints_every_kind_with_its_wall_clock` |
| the traversal surface returns documents only, with a structural graph present to leak | G3 | `tests/test_edges.py::test_the_traversal_surface_returns_no_structural_nodes` |
| `pnk links --json` on both corpora is unchanged across the schema bump | G3 | `tests/test_links_surface.py::test_the_authored_links_surface_is_unchanged_by_the_schema_bump`, `tests/test_links_surface.py::test_the_fixture_covers_both_corpora_and_holds_real_neighbours` |
| a `schema_version` 2 index is refused with a remedy | G3 | `tests/test_edges.py::test_a_schema_version_2_index_is_refused_with_its_remedy`, `tests/test_store.py::test_schema_version_is_3_for_g3s_node_and_edge_tables` |
| the stored edge set agrees with the probe the go decision was taken on | G3 | `tests/test_edges.py::test_the_stored_edge_set_agrees_with_the_probe_the_decision_was_taken_on` |
| a forked KB sharing a document ULID does not forge a local authored edge — found by mutation, caught by nothing | G3 | `tests/test_edges.py::test_a_forked_kb_sharing_a_document_ulid_does_not_forge_a_local_authored_edge` |
| the hierarchy lookup derives exactly the naive prefix relation it replaced | G3 | `tests/test_edges.py::test_hierarchy_matches_the_naive_prefix_predicate` |
| asking for `authored` without the local KB is refused, never silently dropped | G3 | `tests/test_edges.py::test_asking_for_authored_without_the_local_kb_is_refused` |
| an empty tag is not a shared value, and a repeated one does not inflate a hub's size | G3 | `tests/test_edges.py::test_an_empty_tag_is_not_a_shared_value`, `tests/test_edges.py::test_one_document_repeating_a_tag_mints_no_hub` |
| `co-located` is the immediate directory, never an ancestor | G3 | `tests/test_edges.py::test_a_nested_directory_is_its_own_hub` |
| a heading containing the path separator is a measured bound, not a belief | G3 | `tests/test_edges.py::test_a_heading_containing_the_separator_is_a_known_bound` |
| `parent-child`'s arity — the product of two sections' chunk counts — is pinned rather than discovered | G3 | `tests/test_edges.py::test_the_hierarchy_row_count_is_pinned_because_it_is_the_product_of_two_sections` |
| the node- and edge-kind constants match the DDL's CHECK constraints, in both directions | G3 | `tests/test_store.py::test_constants_match_the_check_constraints` |
| the deriver is on the free path, and gate 4 reaches it | G3 | `tests/test_paid_path.py::test_the_free_path_never_imports_the_paid_client` |

## The expansion channel and its gate (G5)

| What must be true | Increment | Where it is checked |
|---|---|---|
| `expand` surfaces a document two-list fusion does not return | G5 | `tests/test_graph_channel.py::test_expand_surfaces_a_document_fusion_alone_does_not` |
| an empty edge set reproduces two-list fusion **exactly**, not approximately | G5 | `tests/test_graph_channel.py::test_an_empty_edge_set_reproduces_two_list_fusion_exactly` |
| `off` issues no query against `nodes` or `edges` at all | G5 | `tests/test_graph_channel.py::test_off_issues_no_traversal_query` |
| a same-document chunk reachable **only** by membership never appears | G5 | `tests/test_graph_channel.py::test_a_chunk_reachable_only_by_membership_never_appears` |
| ...and one also reachable by `sibling` is not excluded — the "only" is load-bearing | G5 | `tests/test_graph_channel.py::test_a_same_document_chunk_reachable_by_sibling_is_not_excluded` |
| membership neighbours are dropped before the cut, so they never spend fan-out budget | G5 | `tests/test_graph_channel.py::test_membership_neighbours_do_not_consume_the_fanout_budget` |
| a root is expanded but never emitted — its slot belongs to a chunk fusion has not seen | G5 | `tests/test_graph_channel.py::test_a_root_is_expanded_but_never_emitted` |
| ...and it is dropped **before** the fan-out cut, so it never spends a slot it is then discarded from | G5 | `tests/test_graph_channel.py::test_a_root_does_not_consume_a_fanout_slot` |
| the channel ranks on the cosines `search` computed, not on a map it never received | G5 | `tests/test_graph_channel.py::test_the_channel_ranks_by_the_cosine_search_computed` |
| a two-hop chunk outranks a one-hop one when the query says so, so depth 2 reaches the *output* | G5 | `tests/test_graph_channel.py::test_a_two_hop_chunk_outranks_a_one_hop_one_when_the_query_says_so` |
| ...and link distance still breaks a tie the query cannot | G5 | `tests/test_graph_channel.py::test_distance_breaks_a_tie_the_query_cannot` |
| a document never passes through to itself, even when it is not a root | G5 | `tests/test_graph_channel.py::test_a_document_never_passes_through_to_itself` |
| a root's own document never contributes its chunks, at any depth — a clause 18 mutants left standing | G5 | `tests/test_graph_channel.py::test_a_root_document_never_contributes_its_chunks_at_any_depth` |
| `pnk links --json` is byte-identical with the channel on (decision 16) | G5 | `tests/test_graph_channel.py::test_pnk_links_output_is_unchanged_with_the_channel_on` |
| the gate's two edge-set variants differ in cardinality, so the split discriminates | G5 | `tests/test_graph_channel.py::test_the_gate_is_computed_with_and_without_authored_edges` |
| "without authored" is the whole kind, whatever a row's `origin` | G5 | `tests/test_graph_channel.py::test_dropping_authored_is_every_links_row_regardless_of_origin` |
| the sign test reproduces the plan's table **and** refuses the row above each threshold | G5 | `tests/test_graph_channel.py::test_the_sign_test_reproduces_the_plans_table_and_the_rows_below_it` |
| a rise in `false_confidence` stops the gate — clause 2 cannot see it | G5 | `tests/test_graph_channel.py::test_a_rise_in_false_confidence_stops_the_gate` |
| a newly-found question reported at LOW does not veto the win clause 1 demands | G5 | `tests/test_graph_channel.py::test_a_newly_found_question_at_low_confidence_does_not_veto_the_win` |
| ...while a question that *lost* confidence does stop it — the other half of the decomposition | G5 | `tests/test_graph_channel.py::test_a_question_that_lost_confidence_stops_the_gate` |
| a drop in `confidence_coverage` stops the gate | G5 | `tests/test_graph_channel.py::test_a_drop_in_confidence_coverage_stops_the_gate` |
| **both** runs must pass; one green run licenses nothing | G5 | `tests/test_graph_channel.py::test_the_gate_requires_both_runs_to_pass` |
| a class vanishing stops the gate | G5 | `tests/test_graph_channel.py::test_a_class_vanishing_stops_the_gate` |
| an unpaired question set is refused before any clause is scored | G5 | `tests/test_graph_channel.py::test_an_unpaired_question_set_is_refused_before_any_clause_is_scored` |
| a leg is identified by its header, never its filename | G5 | `tests/test_graph_channel.py::test_a_leg_that_is_not_the_leg_it_was_passed_as_is_refused`, `tests/test_graph_channel.py::test_a_without_authored_leg_that_kept_authored_edges_is_refused` |
| ...and a gate that should pass does pass, so the four above are not green against a gate that refuses everything | G5 | `tests/test_graph_channel.py::test_a_gate_that_passes_reports_that_it_passes` |
| `graph_channel` defaults to `off`, is not stamped into the template, and refuses an unknown name | G5 | `tests/test_graph_channel.py::test_the_default_is_off`, `tests/test_graph_channel.py::test_the_channel_setting_is_not_stamped_into_the_template`, `tests/test_graph_channel.py::test_an_unknown_channel_name_is_refused` |
| a soft-deleted document never reaches the channel — the other end of G3's reaping | G5 | `tests/test_graph_channel.py::test_a_soft_deleted_document_never_reaches_the_channel` |
| an index with no derived nodes walks empty rather than failing | G5 | `tests/test_graph_channel.py::test_a_kb_synced_before_the_edge_set_existed_walks_empty` |
| the committed corpora still measure the two-list pipeline | G5 | `tests/test_graph_channel.py::test_the_corpora_are_left_alone`, `tests/test_graph_channel.py::test_the_workspace_helper_copies_rather_than_edits` |

## Edge-hub reporting (G6)

| What must be true | Increment | Where it is checked |
|---|---|---|
| `pnk doctor` reports the highest-degree structural edge hubs, highest first | G6 | `tests/test_doctor.py::test_edge_hubs_are_reported_highest_degree_first` |
| a KB with no hub edges reports `none`, cleanly | G6 | `tests/test_doctor.py::test_a_kb_with_no_edges_reports_none` |
| a `co-located` (`dir`) hub is named by its KB-root-relative path, not resolved through a lookup | G6 | `tests/test_doctor.py::test_a_directory_hub_is_named_by_its_kb_root_relative_path` |
| a degree tie between two **different** hub kinds breaks on `kind` before `key` — `nodes` is `UNIQUE (kind, key)`, so `key` alone is not a total order | G6 | `tests/test_doctor.py::test_a_cross_kind_tie_breaks_on_kind_before_key` |
| a degree tie breaks on `(kind, key)`, and the hubs it pushes out of the sample are still counted | G6 | `tests/test_doctor.py::test_a_degree_tie_breaks_deterministically_and_the_rest_are_counted` |
| a hub is named for a human — a document path, never a bare `nodes.id` | G6 | `tests/test_doctor.py::test_an_edge_hub_report_names_a_document_path_never_a_bare_node_id` |

## Release machinery

| What must be true | Increment | Where it is checked |
|---|---|---|
| the demo KB's eval numbers do not move | I3b | `make eval` against `tests/demo-kb/eval/baseline.json` (the committed file is the assertion) |
| the free-vs-paid delta is present and dated in DESIGN §9 | I9 | `tests/test_verification.py::test_the_measured_paid_delta_is_present_and_dated` |
| a fragment cannot be malformed or miscategorised | — | `tests/test_fragments.py::test_an_unknown_category_is_refused_by_name`, `check.sh` gate |
| two agents editing shared documents are told before they merge | — | `tests/test_shared_file_overlap.py::test_uncommitted_work_counts`, `check.sh` gate |
| a core-only wheel still installs and runs | I9 | CI `build` job smoke step |
| the shipped wheel carries `prices.toml` and `floors.toml` | I9 | CI `build` job smoke step |
| `docs/STATUS.md` line 3 names `pinakes.__version__`, in the exact `**Latest release: x.y.z**` shape | fix | `tests/test_status_header_gate.py::test_the_real_status_file_agrees_with_the_real_version`, `tests/test_status_header_gate.py::test_agreeing_versions_pass` |
| a drifted header fails naming both versions and the file | fix | `tests/test_status_header_gate.py::test_disagreeing_versions_fail_naming_both` |
| deleting, moving or reformatting the header cannot silence the gate | fix | `tests/test_status_header_gate.py::test_a_missing_line_fails`, `tests/test_status_header_gate.py::test_a_reformatted_line_fails`, `tests/test_status_header_gate.py::test_the_header_on_the_wrong_line_fails` |
| landing refuses when the default branch's sha did not move — the merge that reports success and lands nothing | fix | `tests/test_land.py::test_refuses_when_the_default_branch_did_not_move`, `tests/test_land.py::test_cleanup_does_not_run_when_the_landing_was_refused` |
| landing merges in the primary checkout even when invoked from the feature worktree | fix | `tests/test_land.py::test_merges_in_the_primary_checkout_even_when_invoked_from_the_feature_worktree` |
| landing cannot fold uncommitted work into the merge, or land onto the wrong branch | fix | `tests/test_land.py::test_refuses_a_dirty_primary_checkout`, `tests/test_land.py::test_refuses_to_merge_the_default_branch_into_itself` |
| `--cleanup` removes the worktree and **both** copies of the branch | fix | `tests/test_land.py::test_cleanup_removes_the_worktree_and_both_copies_of_the_branch` |
| `--cleanup-only` destroys nothing unless the branch is an ancestor of `origin/main` — "looks merged" is not "landed" | fix | `tests/test_land.py::test_cleanup_only_refuses_a_branch_whose_content_never_landed`, `tests/test_land.py::test_cleanup_only_removes_a_branch_that_landed_earlier` |
| the status-header gate is invoked, and can still fail | fix | `tests/test_check_script.py::test_check_sh_declares_the_status_header_gate`, `tests/test_check_script.py::test_ci_runs_the_status_header_gate_and_proves_it_can_fail` |

## The source walk stays inside the KB (0.7.1)

Three defects live since before 0.5.0 let `[sources] include` mint sidecars **outside** the KB —
against the `docs/` belongs to the user invariant. A fourth was found by a test written to pin
*correct* behaviour. The rows below were added on 20260804: 0.7.1 shipped seventeen tests and
touched this file not at all, which `tests/test_verification.py` cannot detect — it walks from this
document to the tests, proving no row is fiction, and structurally cannot prove no guarantee is
un-rowed.

| What must be true | Increment | Where it is checked |
|---|---|---|
| an `include` pattern that climbs out of the KB is refused at load | 0.7.1 | `tests/test_sync.py::test_an_include_pattern_that_climbs_out_of_the_kb_is_refused_at_load` |
| an absolute `include` pattern is a named `ManifestError`, never a traceback | 0.7.1 | `tests/test_sync.py::test_an_absolute_include_pattern_is_a_manifest_error_not_a_traceback` |
| a symlinked directory cannot carry the walk out of the KB | 0.7.1 | `tests/test_sync.py::test_a_symlinked_directory_cannot_carry_the_walk_out_of_the_kb` |
| a symlinked document *inside* the KB is still ingested — containment is not a ban on symlinks | 0.7.1 | `tests/test_sync.py::test_a_symlinked_document_inside_the_kb_is_still_ingested` |
| a `..` pattern that stays inside the KB is legal, and one file reached two legal ways is one document | 0.7.1 | `tests/test_sync.py::test_a_dot_dot_pattern_that_stays_inside_the_kb_is_accepted`, `tests/test_sync.py::test_one_file_reached_by_two_legal_spellings_is_one_document`, `tests/test_sync.py::test_the_same_document_is_ingested_by_a_fixed_and_a_globbed_pattern_alike` |
| a leading glob, or a `**` before the `..`, does not defeat the static refusal | 0.7.1 | `tests/test_sync.py::test_a_leading_glob_does_not_defeat_the_static_refusal`, `tests/test_sync.py::test_a_double_star_before_a_dot_dot_does_not_defeat_the_refusal` |
| an escaping pattern is refused **without enumerating the tree**, and a symlinked escape stops the walk rather than walking it | 0.7.1 | `tests/test_sync.py::test_an_escaping_pattern_is_refused_without_enumerating_the_tree`, `tests/test_sync.py::test_a_symlinked_escape_stops_the_walk_rather_than_enumerating_the_tree` |
| an escaping pattern matching only a directory is still caught | 0.7.1 | `tests/test_sync.py::test_an_escaping_pattern_that_matches_only_a_directory_is_still_caught` |
| the escape is reported once per pattern, never once per file | 0.7.1 | `tests/test_sync.py::test_the_escape_is_reported_once_per_pattern_not_once_per_file` |
| an escape under one root does not drop documents under another | 0.7.1 | `tests/test_sync.py::test_an_escape_under_one_root_does_not_drop_documents_under_another` |
| an `exclude` pattern may contain `..`, and a root that does not exist yet still loads | 0.7.1 | `tests/test_sync.py::test_an_excluded_pattern_may_contain_dot_dot`, `tests/test_sync.py::test_a_root_that_does_not_exist_yet_still_loads` |
| the density gate survives a root reached through a symlinked parent | 0.7.1 | `tests/test_partner_kb.py::test_the_gate_survives_a_root_reached_through_a_symlinked_parent` |
