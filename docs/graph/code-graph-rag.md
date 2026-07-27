# code-graph-rag — investigation notes

**Repo:** https://github.com/vitali87/code-graph-rag · **Stars:** ~2.4k · **License:** MIT · **Investigated:** 20260726 08:52

## What it is

"The ultimate RAG for your monorepo": parses a multi-language codebase (Python, TS/JS, Rust, Go,
Java, C, C++, C#, PHP, Lua, Dart, partial Ruby) with Tree-sitter, builds a structural knowledge
graph in **Memgraph**, and exposes it to agents two ways: an interactive pydantic-ai orchestrator
CLI (`cgr`) and an **MCP server** for Claude Code and other clients. Created 2025-06, pushed
2026-07-24 (actively maintained, v0.0.502, 12 open issues). Same pattern as Pinakes' R6 bet, in
production for code: deterministic structural index, agent does the traversal.

## How the graph is built (deterministic, zero-LLM)

`codebase_rag/graph_updater.py`, class `GraphUpdater.run()` — a multi-pass, **LLM-free** pipeline:

1. **Structure pass** — `factory.structure_processor.identify_structure()`: Project/Folder/File/
   Package/Module hierarchy.
2. **Definitions pass** — `_process_files()`: Tree-sitter `.scm` queries extract Class, Function,
   Method nodes (optional Roslyn/libclang frontends for C#/C++ accuracy — compilers, not LLMs).
3. **Calls pass** — `_process_function_calls()`: call sites resolved against a
   `FunctionRegistryTrie` of qualified names plus a deterministic type-inference engine
   (`parsers/type_inference.py`, `parsers/call_resolver.py`).
4. **Embeddings pass (optional)** — `_generate_semantic_embeddings()` via `embedder.py`.

Node labels: `Project`, `Folder`, `File`, `Module`, `Class`, `Function`, `Method`, plus ast-grep
finding nodes (`Pattern`, `CodeSmell`, `SecurityIssue`). Edge types: `CONTAINS`, `DEFINES`,
`DEFINES_METHOD`, `CALLS`, `IMPORTS`, `INHERITS`, `IMPLEMENTS`, `OVERRIDES`, `FLOWS_TO`
(taint/data-flow), `EXPOSES`/`RESOLVES_TO` (HTTP endpoints).

**Incremental updates** (`UPDATE_REPOSITORY` tool): MD5 per-file hash cache (`.cgr_hash_cache`,
`_load_hash_cache`/`_save_hash_cache`, whole-run skip via `_is_already_in_sync()`). For a changed
file: `_capture_inbound_edges()` snapshots edges arriving from *unchanged* files, the file's
subgraph is dropped (`_delete_module_entities`), re-parsed, then `_restore_inbound_edges()` replays
the snapshot; `_rehydrate_registry_from_graph()` reloads unchanged files' symbols from the graph so
cross-file calls still resolve.

## The tool surface, verb by verb

`codebase_rag/mcp/tools.py` + `mcp/server.py` (raw MCP SDK `Server`, stdio or HTTP+bearer;
results JSON-serialized into `TextContent`). Fifteen tools:

| Tool | Params | Returns |
|---|---|---|
| `query_code_graph` | `natural_language_query` | `{results, query_used, summary, error}` |
| `get_code_snippet` | `qualified_name` | source + `file_path`, `line_start/end`, `docstring`, `found` |
| `semantic_search` | `natural_language_query`, `top_k=5` | node id, qualified_name, type, score |
| `structural_search` / `structural_replace` | ast-grep `pattern` (+`rewrite`, `dry_run=true`) | match/diff text |
| `index_repository` / `update_repository` | — | status string |
| `read_file` / `write_file` / `surgical_replace_code` / `list_directory` | paths etc. | text |
| `list_projects` / `delete_project` / `wipe_database(confirm)` | — | typed result dicts |
| `ask_agent` | `question` | delegates to internal pydantic-ai orchestrator |

**The central graph verb is NL→Cypher, not typed navigation.** There is no `get_callers` /
`get_definition`; the agent asks in English, `CypherGenerator` (`services/llm.py`, a pydantic-ai
`Agent`; Gemini/OpenAI/Ollama providers, Ollama gets a special `build_local_cypher_system_prompt()`)
emits Cypher against a schema prompt (`prompts.py`), then the server defends itself with
bolt-on validators: `_validate_cypher_read_only()`, `_validate_no_unbounded_paths()`,
`_validate_call_procedures()`. The prompt itself must legislate what a typed API would make
impossible: "NEVER use unbounded variable-length paths … always cap", "ALWAYS add LIMIT 50",
"Do NOT return whole nodes", "use ENDS WITH" for short names, "ALWAYS constrain … STARTS WITH
'<projectName>'". Results are double-capped: row cap (`QUERY_RESULT_ROW_CAP`) then token budget
(`truncate_results_by_tokens`), with the `summary` field telling the agent truncation happened
(`tools/codebase_query.py`, `query_codebase_knowledge_graph`).

Awkward for the caller: every graph question costs an extra LLM round-trip, can fail with
`QUERY_SUMMARY_TRANSLATION_FAILED`, and the returned Cypher (`query_used`) is the only way the
agent can debug a miss. What works well: `get_code_snippet(qualified_name)` — the one *typed*
verb — and the two-step "search returns identifiers, a second call fetches content" shape.

## How graph and text retrieval combine

Embeddings are optional (`[semantic]` extra): UniXcoder locally (torch+transformers) or OpenAI
API (`embedder.py`); vectors live in **Qdrant or Milvus** (`vector_store.py`,
`VectorStoreBackend`). `tools/semantic_search.py::semantic_code_search()` embeds the query,
`search_embeddings()` returns node ids + scores, then **enriches hits from the graph**
(`build_nodes_by_ids_query`) so results carry qualified names/types the agent can feed straight
into `get_code_snippet` or a graph query. Project scoping is client-side filtering with adaptive
over-fetch (`_search_project_scoped`, `fetch_k = top_k * _PROJECT_OVERFETCH`, cap 1024). There is
**no fused ranking** (no RRF, no reranker): graph query, semantic search, and ast-grep are three
separate tools; combination happens in the calling agent's head. Routing is likewise 100% the
agent's decision, steered only by tool-description wording (`tools/tool_descriptions.py`):
"describing their purpose" (semantic) vs "by its qualified name" (exact) vs "AST pattern …
not text/regex" (structural). No code-side router exists in MCP mode.

## Cost profile

- **Index time: zero LLM.** Tree-sitter + registries; embeddings optional and local-capable.
- **Query time: not free by default** — every `query_code_graph` call runs `CypherGenerator`
  (paid API unless configured for Ollama). Semantic search is free with UniXcoder.
- **Infra: heavy.** Docker'd Memgraph required, Qdrant/Milvus for vectors, `pydantic-ai` + `mcp` +
  `pymgclient` core deps, torch in the `[semantic]` extra, per-language tree-sitter grammars in
  `[treesitter-full]`. Python ≥3.12.

## What's interesting for Pinakes

- Live validation of R6 at 2.4k stars: deterministic structural index + agent-driven navigation
  over MCP works, for a domain (code) with far denser edge structure than documents.
- The incremental story is the strongest engineering in the repo: hash-gated reparse with
  inbound-edge capture/restore is exactly the "stable IDs make edges survivable" property Pinakes
  gets from permanent ULIDs.
- Their guardrail list is an empirical catalogue of how agents misuse an open graph query surface:
  unbounded traversals, whole-node dumps, unscoped matches, unlimited listings. Every one is a
  design input for `pinakes_links`.
- Tool descriptions are the routing layer; the agent picks the verb. Matches Pinakes' plan of no
  in-engine router.

## What to steal (esp. for pinakes_links)

- **Typed verbs instead of a query language.** Their validators + prompt rules exist only because
  the verb is open-ended. `pinakes_links(doc_id, rel?, direction?, depth?)` encodes read-only,
  bounded, scoped access *in the signature*. Keep it; add a **hard server-side depth cap** (their
  "never unbounded paths" rule, enforced in code, not in a prompt).
- **Double-capped results with an honest summary.** Row cap → token budget → a `summary`/
  `truncated` field so the agent knows to narrow, not retry. Apply to `pinakes_search` and
  `pinakes_links` alike.
- **Two-step retrieval shape.** Search/links return IDs + light metadata (title, rel, path);
  `pinakes_get` fetches content. They do exactly this (`semantic_search` → `get_code_snippet`)
  and it composes well.
- **Cross-index enrichment.** Vector hits come back graph-annotated so the next hop needs no join
  by the agent. Pinakes analog: `pinakes_search` hits could carry link counts / rel types present,
  making `pinakes_links` an informed next hop instead of a blind one.
- **Hash-gated incremental reindex with edge preservation** — reparse only changed docs, keep
  inbound links across reindex (they key on qualified names; Pinakes' ULIDs are strictly stronger).

## What to avoid / doesn't fit

- **NL→Cypher inside the server.** An LLM embedded in a tool call breaks the free path, adds a
  failure mode (`LLMGenerationError`), and duplicates intelligence the calling agent already has.
- **`ask_agent` / internal orchestrator.** An agent inside the server is the anti-R6: it competes
  with the caller. Pinakes exposes verbs only.
- **Infra weight.** Docker Memgraph + Qdrant/Milvus + torch vs Pinakes' single SQLite file. Their
  stack is justified by open Cypher traversals; recursive CTEs over a `links` table cover Pinakes'
  depth-bounded needs.
- **Write tools in the same surface** (`write_file`, `surgical_replace_code`, `wipe_database`).
  Pinakes' `docs/` belongs to the user; keep the MCP surface read-only.
- Client-side over-fetch filtering for scoping — a workaround for vector-store filter limits;
  SQLite WHERE clauses make it unnecessary.

## Key sources

- `codebase_rag/mcp/tools.py`, `mcp/server.py` — tool registry, transports, serialization
- `codebase_rag/graph_updater.py` — `GraphUpdater.run()`, passes, hash cache, edge capture/restore
- `codebase_rag/tools/codebase_query.py` — `query_codebase_knowledge_graph`, caps + summary
- `codebase_rag/services/llm.py` — `CypherGenerator`, validators, `create_rag_orchestrator`
- `codebase_rag/prompts.py` — schema-for-LLM + Cypher rules; `tools/tool_descriptions.py` — routing
- `codebase_rag/embedder.py`, `vector_store.py`, `tools/semantic_search.py` — UniXcoder/OpenAI,
  Qdrant/Milvus, graph enrichment
- `pyproject.toml` — deps, extras; GitHub API — stars 2,355, MIT, pushed 2026-07-24
