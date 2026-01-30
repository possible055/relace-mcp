# Refactoring Analysis Records

> Technical refactoring decision log - focused on "why NOT to refactor"

## Format Specification

Each record follows this structure:

```yaml
- id: UNIQUE_ID          # Format: CATEGORY-NNN (e.g., SYNC-001)
  scope: module/path     # Affected code location
  severity: P0/P1/P2     # Impact level
  status: rejected       # Current decision
  problem:               # What was identified
  rejection_reasons:     # Why NOT to refactor
    - reason 1
    - reason 2
```

## Writing Guidelines

| Rule | Description |
|------|-------------|
| **Language** | All content MUST be written in English |
| **Focus** | Keep only `problem` and `rejection_reasons`; remove auxiliary sections |
| **Brevity** | Each reason should be concise (1-3 sentences per bullet) |
| **Problem** | Describe the identified refactoring opportunity, not the solution |
| **Rejection** | State WHY not to refactor; use UPPERCASE for emphasis on key points |

## Severity Definitions

| Level | Meaning |
|-------|---------|
| P0 | High impact, affects core functionality or has significant duplication |
| P1 | Medium impact, design/structural concerns |
| P2 | Low impact, minor code organization issues |

## Status Definitions

| Status | Meaning |
|--------|---------|
| rejected | Analysis complete, decision made NOT to refactor |
| pending | Under evaluation |
| approved | Decision made to refactor (create implementation ticket) |

## Records

### SYNC-001: Sync/Async Method Duplication

```yaml
id: SYNC-001
scope: src/relace_mcp/tools/search/harness/core.py
severity: P0
status: rejected
problem: |
  _run_search_loop() and _run_search_loop_async() share ~95% identical
  logic (~150 lines each). Differences limited to:
  - chat() vs chat_async()
  - await keyword presence
  - ThreadPoolExecutor wrapping for tool execution
rejection_reasons:
  - |
    CODE GENERATION (unasync): Requires build step, complicates type checking,
    debugging becomes harder (generated code execution). Violates KISS.
  - |
    UNIFIED ASYNC + ADAPTER: asyncio.run() cannot be nested. Would break
    existing API contract when called from async context (RuntimeError).
  - |
    EXTRACT COMMON FUNCTIONS: Would require 10+ parameters, destroy code
    cohesion, scatter logic across small functions. "Prefer clarity over cleverness."
  - |
    Current code is stable with full test coverage. Risk of refactoring
    outweighs benefits.
```

### ARCH-001: Mixin Implicit Coupling

```yaml
id: ARCH-001
scope: src/relace_mcp/tools/search/harness/
severity: P1
status: rejected
problem: |
  ToolCallsMixin depends on ObservedFilesMixin._maybe_record_observed()
  via TYPE_CHECKING declaration. Inheritance order affects method resolution.
rejection_reasons:
  - |
    TYPE_CHECKING coupling is compile-time only, runtime has zero dependency.
    Standard Python pattern for circular import resolution.
  - |
    Method call coupling is intentional design (horizontal reuse via Mixins).
    Alternative (Composition) requires passing 'self' to sub-components,
    creating reverse coupling and manual initialization order management.
  - |
    Would increase code volume by 30-40% without functional improvement.
  - |
    Mixin pattern is widely accepted in Python ecosystem (Django, Flask).
```

### ARCH-002: Elevate tools/apply and tools/search to Top-Level Modules

```yaml
id: ARCH-002
scope: src/relace_mcp/tools/{apply,search}/
severity: P1
status: rejected
problem: |
  Consider elevating tools/apply/ and tools/search/ to top-level modules (src/relace_mcp/apply/,
  src/relace_mcp/search/) to match repo/ structure. Both contain substantial implementation
  code (~369 lines for apply/core.py, ~513 lines for search/harness/core.py) and may benefit
  from clearer separation of concerns.
rejection_reasons:
  - |
    NO SHARED INFRASTRUCTURE ROLE: Unlike repo/ (consumed by both tools/__init__.py and
    repo/retrieval.py), apply/ and search/ are implementation details only used by
    tools/__init__.py. Elevating them would create peer-level modules with no clear
    architectural distinction.
  - |
    CURRENT NESTING IS SEMANTICALLY CORRECT: apply/ and search/ are tool implementations,
    not foundational infrastructure. Nesting under tools/ accurately expresses their
    dependency relationship and namespace scope.
  - |
    ZERO PRACTICAL BENEFIT: The 463-line tools/__init__.py is registration boilerplate,
    not implementation logic. Directory restructuring would not reduce complexity;
    the real issue (if any) is registration layer size, solvable via helper functions.
  - |
    IMPORT PATH REGRESSION: Elevation changes imports from relative (from .apply import ...)
    to absolute (from relace_mcp.apply import ...), requiring updates across tests,
    documentation, and IDE configurations with no functional improvement.
  - |
    EXISTING ORGANIZATION IS SUFFICIENT: search/ already has proper internal organization
    (_impl/, harness/, schemas/ subdirectories). No structural problems exist that
    would justify a breaking change.
```
