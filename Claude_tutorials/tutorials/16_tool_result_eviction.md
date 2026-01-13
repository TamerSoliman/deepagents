# Tool Result Eviction

> Automatically handling large tool outputs

## Overview

Some tool calls return massive results:
- Web searches with many results
- Database queries returning thousands of rows
- API calls with large payloads

Without handling, these bloat context and cause overflow.

## Automatic Eviction

FilesystemMiddleware automatically handles large results:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EVICTION FLOW                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Tool Call                                                                   │
│      │                                                                       │
│      ▼                                                                       │
│  Tool Execution                                                              │
│      │                                                                       │
│      ▼                                                                       │
│  Result Size Check                                                           │
│      │                                                                       │
│      ├── < 20,000 tokens ──► Return normally                                │
│      │                                                                       │
│      └── > 20,000 tokens ──► EVICTION                                       │
│              │                                                               │
│              ├──► Write to /large_tool_results/{tool_call_id}               │
│              │                                                               │
│              └──► Return truncated preview + file pointer                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## What Gets Evicted

```python
# Threshold: ~20,000 tokens (approximately 80,000 characters)
TOOL_RESULT_TOKEN_LIMIT = 20000

# Eviction target:
# /large_tool_results/{sanitized_tool_call_id}
```

## What Agent Sees

When eviction occurs, agent receives:

```
Tool result too large, the result of this tool call abc123 was saved
in the filesystem at this path: /large_tool_results/abc123

You can read the result from the filesystem by using the read_file tool,
but make sure to only read part of the result at a time.
You can do this by specifying an offset and limit in the read_file tool call.

Here are the first 10 lines of the result:
     1	[Preview line 1]
     2	[Preview line 2]
     3	[Preview line 3]
     ...
    10	[Preview line 10]
```

## Working with Evicted Results

### Pattern: Progressive Reading

```python
system_prompt = """
## When Tool Result is Evicted

1. Read the eviction message
   - Note the file path
   - Review the preview

2. Scan the full result
   read_file("/large_tool_results/abc123", limit=100)

3. Find relevant sections
   - Use preview + scan to identify sections
   - grep within the file if needed

4. Read specific sections
   read_file("/large_tool_results/abc123", offset=500, limit=200)

NEVER: read_file("/large_tool_results/abc123")  # Full read defeats purpose!
"""
```

### Example Workflow

```
Tool: web_search("quantum computing")
Result: 100 pages of results (evicted)

Agent receives:
"Tool result too large... saved to /large_tool_results/search_123
Preview:
     1  # Search Results
     2
     3  ## Result 1: Quantum Computing Breakthrough
     4  URL: example.com/quantum
     5  ..."

Agent's approach:
1. read_file("/large_tool_results/search_123", limit=50)
   # See structure of results

2. Identify most relevant results from titles

3. read_file("/large_tool_results/search_123", offset=45, limit=20)
   # Read specific result in detail

4. Extract needed information

5. Continue with task using extracted info
```

## Configuring Eviction

### Disable Eviction

```python
from deepagents.middleware.filesystem import FilesystemMiddleware

# Disable eviction (not recommended)
middleware = FilesystemMiddleware(
    backend=my_backend,
    tool_token_limit_before_evict=None  # Disables eviction
)
```

### Adjust Threshold

```python
# Lower threshold (evict earlier)
middleware = FilesystemMiddleware(
    tool_token_limit_before_evict=10000  # ~40,000 chars
)

# Higher threshold (evict later)
middleware = FilesystemMiddleware(
    tool_token_limit_before_evict=30000  # ~120,000 chars
)
```

## Tools Exempt from Eviction

Filesystem tools are NOT evicted (they handle their own output):

```python
# These tools manage their own output
EXEMPT_TOOLS = ["ls", "read_file", "write_file", "edit_file", "glob", "grep"]

# Only external tools (web_search, api_call, etc.) get evicted
```

## Best Practices

### 1. Expect Large Results

```python
system_prompt = """
When calling tools that might return large results:
- Prepare to handle eviction
- Plan to paginate the evicted file
- Don't assume full result in context
"""
```

### 2. Use Specific Queries

```python
# ❌ May return huge results
web_search("python")

# ✓ More focused, smaller results
web_search("python asyncio error handling best practices")
```

### 3. Process Incrementally

```python
system_prompt = """
For large evicted results:
1. Don't try to read everything
2. Scan for relevant sections
3. Extract only what you need
4. Summarize key points
5. Work from summary
"""
```

## Eviction File Management

### File Naming

```python
# Tool call ID: toolu_01XYZ123
# Sanitized: toolu_01XYZ123 (dots, slashes replaced with _)
# Path: /large_tool_results/toolu_01XYZ123
```

### Cleanup

Evicted files persist in the virtual filesystem. They're cleaned up when:
- StateBackend: Conversation ends
- StoreBackend: Never (persistent)
- FilesystemBackend: Never (on disk)

```python
system_prompt = """
For long-running tasks:
- Large results accumulate in /large_tool_results/
- If no longer needed, you can delete them
- Or organize: move useful data to /research/, delete rest
"""
```

## Related Tutorials

- [Managing Massive Contexts](03_managing_massive_contexts.md)
- [File Pagination Patterns](15_file_pagination.md)
- [Backend Selection Guide](08_backend_selection.md)
