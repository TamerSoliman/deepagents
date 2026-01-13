# Context Quarantine: Isolating Subagent Contexts

> How subagents maintain independent context windows

## The Problem: Context Pollution

Without isolation, delegated work pollutes the main context:

```
MAIN AGENT (without quarantine):
─────────────────────────────────────────
│ User: "Research X and write report"    │
│ Agent: Let me research...              │
│ [50 tool calls for research]           │  ← Context bloat!
│ [All intermediate results]             │
│ [All reasoning steps]                  │
│ Agent: Now writing report...           │
│ [20 more tool calls]                   │
│ Final: Here's your report              │
│                                        │
│ CONTEXT USED: 150k tokens              │  ← Overflow risk!
─────────────────────────────────────────
```

## The Solution: Context Quarantine

With quarantine, subagent work stays isolated:

```
MAIN AGENT (with quarantine):
─────────────────────────────────────────
│ User: "Research X and write report"    │
│ Agent: Delegating research...          │
│ Tool: task("Research X", "researcher") │
│ Result: "Research complete. Summary..."│  ← Only summary!
│ Agent: Delegating writing...           │
│ Tool: task("Write report", "writer")   │
│ Result: "Report written to /output/"   │  ← Only result!
│ Agent: Here's your report              │
│                                        │
│ CONTEXT USED: 5k tokens                │  ← Efficient!
─────────────────────────────────────────
```

## How Quarantine Works

### State Partitioning

```python
# What MAIN AGENT has in state:
main_state = {
    "messages": [100+ messages],           # Full conversation history
    "todos": [task list],                  # Planning state
    "files": {"/notes.md": ...},           # Shared filesystem
    "memory_contents": {...},              # Loaded AGENTS.md
    "structured_response": None,           # Output schema
}

# What SUBAGENT receives (QUARANTINED):
subagent_state = {
    "messages": [HumanMessage("Do X")],    # FRESH - only the task!
    "files": {"/notes.md": ...},           # SHARED - same filesystem
    "memory_contents": {...},              # INHERITED - memory access
    # NO todos - independent planning
    # NO structured_response - own output
}
```

### Excluded State Keys

```python
# In SubAgentMiddleware (subagents.py)
_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response"}

# These are NEVER passed to subagents:
# - messages: Subagent gets fresh context with just the task
# - todos: Subagent manages its own planning
# - structured_response: Subagent has own output handling
```

### Result Purification

```python
def _return_command_with_state_update(result: dict, tool_call_id: str) -> Command:
    """What returns to main agent after subagent completes."""

    # Only include non-excluded state (files, etc.)
    state_update = {
        k: v for k, v in result.items()
        if k not in _EXCLUDED_STATE_KEYS
    }

    # Extract ONLY the final message text
    message_text = result["messages"][-1].text

    return Command(
        update={
            **state_update,  # Any file updates
            "messages": [ToolMessage(message_text, tool_call_id=tool_call_id)],
            # ^ JUST the final message, not the full conversation
        }
    )
```

## Visualization

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONTEXT QUARANTINE FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  MAIN AGENT STATE                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ messages: [User, AI, Tool, AI, Tool, AI, Tool, AI, ...]  (100 msgs) │   │
│  │ todos: [{content: "Research", status: "in_progress"}, ...]          │   │
│  │ files: {"/notes.md": FileData, "/data.json": FileData}              │   │
│  │ memory_contents: {"/AGENTS.md": "preferences..."}                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│                    task("Research topic X", "researcher")                   │
│                                    │                                        │
│                         ┌──────────┴──────────┐                             │
│                         │   QUARANTINE GATE   │                             │
│                         │   ─────────────────  │                             │
│                         │   PASS:              │                             │
│                         │   - files            │                             │
│                         │   - memory_contents  │                             │
│                         │                      │                             │
│                         │   BLOCK:             │                             │
│                         │   - messages ❌      │                             │
│                         │   - todos ❌         │                             │
│                         │   - structured_resp ❌│                            │
│                         └──────────┬──────────┘                             │
│                                    │                                        │
│                                    ▼                                        │
│  SUBAGENT STATE (ISOLATED)                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ messages: [HumanMessage("Research topic X")]  ← FRESH CONTEXT       │   │
│  │ files: {"/notes.md": FileData, "/data.json": FileData}  ← SHARED   │   │
│  │ memory_contents: {"/AGENTS.md": "preferences..."}  ← INHERITED      │   │
│  │                                                                      │   │
│  │ [Subagent works: 50 tool calls, intermediate reasoning]             │   │
│  │                                                                      │   │
│  │ Final message: "Research complete. Key findings: A, B, C"           │   │
│  │ files: {..., "/research/findings.md": NEW FILE}                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│                         ┌──────────┴──────────┐                             │
│                         │   PURIFICATION      │                             │
│                         │   ───────────────── │                             │
│                         │   RETURN:           │                             │
│                         │   - Final message   │                             │
│                         │   - File updates    │                             │
│                         │                     │                             │
│                         │   DISCARD:          │                             │
│                         │   - 50 tool calls ❌│                             │
│                         │   - Reasoning ❌    │                             │
│                         │   - Intermediate ❌ │                             │
│                         └──────────┬──────────┘                             │
│                                    │                                        │
│                                    ▼                                        │
│  MAIN AGENT STATE (UPDATED)                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ messages: [..., ToolMessage("Research complete. Key findings: ...")] │   │
│  │ files: {..., "/research/findings.md": NEW}  ← File changes visible  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Benefits of Quarantine

