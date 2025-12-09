# Relace Fast Apply MCP

基於 [FastMCP 2.x](https://github.com/jlowin/fastmcp) 的 MCP Server，整合 [Relace Instant Apply](https://relace.run/) API 進行高速程式碼合併。

## 功能

- **`relace_apply_file`**：將 LLM 產生的 code snippet merge 回本地檔案
- **dry_run 模式**：預覽合併結果而不實際寫入檔案
- **自動重試**：5xx 錯誤與網路問題自動重試
- **結構化 logging**：JSONL 格式，含 trace_id 與 latency
- **健康檢查**：啟動時驗證設定與環境

## 安裝

### 方式 1：使用 uvx/pipx（推薦，免安裝）

```bash
# 從 PyPI 直接執行（發佈後可用）
uvx relace-mcp
# 或
pipx run relace-mcp
```

### 方式 2：使用 uv 從本地專案執行

```bash
# 直接從專案目錄執行
uv run --directory /path/to/relace-mcp relace-mcp
```

### 方式 3：使用 pip 安裝

```bash
pip install relace-mcp  # 或 pip install -e . 本地開發
relace-mcp              # 直接執行
```

## 設定

複製 `.env.example` 為 `.env` 並填入 API Key：

```bash
cp .env.example .env
# 編輯 .env，設定 RELACE_API_KEY
```

### 環境變數

| 變數 | 必填 | 說明 | 預設值 |
|------|------|------|--------|
| `RELACE_API_KEY` | ✅ | Relace API Key（格式：`rlc-xxx...`） | - |
| `RELACE_BASE_DIR` | ⚠️ | 限制檔案存取的根目錄（強烈建議設定） | 當前工作目錄 |
| `RELACE_STRICT_MODE` | ❌ | 嚴格模式，強制安全設定 | `false` |
| `RELACE_ENDPOINT` | ❌ | API 端點 | `https://instantapply.endpoint.relace.run/v1/code/apply` |
| `RELACE_MODEL` | ❌ | 模型名稱 | `relace-apply-3` |
| `RELACE_LOG_PATH` | ❌ | Log 檔案路徑 | `~/.local/state/relace/relace_apply.log` |
| `RELACE_LOG_LEVEL` | ❌ | Log 層級（DEBUG/INFO/WARNING/ERROR） | `INFO` |
| `RELACE_TIMEOUT` | ❌ | API 請求 timeout 秒數 | `60` |
| `RELACE_MAX_RETRIES` | ❌ | 最大重試次數 | `3` |
| `RELACE_RETRY_BASE_DELAY` | ❌ | 重試基礎延遲秒數 | `1.0` |

### 安全建議

**強烈建議**設定 `RELACE_BASE_DIR` 來限制檔案存取範圍，防止路徑遍歷攻擊：

```bash
# 在 .env 或環境變數中設定
RELACE_BASE_DIR=/path/to/your/project
RELACE_STRICT_MODE=true
```

若未設定 `RELACE_BASE_DIR`：
- 預設為當前工作目錄
- 會發出警告提醒
- 若啟用 `RELACE_STRICT_MODE`，則拒絕啟動

更多安全設定請參閱 [docs/security/hardening.md](docs/security/hardening.md)。

## 啟動方式

### 1. Console Script（推薦）

```bash
# 安裝後直接執行
relace-mcp

# 或使用 uvx（免安裝）
uvx relace-mcp

# 或使用 pipx
pipx run relace-mcp
```

### 2. Python Module

```bash
# 安裝後
python -m relace_mcp

# 或從專案目錄
uv run python -m relace_mcp
```

### 3. FastMCP CLI（進階）

```bash
# 使用 build_server() factory function
uv run --with fastmcp fastmcp run relace_mcp.server:build_server
```

## MCP Host 設定

### Claude Desktop / Cursor（推薦配置）

```json
{
  "mcpServers": {
    "relace": {
      "command": "uvx",
      "args": ["relace-mcp"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/path/to/allowed/directory",
        "RELACE_STRICT_MODE": "true"
      }
    }
  }
}
```

### 本地開發配置

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/relace-mcp",
        "run",
        "relace-mcp"
      ],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/path/to/allowed/directory",
        "RELACE_STRICT_MODE": "true"
      }
    }
  }
}
```

### Windsurf

在 `~/.codeium/windsurf/mcp_config.json` 中加入：

```json
{
  "mcpServers": {
    "relace": {
      "command": "uvx",
      "args": ["relace-mcp"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/path/to/allowed/directory",
        "RELACE_STRICT_MODE": "true"
      }
    }
  }
}
```

## 工具使用

### `relace_apply_file`

```python
# 參數
file_path: str        # 要修改的檔案路徑
edit_snippet: str     # 要 merge 的程式碼片段
instruction: str      # （選填）自然語言說明
dry_run: bool         # （選填）若為 True，只預覽不寫入

# 回傳
{
    "file_path": "...",
    "instruction": "...",
    "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...},
    "merged_code_preview": "...",  # 前 4000 字元預覽
    "dry_run": false
}
```

## 文檔

- [Security Hardening Guide](docs/security/hardening.md) - 安全強化指南
- [Observability Guide](docs/operations/observability.md) - 監控與可觀測性

## License

MIT
