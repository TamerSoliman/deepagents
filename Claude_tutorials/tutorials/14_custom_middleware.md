# Building Custom Middleware

> Extending agent capabilities through the middleware pattern

## Overview

Middleware intercepts and modifies agent behavior at key points. Creating custom middleware lets you add new capabilities without modifying core agent logic.

## Middleware Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MIDDLEWARE STACK                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Message                                                                │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────┐                                                         │
│  │ Middleware 1    │◄── before_agent() called first                         │
│  └────────┬────────┘                                                         │
│           ▼                                                                  │
│  ┌─────────────────┐                                                         │
│  │ Middleware 2    │◄── before_agent() called second                        │
│  └────────┬────────┘                                                         │
│           ▼                                                                  │
│  ┌─────────────────┐                                                         │
│  │ Middleware 3    │◄── before_agent() called third                         │
│  └────────┬────────┘                                                         │
│           ▼                                                                  │
│     ┌───────────┐                                                            │
│     │   MODEL   │◄── wrap_model_call() wraps this                           │
│     └─────┬─────┘                                                            │
│           ▼                                                                  │
│     ┌───────────┐                                                            │
│     │   TOOLS   │◄── wrap_tool_call() wraps each tool                       │
│     └─────┬─────┘                                                            │
│           ▼                                                                  │
│       Response                                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Middleware Protocol

Every middleware implements this protocol:

```python
from typing import Protocol, Callable, Any, Sequence
from langchain_core.messages import BaseMessage

class MiddlewareProtocol(Protocol):
    """Protocol that all middleware must follow."""

    def before_agent(
        self,
        messages: Sequence[BaseMessage],
        config: dict
    ) -> tuple[Sequence[BaseMessage], dict]:
        """
        Called before agent processes messages.

        Returns:
            Modified (messages, config) tuple
        """
        ...

    def wrap_model_call(
        self,
        call_next: Callable,
        messages: Sequence[BaseMessage],
        config: dict
    ) -> Any:
        """
        Wraps the model invocation.

        Args:
            call_next: Function to call the next layer
            messages: Current messages
            config: Current config

        Returns:
            Model response (possibly modified)
        """
        ...

    def wrap_tool_call(
        self,
        call_next: Callable,
        tool_name: str,
        tool_input: dict,
        config: dict
    ) -> Any:
        """
        Wraps individual tool calls.

        Args:
            call_next: Function to call the actual tool
            tool_name: Name of the tool being called
            tool_input: Arguments to the tool
            config: Current config

        Returns:
            Tool result (possibly modified)
        """
        ...
```

## Creating a Simple Middleware

### Example: Logging Middleware

```python
from deepagents.middleware.base import BaseMiddleware
from typing import Callable, Any, Sequence
from langchain_core.messages import BaseMessage
import logging

class LoggingMiddleware(BaseMiddleware):
    """Logs all agent activity for debugging."""

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)

    def before_agent(
        self,
        messages: Sequence[BaseMessage],
        config: dict
    ) -> tuple[Sequence[BaseMessage], dict]:
        """Log incoming messages."""
        self.logger.info(f"Agent receiving {len(messages)} messages")
        self.logger.debug(f"Last message: {messages[-1].content[:100]}...")
        return messages, config

    def wrap_model_call(
        self,
        call_next: Callable,
        messages: Sequence[BaseMessage],
        config: dict
    ) -> Any:
        """Log model calls with timing."""
        import time

        self.logger.info("Model call starting...")
        start = time.time()

        result = call_next(messages, config)

        elapsed = time.time() - start
        self.logger.info(f"Model call completed in {elapsed:.2f}s")

        return result

    def wrap_tool_call(
        self,
        call_next: Callable,
        tool_name: str,
        tool_input: dict,
        config: dict
    ) -> Any:
        """Log tool calls."""
        self.logger.info(f"Tool call: {tool_name}")
        self.logger.debug(f"Tool input: {tool_input}")

        result = call_next(tool_name, tool_input, config)

        self.logger.debug(f"Tool result: {str(result)[:200]}...")
        return result
```

### Using Custom Middleware

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    middleware=[
        LoggingMiddleware(logger=my_logger),
        # Other middleware...
    ],
    system_prompt="Your agent prompt..."
)
```

## Advanced Middleware Patterns

### Pattern 1: Rate Limiting Middleware

```python
class RateLimitMiddleware(BaseMiddleware):
    """Prevents too many API calls."""

    def __init__(self, max_calls_per_minute: int = 60):
        self.max_calls = max_calls_per_minute
        self.calls = []  # Timestamps of recent calls

    def wrap_model_call(
        self,
        call_next: Callable,
        messages: Sequence[BaseMessage],
        config: dict
    ) -> Any:
        import time

        # Clean old calls
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 60]

        # Check rate limit
        if len(self.calls) >= self.max_calls:
            wait_time = 60 - (now - self.calls[0])
            time.sleep(wait_time)

        # Record this call
        self.calls.append(time.time())

        return call_next(messages, config)
