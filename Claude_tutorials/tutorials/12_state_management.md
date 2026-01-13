# State Management Deep Dive

> Understanding how agent state flows through the LangGraph system

## State Architecture

Deep agents use LangGraph's state management:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT STATE STRUCTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  AgentState (composed from middleware):                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  messages: Annotated[list[AnyMessage], add_messages]                │   │
│  │  # Conversation history with reducer for merging                    │   │
│  │                                                                      │   │
│  │  todos: list[Todo]                                                  │   │
│  │  # Task list from TodoListMiddleware                                │   │
│  │                                                                      │   │
│  │  files: Annotated[dict[str, FileData], file_data_reducer]           │   │
│  │  # Virtual filesystem from FilesystemMiddleware                     │   │
│  │                                                                      │   │
│  │  memory_contents: Annotated[dict[str, str], PrivateStateAttr]       │   │
│  │  # Loaded AGENTS.md content (private, not checkpointed)             │   │
│  │                                                                      │   │
│  │  skills_metadata: Annotated[list[SkillMetadata], PrivateStateAttr]  │   │
│  │  # Loaded skill info (private)                                      │   │
│  │                                                                      │   │
│  │  structured_response: Any                                           │   │
│  │  # Structured output (if response_format configured)                │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## State Reducers

Reducers define how state updates merge:

### Messages Reducer (`add_messages`)

```python
# New messages are APPENDED to existing messages
# Handles deduplication by message ID

state = {"messages": [msg1, msg2]}
update = {"messages": [msg3, msg4]}
result = {"messages": [msg1, msg2, msg3, msg4]}
```

### Files Reducer (`file_data_reducer`)

```python
# Supports both updates and DELETIONS
# None value = delete the file

state = {"files": {"/a.txt": FileData, "/b.txt": FileData}}
update = {"files": {"/b.txt": None, "/c.txt": FileData}}  # Delete b, add c
result = {"files": {"/a.txt": FileData, "/c.txt": FileData}}
```

### Default Reducer (replace)

```python
# For fields without custom reducer, new value replaces old
state = {"todos": [todo1]}
update = {"todos": [todo1, todo2]}
result = {"todos": [todo1, todo2]}  # Replaced entirely
```

## State Flow Through Nodes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STATE FLOW                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   START                                                                      │
│     │                                                                        │
│     │ state = initial_state                                                  │
│     │                                                                        │
│     ▼                                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         "agent" NODE                                 │   │
│   │                                                                      │   │
│   │  Input: state (messages, files, todos, ...)                         │   │
│   │                                                                      │   │
│   │  Action: Model generates response                                    │   │
│   │                                                                      │   │
│   │  Output: {"messages": [AIMessage(...)]}                             │   │
│   │          # Merged via add_messages reducer                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                               │                                              │
│                               ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         "tools" NODE                                 │   │
│   │                                                                      │   │
│   │  Input: state with AIMessage containing tool_calls                  │   │
│   │                                                                      │   │
│   │  Action: Execute each tool call                                      │   │
│   │                                                                      │   │
│   │  Output: {"messages": [ToolMessage(...)]}                           │   │
│   │          {"files": {...}}  # If tool modified files                 │   │
│   │          # Each output merged via respective reducer                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                               │                                              │
│                               ▼                                              │
│                        [back to agent]                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Command Pattern for State Updates

Tools that modify state return `Command` objects:

```python
from langgraph.types import Command
from langchain_core.messages import ToolMessage

def write_file(file_path: str, content: str, runtime: ToolRuntime) -> Command:
    """Tool that modifies files state."""

    # Create file data
    file_data = create_file_data(content)

    # Return Command with state update
    return Command(
        update={
            "files": {file_path: file_data},  # Will be merged via file_data_reducer
            "messages": [
                ToolMessage(
                    content=f"Created file {file_path}",
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )
```

## Checkpointing

