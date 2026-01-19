from relace_mcp.lsp.languages.base import LanguageServerConfig

TYPESCRIPT_CONFIG = LanguageServerConfig(
    language_id="typescript",
    file_extensions=(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
    command=["typescript-language-server", "--stdio"],
    config_files=("tsconfig.json", "jsconfig.json", "package.json"),
    install_hint="npm i -g typescript-language-server typescript",
    initialization_options={},
    workspace_config={},
)
