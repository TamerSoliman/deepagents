# Building Custom Tools

> Extending agent capabilities with domain-specific tools

## Overview

While deepagents provides filesystem tools (read_file, write_file, etc.), you often need custom tools for domain-specific operations like API calls, database queries, or specialized computations.

## Tool Definition Structure

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Method 1: Using @tool decorator
@tool
def my_tool(arg1: str, arg2: int = 10) -> str:
    """
    Brief description of what the tool does.

    Args:
        arg1: Description of first argument
        arg2: Description of second argument with default

    Returns:
        Description of return value
    """
    # Tool implementation
    return f"Result: {arg1}, {arg2}"


# Method 2: Using Pydantic schema
class SearchInput(BaseModel):
    """Input schema for search tool."""
    query: str = Field(description="The search query")
    max_results: int = Field(default=10, description="Maximum results to return")

@tool(args_schema=SearchInput)
def search(query: str, max_results: int = 10) -> str:
    """Search for information."""
    # Implementation
    return f"Found results for: {query}"
```

## Integrating Custom Tools

```python
from deepagents import create_deep_agent

# Define your custom tools
@tool
def web_search(query: str) -> str:
    """Search the web for information."""
    # Implementation
    return search_results

@tool
def database_query(sql: str) -> str:
    """Execute a read-only SQL query."""
    # Implementation
    return query_results

# Create agent with custom tools
agent = create_deep_agent(
    tools=[web_search, database_query],  # Add custom tools
    system_prompt="Use web_search for internet info, database_query for internal data."
)
```

## Tool Design Patterns

### Pattern 1: API Integration Tool

```python
import httpx
from typing import Optional

@tool
def api_request(
    endpoint: str,
    method: str = "GET",
    body: Optional[str] = None
) -> str:
    """
    Make an API request to the internal service.

    Args:
        endpoint: API endpoint path (e.g., "/users/123")
        method: HTTP method (GET, POST, PUT, DELETE)
        body: Optional JSON body for POST/PUT

    Returns:
        JSON response as string
    """
    base_url = "https://api.internal.example.com"

    with httpx.Client() as client:
        response = client.request(
            method=method,
            url=f"{base_url}{endpoint}",
            content=body,
            headers={"Content-Type": "application/json"}
        )
        return response.text
```

### Pattern 2: Database Query Tool

```python
import sqlite3
from typing import List, Dict

@tool
def query_database(sql: str) -> str:
    """
    Execute a read-only SQL query.

    Args:
        sql: SELECT query to execute (no INSERT/UPDATE/DELETE)

    Returns:
        Query results as formatted table
    """
    # Validate read-only
    if not sql.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries allowed"

    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()

    try:
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        # Format as table
        result = " | ".join(columns) + "\n"
        result += "-" * len(result) + "\n"
        for row in rows:
            result += " | ".join(str(cell) for cell in row) + "\n"

        return result
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()
```

### Pattern 3: Computation Tool

```python
import pandas as pd
from io import StringIO

@tool
def analyze_csv(csv_data: str, operation: str) -> str:
    """
    Perform statistical analysis on CSV data.

    Args:
        csv_data: CSV formatted data as string
        operation: One of: describe, correlate, group_by_mean

    Returns:
        Analysis results as formatted text
    """
    df = pd.read_csv(StringIO(csv_data))

    if operation == "describe":
        return df.describe().to_string()
    elif operation == "correlate":
        return df.corr().to_string()
    elif operation == "group_by_mean":
        # Group by first column, mean of rest
        first_col = df.columns[0]
        return df.groupby(first_col).mean().to_string()
    else:
        return f"Unknown operation: {operation}"
```

### Pattern 4: External Service Tool

```python
@tool
def send_notification(
    channel: str,
    message: str,
    priority: str = "normal"
) -> str:
    """
    Send notification to specified channel.

    Args:
        channel: Notification channel (slack, email, sms)
        message: Message content
        priority: Priority level (low, normal, high)

    Returns:
        Confirmation message
    """
    # Implementation would integrate with actual services
    if channel == "slack":
        # Send to Slack
        pass
    elif channel == "email":
        # Send email
        pass
    elif channel == "sms":
        # Send SMS
        pass

    return f"Notification sent to {channel} with {priority} priority"
