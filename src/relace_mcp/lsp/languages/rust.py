from relace_mcp.lsp.languages.base import LanguageServerConfig

RUST_CONFIG = LanguageServerConfig(
    language_id="rust",
    file_extensions=(".rs",),
    command=["rust-analyzer"],
    config_files=("Cargo.toml", "Cargo.lock"),
    install_hint="rustup component add rust-analyzer",
    initialization_options={},
    workspace_config={},
)
