from relace_mcp.lsp.languages.base import LanguageServerConfig

TYPESCRIPT_CONFIG = LanguageServerConfig(
    language_id="typescript",
    file_extensions=(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
    command=["typescript-language-server", "--stdio"],
    config_files=("tsconfig.json", "jsconfig.json", "package.json"),
    install_hint="npm i -g typescript-language-server typescript",
    initialization_options={},
    workspace_config={},
    extension_language_map={
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".js": "javascript",
        ".jsx": "javascriptreact",
        ".mjs": "javascript",
        ".cjs": "javascript",
    },
)
