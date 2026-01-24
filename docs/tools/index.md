# Tools Overview

Relace MCP provides several powerful tools for AI-assisted code editing and exploration.

## Core Tools

### Fast Apply

Apply code edits at **10,000+ tokens/sec** via Relace API.

```python
fast_apply(
    path="src/example.py",
    edit_snippet="def hello():\n    print('world')",
    instruction="Add hello function"
)
```

[:octicons-arrow-right-24: Learn more about Fast Apply](fast-apply.md)

### Agentic Search

Search your codebase using natural language queries.

```python
agentic_search(
    query="Where is user authentication implemented?"
)
```

[:octicons-arrow-right-24: Learn more about Agentic Search](agentic-search.md)

## Cloud Tools

!!! info "Enable Cloud Tools"
    Set `RELACE_CLOUD_TOOLS=1` to enable cloud-based tools.

### Cloud Sync

Upload your codebase for semantic search.

```python
cloud_sync(force=False, mirror=False)
```

### Cloud Search

Semantic search over cloud-synced repositories.

```python
cloud_search(query="authentication logic")
```

[:octicons-arrow-right-24: Learn more about Cloud Search](cloud-search.md)

## Advanced Tools

### Agentic Retrieval

Two-stage semantic + agentic code retrieval.

!!! info "Enable Retrieval"
    Set `MCP_SEARCH_RETRIEVAL=1` to enable this tool.

```python
agentic_retrieval(
    query="function that validates JWT tokens"
)
```

## Tool Comparison

| Tool | Speed | Accuracy | Use Case |
|------|-------|----------|----------|
| `fast_apply` | ⚡⚡⚡ | High | Code editing |
| `agentic_search` | ⚡⚡ | Very High | Local search |
| `cloud_search` | ⚡ | High | Cross-repo search |
| `agentic_retrieval` | ⚡ | Very High | Complex queries |

## Next Steps

- [Fast Apply](fast-apply.md) - Detailed guide
- [Agentic Search](agentic-search.md) - Search strategies
- [Cloud Search](cloud-search.md) - Cloud setup