With a checkpointer, state persists across interrupts:

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

agent = create_deep_agent(
    checkpointer=checkpointer,
    interrupt_on={"write_file": True}
)

config = {"configurable": {"thread_id": "my-thread"}}

# Invoke until interrupt
result = agent.invoke({"messages": [...]}, config)

# State is checkpointed at interrupt
# Resume later:
result = agent.invoke(None, config)  # Continues from checkpoint
```

### What Gets Checkpointed

| State Field | Checkpointed? | Notes |
|-------------|---------------|-------|
| `messages` | Yes | Full conversation history |
| `todos` | Yes | Task state preserved |
| `files` | Yes | Virtual filesystem preserved |
| `memory_contents` | No | PrivateStateAttr - reloaded |
| `skills_metadata` | No | PrivateStateAttr - reloaded |
| `structured_response` | Yes | If present |

## Accessing State

### From Tool Runtime

```python
def my_tool(runtime: ToolRuntime) -> str:
    # Access current state
    messages = runtime.state.get("messages", [])
    files = runtime.state.get("files", {})
    todos = runtime.state.get("todos", [])

    return "Tool executed"
```

### From Invoke Result

```python
result = agent.invoke({"messages": [...]})

# Access final state
messages = result.get("messages", [])
files = result.get("files", {})
todos = result.get("todos", [])
```

### From Middleware

```python
class MyMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        # Access state from request
        state = request.state
        messages = state.get("messages", [])

        return handler(request)
```

## Private vs Public State

### Public State

Persisted, visible to all components:

```python
# In state schema
messages: list[AnyMessage]
files: dict[str, FileData]
todos: list[Todo]
```

### Private State (PrivateStateAttr)

Not persisted, reloaded each session:

```python
# In state schema
memory_contents: Annotated[dict[str, str], PrivateStateAttr]
skills_metadata: Annotated[list[SkillMetadata], PrivateStateAttr]
```

**Why Private?**
- Memory is reloaded from files anyway
- Skills are re-scanned from directories
- Reduces checkpoint size

## State Isolation in Subagents

Subagents receive filtered state:

```python
# Main agent state
main_state = {
    "messages": [100 messages],
    "todos": [tasks],
    "files": {files},
    "memory_contents": {memories},
}

# Subagent receives (context quarantine)
subagent_state = {
    "messages": [HumanMessage("task description")],  # Fresh!
    "files": {files},  # Shared
    "memory_contents": {memories},  # Inherited
    # NO todos
    # NO main agent messages
}
```

## Custom State Schema

Add custom fields via `context_schema`:

```python
from typing import TypedDict

class MyContext(TypedDict):
    user_id: str
    session_id: str
    custom_data: dict

agent = create_deep_agent(
    context_schema=MyContext,
)

# Now state includes your custom fields
result = agent.invoke({
    "messages": [...],
    "user_id": "user123",
    "session_id": "sess456",
    "custom_data": {"key": "value"}
})
```

## State Best Practices

### 1. Don't Mutate State Directly

```python
# ❌ BAD: Direct mutation
runtime.state["files"]["/new.txt"] = file_data

# ✓ GOOD: Return Command
return Command(update={"files": {"/new.txt": file_data}})
```

### 2. Use Appropriate Reducers

```python
# For lists that should append:
messages: Annotated[list[Message], add_messages]

# For dicts with delete support:
files: Annotated[dict[str, FileData], file_data_reducer]

# For simple replacement:
todos: list[Todo]  # No annotation = replace
```

### 3. Keep State Minimal

```python
# ❌ BAD: Store large data in state
{"large_result": "50MB of data"}

# ✓ GOOD: Write to files, reference path
{"result_path": "/data/result.json"}
```

## Related Tutorials

- [Backend Selection Guide](08_backend_selection.md)
- [Context Quarantine](06_context_quarantine.md)
- [Human-in-the-Loop](04_human_in_the_loop.md)
