# Testing Audit

## Scope

- Product baseline: `1040` collected items in the legacy layout before this refactor.
- Benchmark baseline: `91` collected items after repairing the internal `FastAgenticSearchHarness` import so `benchmark/tests` can collect cleanly.
- Product target layout: `tests/<domain>/test_<behavior>_<level>.py`, with `unit` / `integration` / `contract` / `smoke` markers applied from the filename suffix.
- Benchmark target layout: `benchmark/tests/{analysis,cli,datasets,docs,runner}` and a dedicated CI job outside the default product `testpaths`.

## Product Tests

| path | collected_count | domain | level | decision | reason | replacement_coverage |
| --- | ---: | --- | --- | --- | --- | --- |
| `tests/contract/test_health_indicators.py` | 8 | `server` | `contract` | `delete` | 純 health / existence / minimal-input matrix，和更強的 contract 與 integration 路徑重複。 | `tests/mcp/test_mcp_compliance_contract.py`; `tests/server/test_runtime_integration.py`; `tests/server/test_dotenv_registration_integration.py` |
| `tests/contract/test_mcp_compliance.py` | 16 | `mcp` | `contract` | `keep+move` | 保護 MCP tool/resource schema、annotations、response contract 與 visibility 邊界。 | `tests/mcp/test_mcp_compliance_contract.py` |
| `tests/integration/test_agentic_retrieval_integration.py` | 12 | `retrieval` | `integration` | `keep+move` | 保留 retrieval orchestration、hint policy、backend dispatch 與 contract。 | `tests/retrieval/test_agentic_retrieval_integration.py` |
| `tests/integration/test_cloud_operations.py` | 18 | `cloud` | `integration` | `keep+move` | 保留 sync/search/clear/info 的真實 state transition 與 client error handling。 | `tests/cloud/test_cloud_operations_integration.py` |
| `tests/integration/test_dotenv_tool_registration.py` | 1 | `server` | `integration` | `keep+move` | 保留 dotenv 對 tool registration 的整合路徑。 | `tests/server/test_dotenv_registration_integration.py` |
| `tests/integration/test_lsp_handler.py` | 23 | `lsp` | `integration` | `keep+move` | 保留 query params、manager、workspace sync 與 timeout 行為。 | `tests/lsp/test_handler_integration.py` |
| `tests/integration/test_lsp_module.py` | 0 | `lsp` | `integration` | `delete` | 空檔案，沒有任何 collected coverage。 | `n/a (empty file)` |
| `tests/integration/test_lsp_search_symbol.py` | 10 | `lsp` | `integration` | `keep+move` | 保留 search symbol request / parse / no-result 路徑。 | `tests/lsp/test_search_symbol_integration.py` |
| `tests/integration/test_middleware_roots.py` | 14 | `middleware` | `integration` | `keep+move` | 保留 roots cache invalidation 與 session-scoped state transition。 | `tests/middleware/test_roots_integration.py` |
| `tests/integration/test_search_commands.py` | 16 | `search` | `integration` | `keep+move` | 保留 grep/glob/bash/view 的真實工具呼叫流程。 | `tests/search/test_commands_integration.py` |
| `tests/integration/test_server.py` | 18 | `server` | `integration` | `keep+move+trim` | 只保留 bootstrap、實際 tool call、`main()` transport 路徑；registration/schema existence 改由 contract suite 承接。 | `tests/server/test_runtime_integration.py`; `tests/mcp/test_mcp_compliance_contract.py` |
| `tests/smoke/test_server_init.py` | 1 | `server` | `smoke` | `delete` | 與 `build_server` bootstrap coverage 重複，屬於純 existence smoke。 | `tests/server/test_runtime_integration.py` |
| `tests/smoke/test_smoke.py` | 2 | `entrypoints` | `smoke` | `keep+move` | 保留 CLI help / dashboard import 的最小 smoke 契約。 | `tests/entrypoints/test_cli_help_smoke.py` |
| `tests/unit/test_agentic_retrieval.py` | 20 | `retrieval` | `unit` | `keep+move` | 保留 semantic hints formatting 與 retrieval core logic。 | `tests/retrieval/test_agentic_retrieval_unit.py` |
| `tests/unit/test_apply.py` | 9 | `apply` | `unit` | `keep+move` | 保留 Apply client request/response/retry 路徑。 | `tests/apply/test_apply_unit.py` |
| `tests/unit/test_apply_client.py` | 5 | `apply` | `unit` | `keep+move` | 保留 OpenAI-compatible apply prompt envelope。 | `tests/apply/test_apply_client_unit.py` |
| `tests/unit/test_apply_core.py` | 28 | `apply` | `unit` | `keep+move` | 保留 conflict、blast radius、symbol preservation 與 progress reporting 核心守門。 | `tests/apply/test_apply_core_unit.py` |
| `tests/unit/test_async_non_blocking.py` | 1 | `search` | `unit` | `keep+move` | 保留 non-blocking async contract。 | `tests/search/test_async_non_blocking_unit.py` |
| `tests/unit/test_base_dir.py` | 32 | `config` | `unit` | `keep+move` | 保留 base-dir validation 與 path containment 邊界。 | `tests/config/test_base_dir_unit.py` |
| `tests/unit/test_chunkhound.py` | 19 | `retrieval` | `unit` | `keep+move` | 保留 ChunkHound parsing、index 與 search 行為。 | `tests/retrieval/test_chunkhound_unit.py` |
| `tests/unit/test_client_exceptions.py` | 1 | `clients` | `unit` | `keep+move` | 保留 OpenAI-style error parsing。 | `tests/clients/test_client_exceptions_unit.py` |
| `tests/unit/test_cloud_search.py` | 4 | `cloud` | `unit` | `keep+move` | 保留 cloud search retry / fallback 邏輯。 | `tests/cloud/test_search_unit.py` |
| `tests/unit/test_cloud_status.py` | 7 | `cloud` | `unit` | `keep+move` | 保留 cloud status readiness / hints usability 判定。 | `tests/cloud/test_status_unit.py` |
| `tests/unit/test_codanna.py` | 23 | `retrieval` | `unit` | `keep+move` | 保留 Codanna index / search / freshness 路徑。 | `tests/retrieval/test_codanna_unit.py` |
| `tests/unit/test_config.py` | 7 | `config` | `unit` | `keep+move` | 保留 env/config parsing 與 base_dir 設定。 | `tests/config/test_config_unit.py` |
| `tests/unit/test_dashboard_log_path.py` | 1 | `dashboard` | `unit` | `keep+move` | 保留 dashboard log path resolution。 | `tests/dashboard/test_log_path_unit.py` |
| `tests/unit/test_encoding.py` | 16 | `encoding` | `unit` | `keep+move` | 保留 encoding detection、set/reset 與 BOM 路徑。 | `tests/encoding/test_encoding_unit.py` |
| `tests/unit/test_encoding_detection_order.py` | 1 | `encoding` | `unit` | `keep+move` | 保留 detection precedence。 | `tests/encoding/test_detection_order_unit.py` |
| `tests/unit/test_entrypoints.py` | 2 | `entrypoints` | `unit` | `keep+move` | 保留 Python entrypoint 對 `server.main` / `dashboard.main` 的綁定。 | `tests/entrypoints/test_python_entrypoints_unit.py` |
| `tests/unit/test_freshness.py` | 8 | `retrieval` | `unit` | `keep+move` | 保留 local index freshness classifier。 | `tests/retrieval/test_freshness_unit.py` |
| `tests/unit/test_harness_messages.py` | 17 | `search` | `unit` | `keep+move` | 保留 harness message sanitation 與 tool-call repair。 | `tests/search/test_harness_messages_unit.py` |
| `tests/unit/test_index_state.py` | 17 | `retrieval` | `unit` | `keep+move` | 保留 indexed-head state read/write 與 transition。 | `tests/retrieval/test_index_state_unit.py` |
| `tests/unit/test_index_status_probe.py` | 6 | `retrieval` | `unit` | `keep+move` | 保留 index status probe 邏輯。 | `tests/retrieval/test_index_status_probe_unit.py` |
| `tests/unit/test_lsp_core.py` | 24 | `lsp` | `unit` | `keep+move` | 保留 core LSP data model、response 與 manager 基本行為。 | `tests/lsp/test_core_unit.py` |
| `tests/unit/test_lsp_languages.py` | 4 | `lsp` | `unit` | `keep+move` | 保留 language/server detection。 | `tests/lsp/test_languages_unit.py` |
| `tests/unit/test_lsp_logging.py` | 15 | `lsp` | `unit` | `keep+move` | 保留 LSP logging / pool logging。 | `tests/lsp/test_logging_unit.py` |
| `tests/unit/test_lsp_multi_language.py` | 2 | `lsp` | `unit` | `keep+move` | 保留 multi-language LSP client selection。 | `tests/lsp/test_multi_language_unit.py` |
| `tests/unit/test_lsp_protocol.py` | 18 | `lsp` | `unit` | `keep+move` | 保留 JSON-RPC / protocol encode-decode。 | `tests/lsp/test_protocol_unit.py` |
| `tests/unit/test_lsp_response_parsers.py` | 0 | `lsp` | `unit` | `delete` | 空檔案，沒有任何 collected coverage。 | `n/a (empty file)` |
| `tests/unit/test_lsp_transport_runtime.py` | 6 | `lsp` | `unit` | `keep+move` | 保留 transport runtime 與 command resolution。 | `tests/lsp/test_transport_runtime_unit.py` |
| `tests/unit/test_observability_filters.py` | 6 | `observability` | `unit` | `keep+move` | 保留 event/trace log filtering。 | `tests/observability/test_filters_unit.py` |
| `tests/unit/test_observed_grep_parsing.py` | 3 | `search` | `unit` | `keep+move` | 保留 grep result normalization。 | `tests/search/test_observed_grep_parsing_unit.py` |
| `tests/unit/test_openai_backend.py` | 13 | `clients` | `unit` | `keep+move` | 保留 retry policy 邊界。 | `tests/clients/test_openai_backend_unit.py` |
| `tests/unit/test_reload_settings.py` | 11 | `config` | `unit` | `keep+move` | 保留 settings reload side effects。 | `tests/config/test_reload_settings_unit.py` |
| `tests/unit/test_repo_clear.py` | 8 | `repo` | `unit` | `keep+move` | 保留 cloud clear confirm / fallback / sync-state 路徑。 | `tests/repo/test_clear_unit.py` |
| `tests/unit/test_repo_client.py` | 20 | `repo` | `unit` | `keep+move` | 保留 repo client request shaping 與 response parsing。 | `tests/repo/test_client_unit.py` |
| `tests/unit/test_repo_list_info.py` | 14 | `repo` | `unit` | `keep+move` | 保留 list/info domain logic。 | `tests/repo/test_list_info_unit.py` |
| `tests/unit/test_repo_search.py` | 17 | `repo` | `unit` | `keep+move` | 保留 repo search logic 與 edge cases。 | `tests/repo/test_search_unit.py` |
| `tests/unit/test_repo_sync.py` | 57 | `repo` | `unit` | `keep+move` | 保留 repo sync diff/state、git tracked files 與 ignore handling。 | `tests/repo/test_sync_unit.py` |
| `tests/unit/test_safe_redaction.py` | 27 | `observability` | `unit` | `keep+move` | 保留 safe redaction/security logging 邊界。 | `tests/observability/test_safe_redaction_unit.py` |
| `tests/unit/test_search_client.py` | 9 | `search` | `unit` | `keep+move` | 保留 provider credential selection 與 payload shaping。 | `tests/search/test_client_unit.py` |
| `tests/unit/test_search_handlers.py` | 92 | `search` | `unit` | `keep+move` | 保留 search path validation、handler dispatch 與 tool argument handling。 | `tests/search/test_handlers_unit.py` |
| `tests/unit/test_search_harness.py` | 19 | `search` | `unit` | `keep+move` | 保留 search harness orchestration 與 parallel tool-call repair。 | `tests/search/test_harness_unit.py` |
| `tests/unit/test_search_prompts.py` | 38 | `search` | `unit` | `keep+move` | 保留 prompt rendering 與 feature gating。 | `tests/search/test_prompts_unit.py` |
| `tests/unit/test_search_security.py` | 95 | `search` | `unit` | `keep+move` | 保留 command sandbox、安全 allowlist、git/path containment 的核心邊界。 | `tests/search/test_security_unit.py` |
| `tests/unit/test_snippet.py` | 77 | `apply` | `unit` | `keep+move` | 保留 snippet merge grammar、remove directive、symbol guard 與 syntax delta。 | `tests/apply/test_snippet_unit.py` |
| `tests/unit/test_tool_timeouts.py` | 2 | `search` | `unit` | `keep+move` | 保留 tool timeout contract。 | `tests/search/test_tool_timeouts_unit.py` |
| `tests/unit/test_tools.py` | 57 | `tools` | `unit` | `keep+move` | 保留 `fast_apply` validation、filesystem safety 與 recoverable error contract。 | `tests/tools/test_tools_unit.py` |
| `tests/unit/test_trace_logging.py` | 14 | `observability` | `unit` | `keep+move` | 保留 trace/event logging 與 rotation。 | `tests/observability/test_trace_logging_unit.py` |
| `tests/unit/test_utils.py` | 29 | `tools` | `unit` | `keep+move` | 保留 path normalization、repo path resolution 與 extra-path containment。 | `tests/tools/test_utils_unit.py` |

