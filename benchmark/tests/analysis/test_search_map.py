import json
import tempfile
from pathlib import Path

from benchmark.analysis.search_map import (
    _normalize_repo_path,
    aggregate_search_maps,
    extract_batch,
    extract_search_map,
    format_search_map_report,
)


def _make_trace_jsonl(turns: list[dict]) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for turn in turns:
        tmp.write(json.dumps(turn) + "\n")
    tmp.close()
    return Path(tmp.name)


def _write_meta(trace_path: Path, payload: dict) -> None:
    trace_path.with_suffix(".meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _tc(tc_id: str, name: str, arguments: dict) -> dict:
    return {"id": tc_id, "function": {"name": name, "arguments": json.dumps(arguments)}}


def _tr(
    tc_id: str,
    name: str,
    result: str,
    success: bool = True,
    latency_ms: float = 10.0,
) -> dict:
    return {
        "id": tc_id,
        "name": name,
        "result": result,
        "success": success,
        "latency_ms": latency_ms,
    }


SAMPLE_TURNS = [
    {
        "turn": 1,
        "llm_latency_ms": 100.0,
        "llm_response": {},
        "tool_calls_raw": [
            _tc("t1", "view_directory", {"path": "/repo/src"}),
            _tc(
                "t2",
                "glob",
                {"pattern": "**/*.py", "path": "./src", "include_hidden": False, "max_results": 50},
            ),
        ],
        "tool_results": [
            _tr("t1", "view_directory", "main.py\nhelpers/\nhelpers/util.py"),
            _tr("t2", "glob", "main.py\nhelpers/util.py\nhelpers/"),
        ],
        "report_back": None,
    },
    {
        "turn": 2,
        "llm_latency_ms": 200.0,
        "llm_response": {},
        "tool_calls_raw": [
            _tc("t3", "view_file", {"path": "./src/main.py", "view_range": [1, 50]}),
            _tc("t4", "grep_search", {"query": "def handler"}),
        ],
        "tool_results": [
            _tr("t3", "view_file", "10 def handler():\n11     return True"),
            _tr(
                "t4",
                "grep_search",
                "/repo/src/main.py:10:def handler():\n./src/helpers/util.py:5:def helper():",
            ),
        ],
        "report_back": None,
    },
    {
        "turn": 3,
        "llm_latency_ms": 150.0,
        "llm_response": {},
        "tool_calls_raw": [
            _tc(
                "t5",
                "report_back",
                {
                    "explanation": "Found the handler",
                    "files": {"/repo/src/main.py": [[10, 20]], "./src/helpers/util.py": [[1, 20]]},
                },
            ),
        ],
        "tool_results": [
            _tr("t5", "report_back", '{"ok": true}'),
        ],
        "report_back": {"explanation": "Found", "files": {"src/main.py": [[10, 20]]}},
    },
]


class TestPathNormalization:
    def test_normalize_repo_path_variants(self) -> None:
        assert _normalize_repo_path("/repo/src/a.py") == "src/a.py"
        assert _normalize_repo_path("./src/a.py") == "src/a.py"
        assert _normalize_repo_path("src/a.py") == "src/a.py"
        assert _normalize_repo_path("/repo/src/") == "src/"
        assert _normalize_repo_path("") == "."


class TestPerToolParsers:
    def test_view_directory_extraction(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)

        dir_events = [e for e in sm.events if e.tool_name == "view_directory"]
        assert {e.path for e in dir_events} == {
            "src/main.py",
            "src/helpers/",
            "src/helpers/util.py",
        }

    def test_glob_extraction(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)

        glob_events = [e for e in sm.events if e.tool_name == "glob"]
        assert {e.path for e in glob_events} == {
            "src/main.py",
            "src/helpers/util.py",
            "src/helpers/",
        }

    def test_view_file_extraction_uses_actual_line_numbers(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)

        read_events = [e for e in sm.events if e.tool_name == "view_file"]
        assert len(read_events) == 1
        assert read_events[0].path == "src/main.py"
        assert read_events[0].lines == (10, 11)
        assert read_events[0].access_type == "read"

    def test_grep_search_extraction_normalizes_paths(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)

        grep_events = [e for e in sm.events if e.tool_name == "grep_search"]
        assert {e.path for e in grep_events} == {"src/main.py", "src/helpers/util.py"}

    def test_report_back_extraction_normalizes_paths(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)

        selected = [e for e in sm.events if e.tool_name == "report_back"]
        assert {e.path for e in selected} == {"src/main.py", "src/helpers/util.py"}
        assert all(e.access_type == "select" for e in selected)


class TestLSPParsing:
    def test_find_symbol_extraction(self) -> None:
        turns = [
            {
                "turn": 1,
                "llm_latency_ms": 100.0,
                "llm_response": {},
                "tool_calls_raw": [
                    _tc(
                        "t1",
                        "find_symbol",
                        {
                            "file": "/repo/src/app.py",
                            "line": 10,
                            "column": 5,
                            "action": "definition",
                        },
                    ),
                ],
                "tool_results": [
                    _tr("t1", "find_symbol", "/repo/src/models.py:25: class User:"),
                ],
                "report_back": None,
            }
        ]

        sm = extract_search_map(_make_trace_jsonl(turns))
        lsp_events = [e for e in sm.events if e.tool_name == "find_symbol"]
        assert {e.path for e in lsp_events} == {"src/app.py", "src/models.py"}

    def test_search_symbol_parses_real_lsp_output_format(self) -> None:
        turns = [
            {
                "turn": 1,
                "llm_latency_ms": 100.0,
                "llm_response": {},
                "tool_calls_raw": [_tc("t1", "search_symbol", {"query": "UserModel"})],
                "tool_results": [
                    _tr(
                        "t1",
                        "search_symbol",
                        "[function] /repo/src/models.py:10:5 UserModel\n[class] ./src/views.py:5:1 UserView",
                    ),
                ],
                "report_back": None,
            }
        ]

        sm = extract_search_map(_make_trace_jsonl(turns))
        lsp_events = [e for e in sm.events if e.tool_name == "search_symbol"]
        assert {e.path for e in lsp_events} == {"src/models.py", "src/views.py"}
        assert lsp_events[0].tool_query == "UserModel"
        assert lsp_events[0].symbol_name == "UserModel"
        assert lsp_events[0].symbol_kind == "function"


class TestSearchMapMetadata:
    def test_extract_search_map_loads_semantic_hints_meta(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        _write_meta(
            path,
            {
                "case_id": path.stem,
                "repo": "example/repo",
                "search_mode": "indexed",
                "semantic_hints_used": 2,
                "semantic_hints": [
                    {"filename": "/repo/src/main.py", "score": 0.91},
                    {"filename": "./src/helpers/util.py", "score": 0.74},
                ],
            },
        )

        sm = extract_search_map(path)
        assert sm.semantic_hints_files == ["src/main.py", "src/helpers/util.py"]
        assert sm.semantic_hints_count == 2

        payload = sm.to_dict()
        assert payload["semantic_hints_files"] == ["src/main.py", "src/helpers/util.py"]
        assert payload["semantic_hints"][0]["score"] == 0.91

    def test_missing_meta_is_allowed(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)
        assert sm.meta == {}
        assert sm.semantic_hints_files == []

    def test_extract_batch_includes_meta_only_case(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "case_1.jsonl"
        trace_path.write_text(
            json.dumps(
                {
                    "turn": 1,
                    "tool_calls_raw": [],
                    "tool_results": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        _write_meta(
            trace_path,
            {
                "schema_version": "1.0",
                "case_id": "case_1",
                "repo": "example/repo",
                "search_mode": "indexed",
                "semantic_hints_used": 0,
                "semantic_hints": [],
            },
        )
        (tmp_path / "case_2.meta.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "case_id": "case_2",
                    "repo": "example/repo",
                    "search_mode": "indexed",
                    "semantic_hints_used": 1,
                    "semantic_hints": [{"filename": "src/only_hint.py", "score": 0.82}],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        maps = extract_batch(tmp_path)

        assert [m.case_id for m in maps] == ["case_1", "case_2"]
        assert maps[1].total_turns == 0
        assert maps[1].semantic_hints_files == ["src/only_hint.py"]


class TestSearchMapEventPayloads:
    def test_to_dict_includes_ordered_events_and_queries(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)

        sm = extract_search_map(path)
        payload = sm.to_dict()

        assert payload["events_count"] == len(payload["events"])
        assert payload["events"][0]["turn"] == 1
        assert payload["events"][0]["tool_name"] == "view_directory"
        grep_event = next(
            event for event in payload["events"] if event["tool_name"] == "grep_search"
        )
        assert grep_event["tool_query"] == "def handler"
        assert payload["events"][-1]["tool_name"] == "report_back"
        assert payload["events"][-1]["access_type"] == "select"


class TestBashParsing:
    def test_bash_parses_find_ls_cat_and_git_grep_outputs(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        repos_dir = tmp_path / "repos"
        repo_root = repos_dir / "example__repo"
        (repo_root / "src" / "pkg").mkdir(parents=True)
        (repo_root / "README.md").write_text("hello\n", encoding="utf-8")

        trace_path = _make_trace_jsonl(
            [
                {
                    "turn": 1,
                    "llm_latency_ms": 100.0,
                    "llm_response": {},
                    "tool_calls_raw": [
                        _tc("t1", "bash", {"command": "find . -maxdepth 2 -type f"}),
                        _tc("t2", "bash", {"command": "ls src"}),
                        _tc("t3", "bash", {"command": "cat README.md"}),
                        _tc("t4", "bash", {"command": "git grep handler"}),
                    ],
                    "tool_results": [
                        _tr("t1", "bash", "./README.md\n./src/main.py\n./src/pkg/\n"),
                        _tr("t2", "bash", "main.py\npkg/\n"),
                        _tr("t3", "bash", "hello\n"),
                        _tr(
                            "t4",
                            "bash",
                            "src/main.py:10:def handler():",
                        ),
                    ],
                    "report_back": None,
                }
            ]
        )
        _write_meta(
            trace_path,
            {
                "case_id": trace_path.stem,
                "repo": "example/repo",
                "search_mode": "agentic",
                "semantic_hints_used": 0,
                "semantic_hints": [],
            },
        )

        monkeypatch.setattr("benchmark.analysis.search_map.get_repos_dir", lambda: repos_dir)

        sm = extract_search_map(trace_path)

        discover_paths = {
            e.path for e in sm.events if e.tool_name == "bash" and e.access_type == "discover"
        }
        assert "README.md" in discover_paths
        assert "src/main.py" in discover_paths
        assert "src/pkg/" in discover_paths

        read_events = [e for e in sm.events if e.tool_name == "bash" and e.access_type == "read"]
        assert len(read_events) == 1
        assert read_events[0].path == "README.md"
        assert read_events[0].tool_command == "cat README.md"

        grep_events = [
            e for e in sm.events if e.tool_name == "bash" and e.access_type == "grep_hit"
        ]
        assert len(grep_events) == 1
        assert grep_events[0].path == "src/main.py"
        assert grep_events[0].lines == (10, 10)
        assert grep_events[0].tool_command == "git grep handler"

    def test_bash_normalizes_absolute_repo_paths_and_augments_python_functions(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        repos_dir = tmp_path / "repos"
        repo_root = repos_dir / "example__repo"
        (repo_root / "src").mkdir(parents=True)
        source = "\n" * 9 + "def handler():\n    return True\n"
        (repo_root / "src" / "main.py").write_text(source, encoding="utf-8")

        trace_path = _make_trace_jsonl(
            [
                {
                    "turn": 1,
                    "llm_latency_ms": 100.0,
                    "llm_response": {},
                    "tool_calls_raw": [
                        _tc("t1", "bash", {"command": "rg -n handler /repo/src"}),
                    ],
                    "tool_results": [
                        _tr("t1", "bash", f"{repo_root}/src/main.py:10:def handler():"),
                    ],
                    "report_back": None,
                }
            ]
        )
        _write_meta(
            trace_path,
            {
                "case_id": trace_path.stem,
                "repo": "example/repo",
                "search_mode": "agentic",
                "semantic_hints_used": 0,
                "semantic_hints": [],
            },
        )

        monkeypatch.setattr("benchmark.analysis.search_map.get_repos_dir", lambda: repos_dir)

        sm = extract_search_map(trace_path)

        grep_event = next(e for e in sm.events if e.tool_name == "bash")
        assert grep_event.path == "src/main.py"
        assert grep_event.functions[0]["function"] == "handler"
        assert sm.unique_functions[0]["function"] == "handler"
        payload = sm.to_dict()
        assert payload["unique_functions_count"] == 1
        assert payload["events"][0]["functions"][0]["signature"] == "def handler()"


class TestSearchMapMetrics:
    def test_unique_files_and_selected_files(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)

        assert sm.unique_files == {"src/main.py", "src/helpers/util.py"}
        assert sm.selected_files == {"src/main.py", "src/helpers/util.py"}

    def test_wasted_reads_excludes_selected_files(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)
        assert sm.wasted_reads() == set()

    def test_incremental_recall(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        sm = extract_search_map(path)
        recall = sm.incremental_recall({"src/main.py", "src/helpers/util.py"})
        assert recall[-1][1] == 1.0

    def test_aggregate_includes_semantic_hint_stats(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        _write_meta(
            path,
            {
                "case_id": path.stem,
                "repo": "example/repo",
                "search_mode": "indexed",
                "semantic_hints_used": 1,
                "semantic_hints": [{"filename": "src/main.py", "score": 0.88}],
            },
        )
        sm = extract_search_map(path)

        agg = aggregate_search_maps([sm, sm])
        assert agg["cases"] == 2
        assert agg["cases_with_semantic_hints"] == 2
        assert agg["avg_semantic_hints_per_case"] == 1.0
        assert "avg_unique_functions_per_case" in agg

    def test_format_report_mentions_retrieval_hints(self) -> None:
        path = _make_trace_jsonl(SAMPLE_TURNS)
        _write_meta(
            path,
            {
                "case_id": path.stem,
                "repo": "example/repo",
                "search_mode": "indexed",
                "semantic_hints_used": 1,
                "semantic_hints": [{"filename": "src/main.py", "score": 0.88}],
            },
        )
        sm = extract_search_map(path)

        report = format_search_map_report([sm])
        assert "Retrieval hints" in report
        assert "Avg semantic_hints/case" in report
        assert "Avg unique functions/case" in report

    def test_failed_tool_with_unparseable_output_is_skipped(self) -> None:
        turns = [
            {
                "turn": 1,
                "llm_latency_ms": 50.0,
                "llm_response": {},
                "tool_calls_raw": [_tc("t1", "grep_search", {"query": "foo"})],
                "tool_results": [_tr("t1", "grep_search", "Error: rg not found", success=False)],
                "report_back": None,
            }
        ]
        sm = extract_search_map(_make_trace_jsonl(turns))
        assert sm.events == []
