from benchmark.analysis.traces import build_search_complete_event


def test_build_search_complete_event_defaults_missing_latency_to_zero() -> None:
    payload = build_search_complete_event(
        case_id="case_1",
        repo="example/repo",
        search_mode="indexed",
        turns_used=1,
        partial=False,
        files_found=2,
        total_latency_ms=None,
        retrieval_backend="chunkhound",
        semantic_hints_used=0,
        hint_policy="prefer-stale",
        hints_index_freshness="fresh",
        background_refresh_scheduled=False,
        reindex_action=None,
    )

    assert payload["total_latency_ms"] == 0.0
