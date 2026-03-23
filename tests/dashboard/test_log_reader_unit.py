from relace_dashboard.log_reader import ALL_KINDS, ERROR_KINDS


class TestDashboardEventKinds:
    def test_all_kinds_include_backend_and_retrieval_events(self) -> None:
        expected = {
            "index_status",
            "index_status_error",
            "retrieval_backend_selected",
            "retrieval_hints_skipped",
            "backend_index_start",
            "backend_index_complete",
            "backend_index_error",
            "backend_disabled",
            "cloud_sync_start",
            "cloud_search_error",
        }
        assert expected.issubset(ALL_KINDS)

    def test_error_kinds_include_backend_cloud_and_tooling_errors(self) -> None:
        expected = {
            "apply_error",
            "search_error",
            "index_status_error",
            "backend_index_error",
            "retrieval_hints_error",
            "cloud_search_error",
            "tool_error",
            "lsp_server_error",
            "mcp_tool_exception",
        }
        assert expected.issubset(ERROR_KINDS)
        assert "backend_disabled" not in ERROR_KINDS
