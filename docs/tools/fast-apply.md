# Fast Apply

`fast_apply` applies edits to a file (or creates a new file) with line-accurate merging.

## Requirements

- Default provider (`APPLY_PROVIDER=relace`): set `RELACE_API_KEY`
- Alternative providers: configure `APPLY_PROVIDER` and the corresponding `*_API_KEY` (see [Advanced](../advanced/index.md))

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | ✅ | File path (absolute or relative to `MCP_BASE_DIR`) |
| `edit_snippet` | ✅ | Code with truncation placeholders |
| `instruction` | ❌ | Hint for disambiguation |

### `edit_snippet` placeholders

Use truncation placeholders to keep context short:

- `// ... existing code ...` (C/JS/TS)
- `# ... existing code ...` (Python/shell)

## Example

```json
{
  "path": "src/example.py",
  "edit_snippet": "# ... existing code ...\n\ndef hello():\n    print('world')\n\n# ... existing code ...",
  "instruction": "Add hello() helper"
}
```

## Returns

UDiff of changes, or confirmation for new files.

## Tips

- Provide `instruction` when the edit location is ambiguous.
- If you see `NEEDS_MORE_CONTEXT`, include a few real lines before/after the target.
