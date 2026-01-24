# Fast Apply

`fast_apply` 以行级精确合并对文件应用编辑（或创建新文件）。

## 前置要求

- 默认提供商（`APPLY_PROVIDER=relace`）：设置 `RELACE_API_KEY`
- 替代提供商：配置 `APPLY_PROVIDER` 与对应 `*_API_KEY`（参见 [Advanced](../advanced/index.md)）

## 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `path` | ✅ | 文件路径（绝对或相对 `MCP_BASE_DIR`） |
| `edit_snippet` | ✅ | 带截断占位符的代码片段 |
| `instruction` | ❌ | 消歧提示 |

### `edit_snippet` 占位符

使用截断占位符以保持上下文精简：

- `// ... existing code ...`（C/JS/TS）
- `# ... existing code ...`（Python/shell）

## 示例

```json
{
  "path": "src/example.py",
  "edit_snippet": "# ... existing code ...\n\ndef hello():\n    print('world')\n\n# ... existing code ...",
  "instruction": "Add hello() helper"
}
```

## 返回

更改的 UDiff，或新文件的确认信息。

## 提示

- 当编辑位置不明确时，提供 `instruction`。
- 若出现 `NEEDS_MORE_CONTEXT`，补充目标前后几行真实代码。
