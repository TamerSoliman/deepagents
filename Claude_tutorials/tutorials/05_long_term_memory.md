# Long-Term Memory Across Sessions

> Persisting user preferences and learned knowledge using StoreBackend

## Overview

By default, deep agents use ephemeral storage - files disappear when the conversation ends. **Long-term memory** requires persistent storage that survives across sessions.

## The Storage Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STORAGE HIERARCHY                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SCOPE              │ BACKEND          │ PERSISTENCE                        │
│  ───────────────────│──────────────────│───────────────────────────────────│
│  Single turn        │ StateBackend     │ Lost after turn                    │
│  Single thread      │ StateBackend     │ Lost after thread (with checkpoint)│
│  Cross-thread       │ StoreBackend     │ ✓ Persistent                       │
│  Cross-session      │ StoreBackend     │ ✓ Persistent                       │
│  Real files         │ FilesystemBackend│ ✓ Persistent (on disk)            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Setting Up Long-Term Memory

### Step 1: Configure a Persistent Store

```python
from langgraph.store.memory import InMemoryStore  # For development
# from langgraph.store.postgres import PostgresStore  # For production

store = InMemoryStore()  # Use PostgresStore for production
```

### Step 2: Create Composite Backend

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

def create_backend(runtime):
    """Factory for composite backend with persistent memory."""
    return CompositeBackend(
        default=StateBackend(runtime),  # Ephemeral by default
        routes={
            "/memories/": StoreBackend(runtime),  # Persistent memory
        }
    )

agent = create_deep_agent(
    backend=create_backend,
    store=store,  # Required for StoreBackend
    system_prompt="""You have access to long-term memory.

    Use /memories/ for information that should persist:
    - User preferences
    - Learned patterns
    - Important facts

    Use / (default) for temporary working files.
    """
)
```

## Memory Patterns

### Pattern 1: User Preferences

```markdown
# /memories/user/preferences.md

## Communication Style
- Prefers concise responses
- Likes bullet points
- Appreciates code examples

## Technical Preferences
- Primary language: Python
- Framework: FastAPI
- IDE: VS Code

## Contact Info
- Email: user@example.com
- Timezone: PST
```

### Pattern 2: Project Context

```markdown
# /memories/projects/current.md

## Current Project
Name: E-commerce Dashboard
Stack: React + FastAPI + PostgreSQL

## Key Files
- Frontend entry: /app/src/App.tsx
- API routes: /app/api/routes/
- Database models: /app/models/

## Build Commands
- Dev: npm run dev
- Test: pytest tests/
- Deploy: ./deploy.sh
```

### Pattern 3: Learned Patterns

```markdown
# /memories/patterns/code_style.md

## Learned from User Feedback

### 2024-01-15: Import Organization
User prefers imports grouped as:
1. Standard library
2. Third-party
3. Local imports
Each group separated by blank line.

### 2024-01-16: Error Handling
User wants try/except blocks to log errors
before re-raising. Use logging module.
```

## Automatic Memory Updates

The MemoryMiddleware provides guidelines for when to update memory:

```python
agent = create_deep_agent(
    backend=create_backend,
    store=store,
    memory=["/memories/user/preferences.md"],  # Load at startup
)
```

The agent receives instructions to:
- Update memory immediately when user provides lasting preferences
- Capture feedback patterns for improvement
- Never store credentials or sensitive data

## Code Example: Learning Agent

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()

def backend_factory(runtime):
    return CompositeBackend(
        default=StateBackend(runtime),
        routes={"/memories/": StoreBackend(runtime)}
    )

agent = create_deep_agent(
    backend=backend_factory,
    store=store,
    memory=["/memories/user/preferences.md"],
    system_prompt="""You are a learning assistant.

    MEMORY PROTOCOL:
    1. When user shares preferences, save to /memories/user/preferences.md
    2. When you learn from feedback, save to /memories/patterns/learned.md
    3. When starting a project, create /memories/projects/{name}.md

    LOADING MEMORY:
    - /memories/user/preferences.md is auto-loaded
    - Check /memories/projects/ for project context
    - Check /memories/patterns/ for learned behaviors

    Always acknowledge when you save something to memory.
    """
)

# Session 1: Learn preferences
result1 = agent.invoke({
    "messages": [{"role": "user", "content": "I prefer TypeScript over JavaScript"}]
})
# Agent saves to /memories/user/preferences.md

# Session 2 (new thread): Preferences persist
result2 = agent.invoke({
    "messages": [{"role": "user", "content": "Write me a hello world"}]
}, config={"configurable": {"thread_id": "new-session"}})
# Agent remembers TypeScript preference and uses it
```

## Cross-Thread Memory Sharing

StoreBackend enables memory sharing between threads:

```python
# Thread 1: User sets preference
config1 = {"configurable": {"thread_id": "thread-1"}}
agent.invoke({
    "messages": [{"role": "user", "content": "Remember: I'm John, email john@example.com"}]
}, config=config1)

# Thread 2: Different conversation, same memory
config2 = {"configurable": {"thread_id": "thread-2"}}
result = agent.invoke({
    "messages": [{"role": "user", "content": "Send me an email summary"}]
}, config=config2)
# Agent knows email from shared memory
```

## Multi-User Memory Isolation

Use assistant_id for per-user isolation:

```python
# User A's session
config_a = {
    "configurable": {"thread_id": "user-a-thread"},
    "metadata": {"assistant_id": "user-a"}  # Isolates memory
}

# User B's session
config_b = {
    "configurable": {"thread_id": "user-b-thread"},
    "metadata": {"assistant_id": "user-b"}  # Different memory namespace
}

# Each user has isolated /memories/ storage
```

## Memory Organization Best Practices

```
/memories/
├── user/
│   ├── preferences.md       # General preferences
│   ├── contact.md           # Contact info (no credentials!)
│   └── communication.md     # Communication style
├── projects/
│   ├── project_a.md         # Project A context
│   └── project_b.md         # Project B context
├── patterns/
│   ├── code_style.md        # Learned code patterns
│   ├── feedback.md          # Feedback history
│   └── corrections.md       # Error corrections
└── context/
    ├── team.md              # Team information
    └── workflows.md         # Standard workflows
```

## Memory Maintenance

### Cleaning Old Memory

```python
system_prompt = """
When memory becomes outdated:
1. Read current memory file
2. Remove obsolete sections
3. Edit to keep only relevant info

Memory should be maintained, not just accumulated.
"""
```

### Memory Versioning

```markdown
# /memories/patterns/code_style.md

## Active Patterns

### [2024-01-20] Import Organization
...current pattern...

## Deprecated Patterns

### [2024-01-15] (superseded by 2024-01-20)
...old pattern...
```

## Production Considerations

### 1. Use Persistent Store

```python
# Development
store = InMemoryStore()  # Lost on restart

# Production
from langgraph.store.postgres import PostgresStore
store = PostgresStore(connection_string="postgresql://...")
```

### 2. Memory Size Limits

```python
system_prompt = """
Memory guidelines:
- Keep each file under 500 lines
- Archive old information to /memories/archive/
- Summarize instead of appending indefinitely
"""
```

### 3. Sensitive Data

```python
system_prompt = """
NEVER store in memory:
- API keys or tokens
- Passwords
- Credit card numbers
- Personal identification numbers

If user provides these, acknowledge but do not save.
"""
```

## Related Tutorials

- [Backend Selection Guide](08_backend_selection.md)
- [Composite Backend Routing](20_composite_routing.md)
- [Memory Middleware Deep Dive](annotated_code/04_memory_middleware.py)
