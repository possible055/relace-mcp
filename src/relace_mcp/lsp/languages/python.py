from relace_mcp.lsp.languages.base import LanguageServerConfig

PYTHON_CONFIG = LanguageServerConfig(
    language_id="python",
    file_extensions=(".py", ".pyi"),
    command=["basedpyright-langserver", "--stdio"],
    initialization_options={},
    workspace_config={
        "basedpyright": {
            "analysis": {
                "autoSearchPaths": True,
                "useLibraryCodeForTypes": True,
                "diagnosticMode": "openFilesOnly",
            }
        }
    },
)
