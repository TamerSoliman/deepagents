# Backend Selection Guide

> Choosing the right storage strategy for your use case

## Overview

The backend determines where files are stored and how they persist:

| Backend | Persistence | Scope | Use Case |
|---------|-------------|-------|----------|
| StateBackend | Ephemeral | Single thread | Default, working files |
| StoreBackend | Persistent | Cross-thread | Long-term memory |
| FilesystemBackend | Persistent | Disk | Real file access |
| CompositeBackend | Mixed | Configurable | Hybrid needs |

## StateBackend (Default)

Files stored in LangGraph agent state.

```python
from deepagents import create_deep_agent

# StateBackend is used by default
agent = create_deep_agent(
    system_prompt="You are helpful."
)
```

### Characteristics

- **Ephemeral**: Files lost when conversation ends
- **Fast**: No I/O overhead
- **Checkpointed**: Survives interrupts if checkpointer configured
- **No setup**: Works out of the box

### When to Use

- Development and testing
- Temporary working files
- No persistence requirements
- Single-session tasks

### Example

```python
# Files exist only during this conversation
result = agent.invoke({
    "messages": [{"role": "user", "content": "Create a note file"}]
})
# Agent creates /notes.md in state

# New conversation = fresh filesystem
result2 = agent.invoke({
    "messages": [{"role": "user", "content": "Read the note file"}]
}, config={"configurable": {"thread_id": "new-thread"}})
# /notes.md doesn't exist in new thread
```

## StoreBackend

Files stored in LangGraph's persistent store.

```python
from deepagents import create_deep_agent
from deepagents.backends import StoreBackend
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()  # Use PostgresStore for production

agent = create_deep_agent(
    backend=lambda rt: StoreBackend(rt),
    store=store,
)
```

### Characteristics

- **Persistent**: Files survive across sessions
- **Cross-thread**: Shared between all conversations
- **Namespaced**: Can isolate per user/assistant
- **Requires store**: Must configure BaseStore

### When to Use

- Long-term memory
- User preferences
- Shared knowledge bases
- Cross-session continuity

### Example

```python
# Thread 1: Save preference
agent.invoke(
    {"messages": [{"role": "user", "content": "Remember I prefer Python"}]},
    config={"configurable": {"thread_id": "thread-1"}}
)
# Writes to /preferences.md in store

# Thread 2: Preference persists
agent.invoke(
    {"messages": [{"role": "user", "content": "Write me a hello world"}]},
    config={"configurable": {"thread_id": "thread-2"}}
)
# Can read /preferences.md from store
```

## FilesystemBackend

Files read/written directly to disk.

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

# Full filesystem access (dangerous!)
agent = create_deep_agent(
    backend=FilesystemBackend(),
)

# Sandboxed to specific directory (safer)
agent = create_deep_agent(
    backend=FilesystemBackend(root_dir="/home/user/project"),
)
```

### Characteristics

- **Real files**: Actual disk I/O
- **Persistent**: Files on filesystem
- **Sandboxable**: Restrict to directory
- **Execute support**: Can run commands (SandboxBackendProtocol)

### When to Use

- Code editing tasks
- File system automation
- When real files needed
- Development environments

### Configuration Options

```python
FilesystemBackend(
    root_dir="/project",       # Sandbox to this directory
    virtual_mode=True,         # Treat paths as virtual (stricter)
    max_file_size_mb=10,       # Limit file size (DoS protection)
)
```

### Security Considerations

```python
# ❌ DANGEROUS: Full filesystem access
backend = FilesystemBackend()  # Can read/write anywhere

# ✓ SAFER: Sandboxed
backend = FilesystemBackend(root_dir="/safe/directory")

# ✓ SAFEST: Sandboxed + HITL
agent = create_deep_agent(
    backend=FilesystemBackend(root_dir="/safe"),
    checkpointer=checkpointer,
    interrupt_on={"write_file": True, "edit_file": True}
)
```

## CompositeBackend

Route operations to different backends by path.

```python
from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    StateBackend,
    StoreBackend,
    FilesystemBackend,
)

def create_backend(runtime):
    return CompositeBackend(
        default=StateBackend(runtime),  # For /working/*
        routes={
            "/memories/": StoreBackend(runtime),  # Persistent
            "/code/": FilesystemBackend(root_dir="/project"),  # Disk
        }
    )

agent = create_deep_agent(
    backend=create_backend,
    store=store,
)
```

### Routing Logic

```
Path: /working/notes.md
  → No route match → StateBackend (ephemeral)

Path: /memories/preferences.md
  → Matches /memories/ → StoreBackend (persistent)

Path: /code/src/main.py
  → Matches /code/ → FilesystemBackend (disk)
```

### Common Patterns

**Working + Memory:**
```python
CompositeBackend(
    default=StateBackend(rt),           # Ephemeral scratch
    routes={
        "/memories/": StoreBackend(rt)  # Persistent memory
    }
)
```

**Virtual + Real:**
```python
CompositeBackend(
    default=StateBackend(rt),                      # Virtual files
    routes={
        "/workspace/": FilesystemBackend(root_dir="/project")  # Real
    }
)
```

**Full Hybrid:**
```python
CompositeBackend(
    default=StateBackend(rt),
    routes={
        "/memories/": StoreBackend(rt),
        "/code/": FilesystemBackend(root_dir="/project"),
        "/sandbox/": DockerSandboxBackend(container="..."),
    }
)
```

## Decision Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BACKEND DECISION MATRIX                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  QUESTION                           │ BACKEND CHOICE                         │
│  ───────────────────────────────────│──────────────────────────────────────│
│  Need files to persist across       │ StoreBackend or FilesystemBackend    │
│  conversations?                     │                                       │
│                                     │                                       │
│  Need to share between threads?     │ StoreBackend                         │
│                                     │                                       │
│  Need access to real filesystem?    │ FilesystemBackend                    │
│                                     │                                       │
│  Need to execute commands?          │ FilesystemBackend (SandboxProtocol)  │
│                                     │                                       │
│  Mixed requirements?                │ CompositeBackend                     │
│                                     │                                       │
│  Simple task, no persistence?       │ StateBackend (default)               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Migration Patterns

### From Ephemeral to Persistent

```python
# Before: Everything ephemeral
agent = create_deep_agent()

# After: Memory path persists
agent = create_deep_agent(
    backend=lambda rt: CompositeBackend(
        default=StateBackend(rt),
        routes={"/memories/": StoreBackend(rt)}
    ),
    store=my_store,
)

# Update prompts to use /memories/ for persistent data
```

### Adding Real File Access

```python
# Before: Virtual only
agent = create_deep_agent()

# After: Add workspace access
agent = create_deep_agent(
    backend=lambda rt: CompositeBackend(
        default=StateBackend(rt),
        routes={"/workspace/": FilesystemBackend(root_dir="/project")}
    ),
)
```

## Performance Considerations

| Backend | Read Speed | Write Speed | Memory Usage |
|---------|------------|-------------|--------------|
| StateBackend | Fast | Fast | In memory |
| StoreBackend | Medium | Medium | Store-dependent |
| FilesystemBackend | Slow (I/O) | Slow (I/O) | Minimal |
| CompositeBackend | Route-dependent | Route-dependent | Composite |

## Related Tutorials

- [Long-Term Memory](05_long_term_memory.md)
- [Composite Backend Routing](20_composite_routing.md)
- [Custom Backends](19_custom_backends.md)
