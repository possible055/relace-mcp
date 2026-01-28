# Agentic Search

Natural language codebase exploration using AI agents.

## Overview

`agentic_search` enables you to search your codebase using natural language queries. An AI agent explores your code to find exactly what you're looking for.

## Basic Usage

```python
agentic_search(query="Where is user authentication handled?")
```

**Returns:**

```json
{
  "files": {
    "src/auth/login.py": [[10, 50], [80, 120]],
    "src/middleware/auth.py": [[1, 30]]
  },
  "explanation": "User authentication is handled in two main places...",
  "partial": false
}
```

## Query Guidelines

### ✅ Good Queries

Specific and descriptive:

```python
# Good: Specific function behavior
agentic_search(query="function that validates JWT tokens and extracts user ID")

# Good: Describes what to find
agentic_search(query="where HTTP 4xx errors are caught and transformed to user messages")

# Good: Technical and precise
agentic_search(query="UserService class initialization and dependency injection")
```

### ❌ Bad Queries

Too vague or broad:

```python
# Bad: Too vague
agentic_search(query="auth logic")

# Bad: Too broad
agentic_search(query="error handling")

# Bad: Not specific enough
agentic_search(query="config")
```

## Advanced Queries

### Multi-Component Searches

Search across related components:

```python
agentic_search(
    query="trace the complete request flow from HTTP endpoint to database query for user creation"
)
```

### Implementation Details

Find specific implementation patterns:

```python
agentic_search(
    query="all places where Redis cache is invalidated after database writes"
)
```

### Architecture Exploration

Understand system architecture:

```python
agentic_search(
    query="how does the event bus connect publishers to subscribers, including retry logic"
)
```

## Use Cases

### 1. Bug Investigation

Find where bugs might occur:

```python
agentic_search(
    query="where user session tokens are validated, including expiration checks"
)
```

### 2. Feature Implementation

Locate related code before adding features:

```python
agentic_search(
    query="all API endpoints that handle file uploads, including validation"
)
```

### 3. Code Review

Find code that needs review:

```python
agentic_search(
    query="functions that directly construct SQL queries without parameterization"
)
```

### 4. Refactoring

Identify refactoring targets:

```python
agentic_search(
    query="all usages of the deprecated UserManager class"
)
```

## Best Practices

### Be Specific

Include technical terms and patterns:

```python
# Instead of: "logging"
agentic_search(query="where we log user authentication failures with error codes")
```

### Describe Behavior

Focus on what the code does:

```python
# Instead of: "payment code"
agentic_search(query="functions that process credit card payments and handle Stripe webhooks")
```

### Include Context

Add relevant context to narrow results:

```python
# Instead of: "database queries"
agentic_search(query="PostgreSQL queries that join users table with orders for analytics")
```

## Response Format

### Success Response

```json
{
  "files": {
    "path/to/file.py": [[start_line, end_line], ...],
    ...
  },
  "explanation": "Human-readable explanation of findings",
  "partial": false
}
```

### Partial Results

When search is incomplete:

```json
{
  "files": { ... },
  "explanation": "Found partial results...",
  "partial": true
}
```

## Performance Tips

### 1. Use Specific Queries

More specific = faster results:

```python
# Slow
agentic_search(query="config")

# Fast
agentic_search(query="database connection pool configuration in settings.py")
```

### 2. Install ripgrep

Significantly speeds up file scanning:

```bash
# macOS
brew install ripgrep

# Debian/Ubuntu
sudo apt-get install ripgrep
```

### 3. Limit Scope

Search specific areas when possible:

```python
agentic_search(
    query="authentication middleware in the src/middleware directory"
)
```

## Comparison with Other Tools

| Tool | Speed | Accuracy | Use Case |
|------|-------|----------|----------|
| `grep` | ⚡⚡⚡ | Low | Exact text match |
| `agentic_search` | ⚡⚡ | High | Natural language |
| `agentic_retrieval` | ⚡ | Very High | Complex queries |
| `cloud_search` | ⚡ | High | Cloud semantic search |

## Examples

### Example 1: Find Entry Point

```python
agentic_search(
    query="main application entry point where FastAPI app is created"
)
```

### Example 2: Trace Dependencies

```python
agentic_search(
    query="all imports and usages of the UserRepository class"
)
```

### Example 3: Security Audit

```python
agentic_search(
    query="functions that handle user passwords, including hashing and validation"
)
```

## Troubleshooting

??? question "No results found?"

    1. Make query more specific
    2. Check if code exists in repository
    3. Try alternative phrasing
    4. Enable debug logging: `MCP_LOG_LEVEL=DEBUG`

??? question "Too many results?"

    1. Add more specific terms
    2. Include file/directory context
    3. Describe exact behavior needed

??? question "Slow performance?"

    1. Install `ripgrep`
    2. Make query more specific
    3. Check system resources

## Next Steps

- [Fast Apply](fast-apply.md) - Apply code changes
- [Cloud Search](cloud-search.md) - Cloud semantic search
