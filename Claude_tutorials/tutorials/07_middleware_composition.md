# Middleware Composition: Building Capability Stacks

> Understanding how middleware layers compose to create agent capabilities

## What is Middleware?

Middleware are composable layers that add capabilities to agents:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MIDDLEWARE CONCEPT                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   REQUEST PATH                           RESPONSE PATH                       │
│                                                                              │
│   User Request                           Final Response                      │
│       │                                       ▲                              │
│       ▼                                       │                              │
│   ┌─────────────────────┐               ┌─────────────────────┐             │
│   │ Middleware Layer 1  │───────────────│ Middleware Layer 1  │             │
│   │ (TodoList)          │               │ (TodoList)          │             │
│   └─────────┬───────────┘               └─────────────────────┘             │
│             │                                       ▲                        │
│             ▼                                       │                        │
│   ┌─────────────────────┐               ┌─────────────────────┐             │
│   │ Middleware Layer 2  │───────────────│ Middleware Layer 2  │             │
│   │ (Filesystem)        │               │ (Filesystem)        │             │
│   └─────────┬───────────┘               └─────────────────────┘             │
│             │                                       ▲                        │
│             ▼                                       │                        │
│   ┌─────────────────────┐               ┌─────────────────────┐             │
│   │ Middleware Layer 3  │───────────────│ Middleware Layer 3  │             │
│   │ (SubAgent)          │               │ (SubAgent)          │             │
│   └─────────┬───────────┘               └─────────────────────┘             │
│             │                                       ▲                        │
│             ▼                                       │                        │
│         ┌───────────────────────────────────────────┐                       │
│         │               MODEL CALL                   │                       │
│         │  (System prompt + Tools + Messages)        │                       │
│         └───────────────────────────────────────────┘                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Middleware Capabilities

Each middleware can:

### 1. Add Tools

```python
class FilesystemMiddleware(AgentMiddleware):
    def __init__(self):
        self.tools = [
            read_file_tool,
            write_file_tool,
            edit_file_tool,
            ls_tool,
            glob_tool,
            grep_tool,
        ]
```

### 2. Modify System Prompt

```python
def wrap_model_call(self, request, handler):
    # Add middleware-specific instructions
    new_prompt = request.system_prompt + "\n\n" + FILESYSTEM_INSTRUCTIONS
    return handler(request.override(system_prompt=new_prompt))
```

### 3. Intercept Tool Calls

```python
def wrap_tool_call(self, request, handler):
    # Check tool result size
    result = handler(request)

    if len(result.content) > THRESHOLD:
        # Evict large result to filesystem
        return self._evict_to_file(result)

    return result
```

### 4. Add State Schema

```python
class FilesystemMiddleware(AgentMiddleware):
    state_schema = FilesystemState  # Adds 'files' to state

class MemoryMiddleware(AgentMiddleware):
    state_schema = MemoryState  # Adds 'memory_contents' to state
```

### 5. Run Before/After Agent

```python
def before_agent(self, state, runtime, config):
    """Load data before agent runs."""
    return {"memory_contents": load_memory()}

def after_agent(self, state, result, config):
    """Clean up after agent completes."""
    pass
```

## The Default Middleware Stack

`create_deep_agent()` builds this stack:

```python
middleware_stack = [
    # 1. Planning capability
    TodoListMiddleware(),

    # 2. Memory (if configured)
    MemoryMiddleware(backend=backend, sources=memory),  # Optional

    # 3. Skills (if configured)
    SkillsMiddleware(backend=backend, sources=skills),  # Optional

    # 4. File operations
    FilesystemMiddleware(backend=backend),

    # 5. Subagent delegation
    SubAgentMiddleware(
        default_model=model,
        default_tools=tools,
        subagents=subagents,
    ),

    # 6. Context management
    SummarizationMiddleware(model=model, trigger=trigger, keep=keep),

    # 7. Performance optimization
    AnthropicPromptCachingMiddleware(),

    # 8. Error recovery
    PatchToolCallsMiddleware(),

    # 9. Human oversight (if configured)
    HumanInTheLoopMiddleware(interrupt_on=interrupt_on),  # Optional

    # 10. Custom middleware (user-provided)
    *custom_middleware,
]
```

## Execution Order

