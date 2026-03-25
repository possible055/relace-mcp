from benchmark.analysis.journey import build_journey_graph


def test_build_journey_graph_preserves_multi_range_report_back_and_causality() -> None:
    case_data = {
        "case_id": "case_1",
        "query": "find handler",
        "repo": "example/repo",
        "ground_truth_files": {"src/service.py": [[12, 18], [40, 48]]},
        "ground_truth_context_files": {},
        "ground_truth_functions": [
            {
                "path": "src/service.py",
                "name": "handle",
                "container": "Handler",
                "ranges": [[12, 18]],
            },
            {
                "path": "src/service.py",
                "name": "finalize",
                "container": "Handler",
                "ranges": [[40, 48]],
            },
        ],
        "semantic_hints": [{"filename": "src/service.py", "score": 0.92}],
        "selected_files": ["src/service.py"],
        "events": [
            {
                "turn": 1,
                "tool_name": "grep_search",
                "tool_call_id": "t1",
                "access_type": "grep_hit",
                "path": "src/service.py",
                "lines": [12, 12],
                "tool_query": "handler",
                "functions": [],
            },
            {
                "turn": 2,
                "tool_name": "view_file",
                "tool_call_id": "t2",
                "access_type": "read",
                "path": "src/service.py",
                "lines": [10, 55],
                "functions": [
                    {
                        "path": "src/service.py",
                        "class": "Handler",
                        "function": "handle",
                        "range": [12, 18],
                    },
                    {
                        "path": "src/service.py",
                        "class": "Handler",
                        "function": "finalize",
                        "range": [40, 48],
                    },
                ],
            },
            {
                "turn": 3,
                "tool_name": "report_back",
                "tool_call_id": "t3",
                "access_type": "select",
                "path": "src/service.py",
                "lines": [12, 18],
                "ranges": [[12, 18], [40, 48]],
                "functions": [
                    {
                        "path": "src/service.py",
                        "class": "Handler",
                        "function": "handle",
                        "range": [12, 18],
                    },
                    {
                        "path": "src/service.py",
                        "class": "Handler",
                        "function": "finalize",
                        "range": [40, 48],
                    },
                ],
            },
        ],
        "function_blocks": [
            {
                "path": "src/service.py",
                "class": "Handler",
                "function": "handle",
                "range": [12, 18],
                "first_turn": 2,
                "last_turn": 3,
                "access_kinds": ["read", "select"],
            },
            {
                "path": "src/service.py",
                "class": "Handler",
                "function": "finalize",
                "range": [40, 48],
                "first_turn": 2,
                "last_turn": 3,
                "access_kinds": ["read", "select"],
            },
        ],
        "turn_summaries": [
            {
                "turn": 1,
                "tool_names": ["grep_search"],
                "new_files": ["src/service.py"],
                "new_functions": [],
                "selected_files": [],
            },
            {
                "turn": 2,
                "tool_names": ["view_file"],
                "new_files": [],
                "new_functions": [
                    {
                        "path": "src/service.py",
                        "class": "Handler",
                        "function": "handle",
                        "range": [12, 18],
                    },
                    {
                        "path": "src/service.py",
                        "class": "Handler",
                        "function": "finalize",
                        "range": [40, 48],
                    },
                ],
                "selected_files": [],
            },
            {
                "turn": 3,
                "tool_names": ["report_back"],
                "new_files": [],
                "new_functions": [],
                "selected_files": ["src/service.py"],
            },
        ],
        "result_status": "ok",
    }
    trace_turns = [
        {
            "turn": 1,
            "llm_response": {"usage": {"prompt_tokens": 10, "completion_tokens": 3}},
            "tool_calls_raw": [
                {
                    "id": "t1",
                    "function": {"name": "grep_search", "arguments": '{"query":"handler"}'},
                }
            ],
            "tool_results": [{"id": "t1", "name": "grep_search", "success": True}],
        },
        {
            "turn": 2,
            "llm_response": {"usage": {"prompt_tokens": 9, "completion_tokens": 4}},
            "tool_calls_raw": [
                {
                    "id": "t2",
                    "function": {
                        "name": "view_file",
                        "arguments": '{"path":"src/service.py","view_range":[1,80]}',
                    },
                }
            ],
            "tool_results": [{"id": "t2", "name": "view_file", "success": True}],
        },
        {
            "turn": 3,
            "llm_response": {"usage": {"prompt_tokens": 8, "completion_tokens": 2}},
            "tool_calls_raw": [
                {
                    "id": "t3",
                    "function": {
                        "name": "report_back",
                        "arguments": '{"files":{"src/service.py":[[12,18],[40,48]]}}',
                    },
                }
            ],
            "tool_results": [{"id": "t3", "name": "report_back", "success": True}],
        },
    ]

    payload = build_journey_graph(case_data, trace_turns=trace_turns)

    nodes = {node["id"]: node for node in payload["nodes"]}
    edge_ids = {edge["id"] for edge in payload["edges"]}

    assert payload["meta"]["degraded"] is False
    assert payload["meta"]["default_view"] == "cumulative"
    assert nodes["tool:2:0:view_file"]["kind"] == "tool_call"
    assert nodes["candidate:1:0:grep_hit"]["kind"] == "candidate_set"
    assert nodes["candidate:1:0:grep_hit"]["candidate_count"] == 1
    assert nodes["file:src/service.py"]["ranges"] == [[10, 55]]
    assert "causal_exact:candidate:1:0:grep_hit:tool:2:0:view_file" in edge_ids
    assert "converges:file:src/service.py:result" in edge_ids
    assert payload["turns"][0]["summary"]["candidate_file_count"] == 1
    assert payload["turns"][1]["summary"]["inspected_file_count"] == 1
    assert payload["turns"][2]["summary"]["selected_file_count"] == 1
    assert payload["turns"][2]["selected_node_ids"] == [
        "class:src/service.py:Handler",
        "file:src/service.py",
        "function:src/service.py:Handler:finalize:40:48",
        "function:src/service.py:Handler:handle:12:18",
    ]


def test_build_journey_graph_degrades_without_trace_turns() -> None:
    case_data = {
        "case_id": "case_1",
        "query": "find handler",
        "repo": "example/repo",
        "ground_truth_files": {},
        "ground_truth_context_files": {},
        "ground_truth_functions": [],
        "semantic_hints": [],
        "selected_files": ["src/main.py"],
        "events": [
            {
                "turn": 1,
                "tool_name": "report_back",
                "access_type": "select",
                "path": "src/main.py",
                "ranges": [[4, 8]],
                "functions": [],
            }
        ],
        "function_blocks": [],
        "turn_summaries": [
            {
                "turn": 1,
                "tool_names": ["report_back"],
                "new_files": ["src/main.py"],
                "new_functions": [],
                "selected_files": ["src/main.py"],
            }
        ],
        "result_status": "ok",
    }

    payload = build_journey_graph(case_data)

    assert payload["meta"]["degraded"] is True
    assert payload["meta"]["degraded_reasons"] == ["trace_turns_missing"]
    assert [node["kind"] for node in payload["nodes"]].count("tool_call") == 0
    assert payload["turns"][0]["tool_call_ids"] == []
    assert payload["turns"][0]["summary"]["selected_file_count"] == 1