```

## Tool Safety Considerations

### Input Validation

```python
from pydantic import BaseModel, Field, field_validator

class SafeQueryInput(BaseModel):
    sql: str = Field(description="SQL query to execute")

    @field_validator('sql')
    @classmethod
    def validate_sql(cls, v: str) -> str:
        # Prevent dangerous operations
        dangerous = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 'TRUNCATE']
        upper_sql = v.upper()
        for keyword in dangerous:
            if keyword in upper_sql:
                raise ValueError(f"Dangerous SQL keyword: {keyword}")
        return v

@tool(args_schema=SafeQueryInput)
def safe_query(sql: str) -> str:
    """Execute a validated read-only query."""
    # Implementation
    pass
```

### Rate Limiting

```python
import time
from functools import wraps

def rate_limit(max_calls: int, period: float):
    """Decorator to rate limit tool calls."""
    calls = []

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            # Remove old calls
            calls[:] = [t for t in calls if now - t < period]

            if len(calls) >= max_calls:
                wait = period - (now - calls[0])
                return f"Rate limited. Try again in {wait:.1f} seconds."

            calls.append(now)
            return func(*args, **kwargs)
        return wrapper
    return decorator

@tool
@rate_limit(max_calls=10, period=60.0)
def rate_limited_search(query: str) -> str:
    """Search with rate limiting (10 calls/minute)."""
    # Implementation
    pass
```

### Sandboxing

```python
@tool
def execute_code(code: str, language: str = "python") -> str:
    """
    Execute code in a sandboxed environment.

    Args:
        code: Code to execute
        language: Programming language (python, javascript)

    Returns:
        Execution output
    """
    import subprocess
    import tempfile

    # Create isolated temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write code to file
        if language == "python":
            filepath = f"{tmpdir}/script.py"
            cmd = ["python", filepath]
        elif language == "javascript":
            filepath = f"{tmpdir}/script.js"
            cmd = ["node", filepath]
        else:
            return f"Unsupported language: {language}"

        with open(filepath, "w") as f:
            f.write(code)

        # Execute with timeout and resource limits
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmpdir
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "Execution timed out (30s limit)"
```

## Tool Documentation Best Practices

```python
@tool
def well_documented_tool(
    required_arg: str,
    optional_arg: int = 10,
    flag: bool = False
) -> str:
    """
    One-line summary of what this tool does.

    Detailed description explaining when to use this tool,
    what it's good for, and any important caveats.

    Args:
        required_arg: Clear description of what this should contain.
            Include format expectations (e.g., "JSON string", "file path")
        optional_arg: Description with default behavior.
            Default: 10. Higher values mean more results.
        flag: Boolean flag description.
            When True, enables X behavior.

    Returns:
        Description of return format.
        Example: "JSON object with keys: name, value, timestamp"

    Raises:
        ValueError: When input is invalid (describe conditions)

    Example:
        well_documented_tool("input", optional_arg=20, flag=True)
        → Returns: {"status": "success", "data": [...]}
    """
    pass
```

## Async Tools

For I/O-bound operations:

```python
import asyncio
import httpx

@tool
async def async_web_search(query: str) -> str:
    """Asynchronously search the web."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.search.com/search",
            params={"q": query}
        )
        return response.text

# Multiple async tools run concurrently when called in parallel
```

## Testing Custom Tools

```python
import pytest

def test_my_tool_basic():
    """Test basic functionality."""
    result = my_tool("test", 5)
    assert "test" in result
    assert "5" in result

def test_my_tool_defaults():
    """Test default argument handling."""
    result = my_tool("test")  # Uses default arg2=10
    assert "10" in result

def test_my_tool_error_handling():
    """Test error cases."""
    with pytest.raises(ValueError):
        my_tool("")  # Empty input should raise

def test_my_tool_edge_cases():
    """Test edge cases."""
    # Very long input
    result = my_tool("x" * 10000, 1)
    assert result is not None

    # Unicode input
    result = my_tool("unicode", 1)
    assert result is not None
```

## Related Tutorials

- [Custom Middleware](14_custom_middleware.md)
- [Error Recovery Patterns](10_error_recovery.md)
- [Human in the Loop](04_human_in_the_loop.md)
