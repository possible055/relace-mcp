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

    def to_grep_format(self, base_dir: str) -> str:
        """Format as grep-like output: path:line:col"""
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
