from typing import Any

from relace_mcp.lsp.types import (
    CallHierarchyItem,
    CallInfo,
    DocumentSymbol,
    HoverInfo,
    Location,
    SymbolInfo,
)


def parse_locations(result: Any) -> list[Location]:
    if result is None:
        return []

    if isinstance(result, dict) and "uri" in result:
        result = [result]

    if not isinstance(result, list):
        return []

    locations: list[Location] = []
    for item in result:
        if not isinstance(item, dict):
            continue

        uri = item.get("uri") or item.get("targetUri", "")
        rng = item.get("range") or item.get("targetRange", {})
        start = rng.get("start", {})

        if uri:
            locations.append(
                Location(
                    uri=uri,
                    line=start.get("line", 0),
                    character=start.get("character", 0),
                )
            )

    return locations


def parse_symbol_info(result: Any) -> list[SymbolInfo]:
    if not isinstance(result, list):
        return []

    symbols: list[SymbolInfo] = []
    for item in result:
        if not isinstance(item, dict):
            continue

        name = item.get("name", "")
        kind = item.get("kind", 0)
        location = item.get("location", {})
        uri = location.get("uri", "")
        rng = location.get("range", {})
        start = rng.get("start", {})
        container = item.get("containerName")

        if name and uri:
            symbols.append(
                SymbolInfo(
                    name=name,
                    kind=kind,
                    uri=uri,
                    line=start.get("line", 0),
                    character=start.get("character", 0),
                    container_name=container,
                )
            )

    return symbols


def parse_document_symbols(result: Any) -> list[DocumentSymbol]:
    if not isinstance(result, list):
        return []

    def parse_item(item: dict[str, Any]) -> DocumentSymbol | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name", "")
        kind = item.get("kind", 0)
        rng = item.get("range", {})
        start = rng.get("start", {})
        end = rng.get("end", {})

        if not name:
            return None

        children_raw = item.get("children", [])
        children = None
        if children_raw:
            parsed = [parse_item(c) for c in children_raw]
            children = [c for c in parsed if c is not None]

        return DocumentSymbol(
            name=name,
            kind=kind,
            range_start=start.get("line", 0),
            range_end=end.get("line", 0),
            children=children if children else None,
        )

    symbols = [parse_item(item) for item in result]
    return [s for s in symbols if s is not None]


def parse_hover(result: Any) -> HoverInfo | None:
    if not result or not isinstance(result, dict):
        return None

    contents = result.get("contents")
    if contents is None:
        return None

    if isinstance(contents, dict):
        value = contents.get("value", "")
        return HoverInfo(content=value) if value else None

    if isinstance(contents, str):
        return HoverInfo(content=contents) if contents else None

    if isinstance(contents, list):
        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("value", ""))
        combined = "\n\n".join(p for p in parts if p)
        return HoverInfo(content=combined) if combined else None

    return None


def parse_call_hierarchy_item(raw: dict[str, Any]) -> CallHierarchyItem | None:
    if not isinstance(raw, dict):
        return None

    name = raw.get("name", "")
    kind = raw.get("kind", 0)
    uri = raw.get("uri", "")
    rng = raw.get("range", {})
    sel = raw.get("selectionRange", {})

    if not name or not uri:
        return None

    return CallHierarchyItem(
        name=name,
        kind=kind,
        uri=uri,
        range_start_line=rng.get("start", {}).get("line", 0),
        range_start_char=rng.get("start", {}).get("character", 0),
        selection_start_line=sel.get("start", {}).get("line", 0),
        selection_start_char=sel.get("start", {}).get("character", 0),
    )


def parse_call_info_list(raw: Any, direction: str) -> list[CallInfo]:
    if not isinstance(raw, list):
        return []

    results: list[CallInfo] = []
    for call in raw:
        if not isinstance(call, dict):
            continue

        item_key = "from" if direction == "incoming" else "to"
        raw_item = call.get(item_key)
        if not raw_item:
            continue

        item = parse_call_hierarchy_item(raw_item)
        if not item:
            continue

        from_ranges = []
        for rng in call.get("fromRanges", []):
            if isinstance(rng, dict):
                start = rng.get("start", {})
                from_ranges.append((start.get("line", 0), start.get("character", 0)))

        results.append(CallInfo(item=item, from_ranges=from_ranges))

    return results


__all__ = [
    "parse_call_hierarchy_item",
    "parse_call_info_list",
    "parse_document_symbols",
    "parse_hover",
    "parse_locations",
    "parse_symbol_info",
]
