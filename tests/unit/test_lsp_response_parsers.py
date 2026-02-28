from relace_mcp.lsp.response_parsers import (
    parse_call_hierarchy_item,
    parse_call_info_list,
    parse_document_symbols,
    parse_hover,
    parse_locations,
    parse_symbol_info,
)
from relace_mcp.lsp.types import CallHierarchyItem, DocumentSymbol, HoverInfo, Location, SymbolInfo


class TestParseLocations:
    def test_none_returns_empty(self) -> None:
        assert parse_locations(None) == []

    def test_single_dict_wrapped_to_list(self) -> None:
        result = parse_locations(
            {"uri": "file:///a.py", "range": {"start": {"line": 1, "character": 2}}}
        )
        assert result == [Location(uri="file:///a.py", line=1, character=2)]

    def test_list_of_locations(self) -> None:
        raw = [
            {"uri": "file:///a.py", "range": {"start": {"line": 0, "character": 0}}},
            {"uri": "file:///b.py", "range": {"start": {"line": 5, "character": 3}}},
        ]
        result = parse_locations(raw)
        assert len(result) == 2
        assert result[0].uri == "file:///a.py"
        assert result[1].line == 5

    def test_target_uri_and_target_range(self) -> None:
        raw = [
            {
                "targetUri": "file:///t.py",
                "targetRange": {"start": {"line": 10, "character": 0}},
            }
        ]
        result = parse_locations(raw)
        assert result == [Location(uri="file:///t.py", line=10, character=0)]

    def test_non_dict_items_skipped(self) -> None:
        raw = [42, "bad", {"uri": "file:///ok.py", "range": {"start": {}}}]
        result = parse_locations(raw)
        assert len(result) == 1
        assert result[0].uri == "file:///ok.py"

    def test_empty_uri_skipped(self) -> None:
        raw = [{"uri": "", "range": {"start": {"line": 0, "character": 0}}}]
        assert parse_locations(raw) == []

    def test_non_list_non_dict_returns_empty(self) -> None:
        assert parse_locations("garbage") == []
        assert parse_locations(123) == []

    def test_missing_range_uses_defaults(self) -> None:
        result = parse_locations([{"uri": "file:///x.py"}])
        assert result == [Location(uri="file:///x.py", line=0, character=0)]


class TestParseSymbolInfo:
    def test_non_list_returns_empty(self) -> None:
        assert parse_symbol_info(None) == []
        assert parse_symbol_info("bad") == []

    def test_valid_symbols(self) -> None:
        raw = [
            {
                "name": "foo",
                "kind": 12,
                "location": {
                    "uri": "file:///a.py",
                    "range": {"start": {"line": 3, "character": 1}},
                },
            }
        ]
        result = parse_symbol_info(raw)
        assert len(result) == 1
        assert result[0] == SymbolInfo(
            name="foo", kind=12, uri="file:///a.py", line=3, character=1, container_name=None
        )

    def test_with_container_name(self) -> None:
        raw = [
            {
                "name": "bar",
                "kind": 6,
                "location": {"uri": "file:///a.py", "range": {"start": {}}},
                "containerName": "MyClass",
            }
        ]
        result = parse_symbol_info(raw)
        assert result[0].container_name == "MyClass"

    def test_missing_name_skipped(self) -> None:
        raw = [{"name": "", "kind": 5, "location": {"uri": "file:///a.py", "range": {"start": {}}}}]
        assert parse_symbol_info(raw) == []

    def test_missing_uri_skipped(self) -> None:
        raw = [{"name": "x", "kind": 5, "location": {"uri": "", "range": {"start": {}}}}]
        assert parse_symbol_info(raw) == []

    def test_non_dict_items_skipped(self) -> None:
        raw = [
            42,
            None,
            {"name": "ok", "kind": 5, "location": {"uri": "file:///a.py", "range": {"start": {}}}},
        ]
        result = parse_symbol_info(raw)
        assert len(result) == 1


class TestParseDocumentSymbols:
    def test_non_list_returns_empty(self) -> None:
        assert parse_document_symbols(None) == []
        assert parse_document_symbols({}) == []

    def test_flat_list(self) -> None:
        raw = [
            {
                "name": "MyClass",
                "kind": 5,
                "range": {"start": {"line": 0}, "end": {"line": 10}},
            }
        ]
        result = parse_document_symbols(raw)
        assert len(result) == 1
        assert result[0] == DocumentSymbol(
            name="MyClass", kind=5, range_start=0, range_end=10, children=None
        )

    def test_nested_children(self) -> None:
        raw = [
            {
                "name": "Parent",
                "kind": 5,
                "range": {"start": {"line": 0}, "end": {"line": 20}},
                "children": [
                    {
                        "name": "child_method",
                        "kind": 6,
                        "range": {"start": {"line": 2}, "end": {"line": 5}},
                    }
                ],
            }
        ]
        result = parse_document_symbols(raw)
        assert len(result) == 1
        assert result[0].children is not None
        assert len(result[0].children) == 1
        assert result[0].children[0].name == "child_method"

    def test_empty_name_skipped(self) -> None:
        raw = [{"name": "", "kind": 5, "range": {"start": {}, "end": {}}}]
        assert parse_document_symbols(raw) == []

    def test_non_dict_items_skipped(self) -> None:
        raw = ["bad", 42]
        assert parse_document_symbols(raw) == []

    def test_empty_children_list_gives_none(self) -> None:
        raw = [
            {
                "name": "Func",
                "kind": 12,
                "range": {"start": {"line": 0}, "end": {"line": 5}},
                "children": [],
            }
        ]
        result = parse_document_symbols(raw)
        assert result[0].children is None


