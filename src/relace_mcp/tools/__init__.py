from typing import Any

from fastmcp import FastMCP

from ..clients import RelaceClient, RelaceSearchClient
from ..config import RelaceConfig
from .apply import apply_file_logic
from .search import FastAgenticSearchHarness

__all__ = ["register_tools"]


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """Register Relace tools to the FastMCP instance."""
    client = RelaceClient(config)

    @mcp.tool
    def fast_apply(
        file_path: str,
        edit_snippet: str,
        instruction: str | None = None,
    ) -> str:
        """Use this tool to propose an edit to an existing file or create a new file.

        If you are performing an edit follow these formatting rules:
        - Abbreviate sections of the code in your response that will remain the same
          by replacing those sections with a comment like "// ... rest of code ...",
          "// ... keep existing code ...", "// ... code remains the same".
        - Be precise with the location of these comments within your edit snippet.
          A less intelligent model will use the context clues you provide to accurately
          merge your edit snippet.
        - If applicable, it can help to include some concise information about the
          specific code segments you wish to retain "// ... keep calculateTotalFunction ...".
        - If you plan on deleting a section, you must provide the context to delete it.
          Some options:
          1. If the initial code is `Block 1 / Block 2 / Block 3`, and you want to remove
             Block 2, you would output `// ... keep existing code ... / Block 1 / Block 3 /
             // ... rest of code ...`.
          2. If the initial code is `code / Block / code`, and you want to remove Block,
             you can also specify `// ... keep existing code ... / // remove Block /
             // ... rest of code ...`.
        - You must use the comment format applicable to the specific code provided to
          express these truncations.
        - Preserve the indentation and code structure of exactly how you believe the
          final code will look (do not output lines that will not be in the final code
          after they are merged).
        - Be as length efficient as possible without omitting key context.

        To create a new file, simply specify the content of the file in the `edit_snippet` field.
        """
        return apply_file_logic(
            client=client,
            file_path=file_path,
            edit_snippet=edit_snippet,
            instruction=instruction,
            base_dir=config.base_dir,
        )

    # Fast Agentic Search
    search_client = RelaceSearchClient(config)
    search_harness = FastAgenticSearchHarness(config, search_client)

    @mcp.tool
    def fast_search(query: str) -> dict[str, Any]:
        """Run Fast Agentic Search over the configured base_dir.

        Use this tool to quickly explore and understand the codebase.
        The search agent will examine files, search for patterns, and report
        back with relevant files and line ranges for the given query.

        This is useful before using fast_apply to understand which files
        need to be modified and how they relate to each other.
        """
        return search_harness.run(query=query)

    _ = fast_apply
    _ = fast_search
