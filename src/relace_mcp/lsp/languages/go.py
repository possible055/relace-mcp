from relace_mcp.lsp.languages.base import LanguageServerConfig

GO_CONFIG = LanguageServerConfig(
    language_id="go",
    file_extensions=(".go",),
    command=["gopls"],
    config_files=("go.mod", "go.sum"),
    install_hint="go install golang.org/x/tools/gopls@latest",
    initialization_options={},
    workspace_config={},
)
