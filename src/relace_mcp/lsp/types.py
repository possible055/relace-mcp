from dataclasses import dataclass
from urllib.parse import unquote, urlparse


@dataclass
class Location:
    """Represents a location in a source file."""

    uri: str
    line: int  # 0-indexed
    character: int  # 0-indexed

    def _uri_to_path(self) -> str:
        uri = self.uri
        if not uri.startswith("file:"):
            return uri

        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return uri

        path = unquote(parsed.path)

        # file://C:/path (non-standard but seen in the wild)
        netloc = parsed.netloc
        if netloc and len(netloc) == 2 and netloc[1] == ":" and netloc[0].isalpha():
            if path.startswith("/"):
                path = path[1:]
            return f"{netloc}/{path}" if path else netloc

        # file://server/share/path -> //server/share/path (UNC)
        if netloc and netloc != "localhost":
            return f"//{netloc}{path}"

        # file:///C:/path -> C:/path (strip leading slash before drive letter)
        if len(path) >= 3 and path[0] == "/" and path[2] == ":" and path[1].isalpha():
            path = path[1:]

        return path

    def to_grep_format(self, base_dir: str, *, filter_external: bool = True) -> str | None:
        """Format as grep-like output: path:line:col

        Args:
            base_dir: Repository root directory.
            filter_external: If True, return None for paths outside base_dir.

        Returns:
            Formatted string, or None if path is external and filter_external=True.
        """
        path = self._uri_to_path().replace("\\", "/")
        # Convert to repo-relative path
        base_dir_norm = base_dir.replace("\\", "/")
        base_prefix = base_dir_norm if base_dir_norm.endswith("/") else base_dir_norm + "/"

        path_cmp = path
        base_prefix_cmp = base_prefix
        if (len(base_prefix) >= 3 and base_prefix[1:3] == ":/") or base_prefix.startswith("//"):
            path_cmp = path.lower()
            base_prefix_cmp = base_prefix.lower()

        if path_cmp.startswith(base_prefix_cmp):
            path = "/repo/" + path[len(base_prefix) :]
        elif filter_external:
            return None  # External path (stdlib, site-packages, etc.)
        # Line and column are 1-indexed in output (standard grep format)
        return f"{path}:{self.line + 1}:{self.character + 1}"


@dataclass
class LSPError(Exception):
    """LSP-related error."""

    message: str
    code: int | None = None

    def __str__(self) -> str:
        if self.code is not None:
            return f"LSP Error {self.code}: {self.message}"
        return f"LSP Error: {self.message}"

    def __reduce__(self) -> tuple[type, tuple[str, int | None]]:
        """Enable proper pickling for dataclass Exception subclass."""
        return (type(self), (self.message, self.code))


# LSP SymbolKind enum values (subset)
SYMBOL_KIND_MAP: dict[int, str] = {
    1: "file",
    2: "module",
    3: "namespace",
    5: "class",
    6: "method",
    7: "property",
    8: "field",
    9: "constructor",
    10: "enum",
    11: "interface",
    12: "function",
    13: "variable",
    14: "constant",
    23: "struct",
    26: "type_parameter",
}


@dataclass
class SymbolInfo:
    """Workspace symbol search result."""

    name: str
    kind: int  # LSP SymbolKind
    uri: str
    line: int  # 0-indexed
    character: int  # 0-indexed
    container_name: str | None = None

    @property
    def kind_name(self) -> str:
        return SYMBOL_KIND_MAP.get(self.kind, "unknown")

    def to_grep_format(self, base_dir: str, *, filter_external: bool = True) -> str | None:
        """Format as grep-like output: [kind] path:line:col name

        Returns None if path is external and filter_external=True.
        """
        loc = Location(uri=self.uri, line=self.line, character=self.character)
        base = loc.to_grep_format(base_dir, filter_external=filter_external)
        if base is None:
            return None
        kind_str = self.kind_name
        container = f" ({self.container_name})" if self.container_name else ""
        return f"[{kind_str}] {base} {self.name}{container}"


@dataclass
class DocumentSymbol:
    """Symbol in a document with hierarchical structure."""

    name: str
    kind: int  # LSP SymbolKind
    range_start: int  # start line (0-indexed)
    range_end: int  # end line (0-indexed)
    children: list["DocumentSymbol"] | None = None

    @property
    def kind_name(self) -> str:
        return SYMBOL_KIND_MAP.get(self.kind, "unknown")

    def to_outline_str(self, indent: int = 0) -> str:
        """Format as outline string with optional indentation."""
        prefix = "  " * indent
        kind_str = self.kind_name
        # 1-indexed for display
        line_info = f"L{self.range_start + 1}-{self.range_end + 1}"
        result = f"{prefix}[{kind_str}] {self.name} ({line_info})"
        if self.children:
            for child in self.children:
                result += "\n" + child.to_outline_str(indent + 1)
        return result


@dataclass
class HoverInfo:
    """Type information from hover."""

    content: str  # Markdown formatted type/documentation info

    def to_display_str(self) -> str:
        """Format for display."""
        return self.content if self.content else "No type information available."


@dataclass
class CallHierarchyItem:
    """Item in call hierarchy."""

    name: str
    kind: int  # LSP SymbolKind
    uri: str
    range_start_line: int  # 0-indexed
    range_start_char: int
    selection_start_line: int  # 0-indexed
    selection_start_char: int

    @property
    def kind_name(self) -> str:
        return SYMBOL_KIND_MAP.get(self.kind, "unknown")

    def to_display_str(self, base_dir: str, *, filter_external: bool = True) -> str | None:
        """Format for display.

        Returns None if path is external and filter_external=True.
        """
        loc = Location(
            uri=self.uri, line=self.selection_start_line, character=self.selection_start_char
        )
        path_str = loc.to_grep_format(base_dir, filter_external=filter_external)
        if path_str is None:
            return None
        return f"[{self.kind_name}] {path_str} {self.name}"


@dataclass
class CallInfo:
    """Represents a call relationship."""

    item: CallHierarchyItem
    from_ranges: list[tuple[int, int]]  # list of (line, char) - 0-indexed

    def to_display_str(self, base_dir: str, *, filter_external: bool = True) -> str | None:
        """Format for display.

        Returns None if path is external and filter_external=True.
        """
        return self.item.to_display_str(base_dir, filter_external=filter_external)