class TestParseHover:
    def test_none_returns_none(self) -> None:
        assert parse_hover(None) is None

    def test_non_dict_returns_none(self) -> None:
        assert parse_hover("string") is None
        assert parse_hover(42) is None

    def test_no_contents_key(self) -> None:
        assert parse_hover({"other": "stuff"}) is None

    def test_contents_none(self) -> None:
        assert parse_hover({"contents": None}) is None

    def test_contents_as_dict(self) -> None:
        result = parse_hover({"contents": {"value": "int", "language": "python"}})
        assert result == HoverInfo(content="int")

    def test_contents_dict_empty_value(self) -> None:
        assert parse_hover({"contents": {"value": ""}}) is None

    def test_contents_as_string(self) -> None:
        result = parse_hover({"contents": "some docs"})
        assert result == HoverInfo(content="some docs")

    def test_contents_empty_string(self) -> None:
        assert parse_hover({"contents": ""}) is None

    def test_contents_as_list(self) -> None:
        result = parse_hover({"contents": ["first", {"value": "second"}, {"value": ""}, "third"]})
        assert result is not None
        assert result.content == "first\n\nsecond\n\nthird"

    def test_contents_list_all_empty(self) -> None:
        assert parse_hover({"contents": ["", {"value": ""}]}) is None

    def test_contents_unknown_type(self) -> None:
        assert parse_hover({"contents": 42}) is None

    def test_empty_dict_returns_none(self) -> None:
        assert parse_hover({}) is None


class TestParseCallHierarchyItem:
    def test_valid_item(self) -> None:
        raw = {
            "name": "my_func",
            "kind": 12,
            "uri": "file:///a.py",
            "range": {"start": {"line": 5, "character": 0}},
            "selectionRange": {"start": {"line": 5, "character": 4}},
        }
        result = parse_call_hierarchy_item(raw)
        assert result is not None
        assert result == CallHierarchyItem(
            name="my_func",
            kind=12,
            uri="file:///a.py",
            range_start_line=5,
            range_start_char=0,
            selection_start_line=5,
            selection_start_char=4,
        )

    def test_missing_name_returns_none(self) -> None:
        assert parse_call_hierarchy_item({"name": "", "kind": 12, "uri": "file:///a.py"}) is None

    def test_missing_uri_returns_none(self) -> None:
        assert parse_call_hierarchy_item({"name": "f", "kind": 12, "uri": ""}) is None

    def test_non_dict_returns_none(self) -> None:
        assert parse_call_hierarchy_item("bad") is None  # type: ignore[arg-type]
        assert parse_call_hierarchy_item(42) is None  # type: ignore[arg-type]

    def test_missing_ranges_use_defaults(self) -> None:
        raw = {"name": "f", "kind": 12, "uri": "file:///a.py"}
        result = parse_call_hierarchy_item(raw)
        assert result is not None
        assert result.range_start_line == 0
        assert result.selection_start_line == 0


class TestParseCallInfoList:
    def test_non_list_returns_empty(self) -> None:
        assert parse_call_info_list(None, "incoming") == []
        assert parse_call_info_list("bad", "outgoing") == []

    def test_incoming_direction(self) -> None:
        raw = [
            {
                "from": {
                    "name": "caller",
                    "kind": 12,
                    "uri": "file:///a.py",
                    "range": {"start": {"line": 1, "character": 0}},
                    "selectionRange": {"start": {"line": 1, "character": 4}},
                },
                "fromRanges": [{"start": {"line": 10, "character": 5}}],
            }
        ]
        result = parse_call_info_list(raw, "incoming")
        assert len(result) == 1
        assert result[0].item.name == "caller"
        assert result[0].from_ranges == [(10, 5)]

    def test_outgoing_direction(self) -> None:
        raw = [
            {
                "to": {
                    "name": "callee",
                    "kind": 12,
                    "uri": "file:///b.py",
                    "range": {"start": {}},
                    "selectionRange": {"start": {}},
                },
                "fromRanges": [],
            }
        ]
        result = parse_call_info_list(raw, "outgoing")
        assert len(result) == 1
        assert result[0].item.name == "callee"
        assert result[0].from_ranges == []

    def test_invalid_items_skipped(self) -> None:
        raw = [
            42,
            {"from": None},  # None item → skipped
            {"from": {"name": "", "kind": 0, "uri": ""}},  # invalid hierarchy item → skipped
        ]
        assert parse_call_info_list(raw, "incoming") == []

    def test_non_dict_from_ranges_skipped(self) -> None:
        raw = [
            {
                "from": {
                    "name": "f",
                    "kind": 12,
                    "uri": "file:///a.py",
                    "range": {"start": {}},
                    "selectionRange": {"start": {}},
                },
                "fromRanges": ["not-a-dict", 42],
            }
        ]
        result = parse_call_info_list(raw, "incoming")
        assert len(result) == 1
        assert result[0].from_ranges == []