### 1. Context Efficiency

```
Without Quarantine:
- Main agent context: 150k tokens
- Risk of overflow: HIGH

With Quarantine:
- Main agent context: 20k tokens
- Subagent context: 50k tokens (isolated, discarded)
- Risk of overflow: LOW
```

### 2. Clean Abstractions

Main agent doesn't need to know HOW tasks were accomplished:

```
Main agent sees:
"Research complete. Key findings: A, B, C"

Main agent doesn't see:
- 20 web searches performed
- 15 documents read
- 10 failed attempts
- Internal reasoning steps
```

### 3. Parallel Execution

Multiple subagents can run without interfering:

```
Main agent:
├── task("Research A") → Subagent 1 (isolated)
├── task("Research B") → Subagent 2 (isolated)
└── task("Research C") → Subagent 3 (isolated)

Each subagent has its own quarantined context
Results merge cleanly back to main agent
```

## Shared vs. Isolated State

### SHARED (Passes through quarantine):

| State Key | Why Shared |
|-----------|------------|
| `files` | Subagent needs working filesystem |
| `memory_contents` | Subagent needs user preferences |
| `skills_metadata` | Subagent needs available skills |

### ISOLATED (Blocked by quarantine):

| State Key | Why Isolated |
|-----------|--------------|
| `messages` | Subagent gets fresh context |
| `todos` | Subagent manages own planning |
| `structured_response` | Subagent has own output |

## Lateral Communication via Files

Subagents can communicate through the shared filesystem:

```python
# Subagent A writes
write_file("/shared/data.json", research_results)

# Subagent B reads (after A completes)
data = read_file("/shared/data.json")
```

**Important:** This requires orchestrator coordination:

```python
system_prompt = """
When coordinating subagents that need to share data:
1. Subagent A completes and writes to /shared/
2. WAIT for A to complete
3. Subagent B starts and reads from /shared/

Never start dependent subagents in parallel.
"""
```

## Code Example

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt="""You coordinate research projects.

    DELEGATION PATTERN:
    1. Break complex tasks into subtasks
    2. Delegate to subagents via task()
    3. Each subagent works in ISOLATED context
    4. Only final results return to you

    WHAT SUBAGENTS RECEIVE:
    - Your task description (fresh messages)
    - Shared filesystem access
    - Memory/preferences

    WHAT SUBAGENTS DON'T RECEIVE:
    - Your conversation history
    - Your todo list
    - Your intermediate work

    USE THIS TO YOUR ADVANTAGE:
    - Delegate context-heavy work
    - Keep your context clean
    - Synthesize results efficiently
    """
)
```

## Debugging Quarantine

To understand what subagents see:

```python
# Subagent system prompt for debugging
subagent_prompt = """
DEBUG: Log what you received:
1. How many messages in your context?
2. What files are available?
3. What's your task?

Write to /debug/subagent_state.md before starting work.
"""
```

## Related Tutorials

- [Architecting Sub-Agent Hierarchies](02_architecting_subagent_hierarchies.md)
- [Hierarchical Communication](17_hierarchical_communication.md)
- [Parallel Subagents](11_parallel_subagents.md)