## Benchmark Tests

| path | collected_count | domain | level | decision | reason | replacement_coverage |
| --- | ---: | --- | --- | --- | --- | --- |
| `benchmark/tests/test_analyze_cli.py` | 1 | `cli` | `suite` | `keep+move` | 保留 analyze 預設選最新 `results.jsonl` 的 CLI 契約。 | `benchmark/tests/cli/test_analyze_cli.py` |
| `benchmark/tests/test_benchmark_docs.py` | 2 | `docs` | `suite` | `keep+move+minimize` | 改成最小文件契約，只保護 benchmark 測試命令與測試目錄結構。 | `benchmark/tests/docs/test_benchmark_docs.py` |
| `benchmark/tests/test_checkpoint_schema.py` | 1 | `runner` | `suite` | `keep+move` | 保留 resume checkpoint schema fail-fast。 | `benchmark/tests/runner/test_checkpoint_schema.py` |
| `benchmark/tests/test_experiment_paths.py` | 4 | `runner` | `suite` | `keep+move` | 保留 experiment layout、命名與 latest traces 選擇。 | `benchmark/tests/runner/test_experiment_paths.py` |
| `benchmark/tests/test_grid_cli.py` | 1 | `cli` | `suite` | `keep+move` | 保留 grid parent/child summary orchestration。 | `benchmark/tests/cli/test_grid_cli.py` |
| `benchmark/tests/test_locbench_build.py` | 5 | `datasets` | `suite` | `keep+move` | 保留 dataset diff 解析、function GT 與 target ranges 生成。 | `benchmark/tests/datasets/test_locbench_build.py` |
| `benchmark/tests/test_preflight.py` | 14 | `runner` | `suite` | `keep+move` | 保留 retrieval preflight backend 狀態矩陣。 | `benchmark/tests/runner/test_preflight.py` |
| `benchmark/tests/test_ranges.py` | 11 | `analysis` | `suite` | `keep+move` | 保留 range normalization / intersection 演算法。 | `benchmark/tests/analysis/test_ranges.py` |
| `benchmark/tests/test_report_cli.py` | 8 | `cli` | `suite` | `keep+move` | 保留 report mode 輸入契約與 help 文案邊界。 | `benchmark/tests/cli/test_report_cli.py` |
| `benchmark/tests/test_run_cli.py` | 1 | `cli` | `suite` | `keep+move` | 保留 `run.py` 使用 UTC timestamp 的契約。 | `benchmark/tests/cli/test_run_cli.py` |
| `benchmark/tests/test_search_map.py` | 17 | `analysis` | `suite` | `keep+move` | 保留 search-map extraction、normalization 與 metrics。 | `benchmark/tests/analysis/test_search_map.py` |
| `benchmark/tests/test_target_ranges.py` | 7 | `analysis` | `suite` | `keep+move` | 保留 target-range clustering 與 fallback 規則。 | `benchmark/tests/analysis/test_target_ranges.py` |
| `benchmark/tests/test_trace_artifact_helpers.py` | 1 | `analysis` | `suite` | `keep+move` | 保留 `total_latency_ms` fallback helper 契約。 | `benchmark/tests/analysis/test_trace_artifact_helpers.py` |
| `benchmark/tests/test_trace_artifacts.py` | 4 | `analysis` | `suite` | `keep+move` | 保留 trace artifact collection / validation 與 metadata summary。 | `benchmark/tests/analysis/test_trace_artifacts.py` |
| `benchmark/tests/test_trace_cli.py` | 3 | `cli` | `suite` | `keep+move` | 保留 trace/search-map/validate CLI 路徑。 | `benchmark/tests/cli/test_trace_cli.py` |
| `benchmark/tests/test_trace_metadata.py` | 3 | `runner` | `suite` | `keep+move` | 保留 trace metadata persistence 與 event payload。 | `benchmark/tests/runner/test_trace_metadata.py` |
| `benchmark/tests/test_trace_recorder.py` | 2 | `runner` | `suite` | `keep+move` | 保留 trace/event artifact 寫入路徑。 | `benchmark/tests/runner/test_trace_recorder.py` |
| `benchmark/tests/test_trace_recorder_helpers.py` | 1 | `runner` | `suite` | `keep+move` | 保留 `ArtifactWriteResult` hashability 契約。 | `benchmark/tests/runner/test_trace_recorder_helpers.py` |
| `benchmark/tests/test_treesitter.py` | 5 | `analysis` | `suite` | `keep+move` | 保留 parser cache 與 signature extraction。 | `benchmark/tests/analysis/test_treesitter.py` |

## Resulting Policy

- Product tests live only under `tests/**`, grouped by domain, with level carried by filename suffix and `pytest` markers.
- Benchmark tests live only under `benchmark/tests/**`, grouped by `analysis`, `cli`, `datasets`, `docs`, `runner`.
- Removed tests are either empty or replaced by a stronger / less duplicated surviving suite recorded above.
- CI keeps the existing product matrix and adds a single dedicated benchmark job.