```

### Pattern 2: Content Filtering Middleware

```python
class ContentFilterMiddleware(BaseMiddleware):
    """Filters sensitive content from outputs."""

    def __init__(self, patterns: list[str]):
        import re
        self.patterns = [re.compile(p) for p in patterns]

    def wrap_model_call(
        self,
        call_next: Callable,
        messages: Sequence[BaseMessage],
        config: dict
    ) -> Any:
        result = call_next(messages, config)

        # Filter the response content
        if hasattr(result, 'content'):
            for pattern in self.patterns:
                result.content = pattern.sub('[REDACTED]', result.content)

        return result

    def wrap_tool_call(
        self,
        call_next: Callable,
        tool_name: str,
        tool_input: dict,
        config: dict
    ) -> Any:
        result = call_next(tool_name, tool_input, config)

        # Filter tool results too
        if isinstance(result, str):
            for pattern in self.patterns:
                result = pattern.sub('[REDACTED]', result)

        return result

# Usage
agent = create_deep_agent(
    middleware=[
        ContentFilterMiddleware([
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN pattern
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        ])
    ]
)
```

### Pattern 3: Caching Middleware

```python
class CachingMiddleware(BaseMiddleware):
    """Caches tool results to avoid redundant calls."""

    def __init__(self, cache_tools: list[str] = None):
        self.cache = {}
        self.cache_tools = cache_tools or ["web_search", "read_file"]

    def wrap_tool_call(
        self,
        call_next: Callable,
        tool_name: str,
        tool_input: dict,
        config: dict
    ) -> Any:
        # Only cache specified tools
        if tool_name not in self.cache_tools:
            return call_next(tool_name, tool_input, config)

        # Create cache key
        import json
        cache_key = f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"

        # Check cache
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Execute and cache
        result = call_next(tool_name, tool_input, config)
        self.cache[cache_key] = result

        return result
```

### Pattern 4: Metrics Middleware

```python
class MetricsMiddleware(BaseMiddleware):
    """Collects metrics about agent execution."""

    def __init__(self):
        self.metrics = {
            "model_calls": 0,
            "tool_calls": {},
            "total_tokens": 0,
            "errors": 0
        }

    def wrap_model_call(
        self,
        call_next: Callable,
        messages: Sequence[BaseMessage],
        config: dict
    ) -> Any:
        self.metrics["model_calls"] += 1

        try:
            result = call_next(messages, config)
            # Extract token usage if available
            if hasattr(result, 'usage_metadata'):
                self.metrics["total_tokens"] += result.usage_metadata.get("total_tokens", 0)
            return result
        except Exception as e:
            self.metrics["errors"] += 1
            raise

    def wrap_tool_call(
        self,
        call_next: Callable,
        tool_name: str,
        tool_input: dict,
        config: dict
    ) -> Any:
        self.metrics["tool_calls"][tool_name] = \
            self.metrics["tool_calls"].get(tool_name, 0) + 1

        return call_next(tool_name, tool_input, config)

    def get_metrics(self) -> dict:
        return self.metrics.copy()
```

## Middleware Ordering

Order matters! Middleware executes in stack order:

```python
middleware = [
    LoggingMiddleware(),      # Executes first (outermost)
    RateLimitMiddleware(),    # Executes second
    ContentFilterMiddleware(),# Executes third
    CachingMiddleware(),      # Executes last (innermost)
]

# Flow:
# Request:  Logging → RateLimit → ContentFilter → Caching → Model/Tool
# Response: Caching → ContentFilter → RateLimit → Logging → User
```

## Best Practices

### 1. Keep Middleware Focused

```python
# ❌ BAD: Middleware doing too much
class KitchenSinkMiddleware:
    def wrap_tool_call(...):
        # Logs, caches, filters, rate limits, validates...
        pass

# ✓ GOOD: Single responsibility
class LoggingMiddleware: ...
class CachingMiddleware: ...
class FilteringMiddleware: ...
```

### 2. Handle Errors Gracefully

```python
def wrap_tool_call(self, call_next, tool_name, tool_input, config):
    try:
        return call_next(tool_name, tool_input, config)
    except Exception as e:
        self.logger.error(f"Tool {tool_name} failed: {e}")
        raise  # Re-raise to let agent handle it
```

### 3. Be State-Aware

```python
class StatefulMiddleware(BaseMiddleware):
    def __init__(self):
        self.state = {}  # Per-conversation state

    def before_agent(self, messages, config):
        # Use thread_id for conversation-specific state
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id not in self.state:
            self.state[thread_id] = {}
        return messages, config
```

## Related Tutorials

- [Middleware Composition](07_middleware_composition.md)
- [Building Custom Tools](24_building_custom_tools.md)
- [Error Recovery Patterns](10_error_recovery.md)