**Request path** (top to bottom):
```
User Request
  → TodoListMiddleware.wrap_model_call (adds write_todos instructions)
    → MemoryMiddleware.wrap_model_call (adds memory to prompt)
      → SkillsMiddleware.wrap_model_call (adds skill descriptions)
        → FilesystemMiddleware.wrap_model_call (adds file instructions)
          → SubAgentMiddleware.wrap_model_call (adds task instructions)
            → SummarizationMiddleware.wrap_model_call (may summarize)
              → AnthropicCachingMiddleware.wrap_model_call (adds cache markers)
                → PatchToolCallsMiddleware.wrap_model_call (patches history)
                  → HumanInTheLoopMiddleware.wrap_model_call (may interrupt)
                    → ACTUAL MODEL CALL
```

**Response path** (bottom to top):
```
Model Response
  ← HumanInTheLoopMiddleware (handles interrupts)
    ← PatchToolCallsMiddleware (patches tool calls)
      ← AnthropicCachingMiddleware (cache management)
        ← SummarizationMiddleware (context tracking)
          ← SubAgentMiddleware (subagent invocation)
            ← FilesystemMiddleware (file operations)
              ← SkillsMiddleware (skill access)
                ← MemoryMiddleware (memory updates)
                  ← TodoListMiddleware (task updates)
                    ← Final Response to User
```

## Custom Middleware

### Basic Template

```python
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)

class LoggingMiddleware(AgentMiddleware):
    """Middleware that logs all model calls."""

    def wrap_model_call(self, request, handler):
        print(f"REQUEST: {len(request.messages)} messages")
        print(f"TOOLS: {[t.name for t in request.tools]}")

        response = handler(request)

        print(f"RESPONSE: {response.message.content[:100]}...")
        return response

    async def awrap_model_call(self, request, handler):
        """Async version."""
        print(f"REQUEST: {len(request.messages)} messages")
        response = await handler(request)
        print(f"RESPONSE: {response.message.content[:100]}...")
        return response
```

### Using Custom Middleware

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    middleware=[LoggingMiddleware()],  # Added to stack
    system_prompt="You are helpful."
)
```

### Middleware with State

```python
from langchain.agents.middleware.types import AgentState
from typing import Annotated, NotRequired

class CounterState(AgentState):
    """State that tracks call count."""
    call_count: NotRequired[int]

class CounterMiddleware(AgentMiddleware):
    """Counts model calls."""

    state_schema = CounterState

    def wrap_model_call(self, request, handler):
        # Increment counter
        current = request.state.get("call_count", 0)
        # Note: State updates require Command pattern
        response = handler(request)
        return response
```

## Middleware Interaction Patterns

### Pattern 1: Sequential Enhancement

Each middleware adds to the prompt:

```
Base prompt: "You are helpful"

+ TodoListMiddleware: "Use write_todos for planning..."
+ MemoryMiddleware: "<agent_memory>...</agent_memory>"
+ FilesystemMiddleware: "## Filesystem Tools..."
+ SubAgentMiddleware: "## Task Tool..."

Final prompt: All combined
```

### Pattern 2: Interception Chain

Middleware can intercept and modify:

```
Tool Call: write_file("/code.py", content)
  │
  ├── FilesystemMiddleware: Execute write
  │
  ├── HumanInTheLoopMiddleware: Pause for approval?
  │
  └── Result to agent
```

### Pattern 3: State Composition

State schemas merge:

```python
# Final state includes all middleware state schemas:
{
    "messages": [...],           # Base
    "todos": [...],              # TodoListMiddleware
    "files": {...},              # FilesystemMiddleware
    "memory_contents": {...},    # MemoryMiddleware
    "skills_metadata": [...],    # SkillsMiddleware
}
```

## Best Practices

### 1. Order Matters

Put critical middleware early (executed last on response path):

```python
middleware = [
    SecurityMiddleware(),    # Checked LAST on response
    LoggingMiddleware(),     # Logs near the end
    # ... other middleware ...
]
```

### 2. Keep Middleware Focused

One middleware = one capability:

```python
# ✓ GOOD: Single responsibility
class RateLimitMiddleware: ...
class AuditLogMiddleware: ...
class MetricsMiddleware: ...

# ❌ BAD: Multiple responsibilities
class KitchenSinkMiddleware: ...
```

### 3. Handle Both Sync and Async

```python
class MyMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        # Sync implementation
        return handler(request)

    async def awrap_model_call(self, request, handler):
        # Async implementation
        return await handler(request)
```

## Related Tutorials

- [Custom Middleware Development](14_custom_middleware.md)
- [The Orchestration Loop](annotated_code/01_create_deep_agent.py)
- [Error Recovery Patterns](10_error_recovery.md)
