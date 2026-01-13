# Human-in-the-Loop for Long Tasks

> Pausing deep agents for approval before sensitive operations

## Overview

Some operations are too important to execute without human oversight:
- File modifications to production code
- Executing shell commands
- Making API calls with side effects
- Spending resources (API credits, compute time)

**Human-in-the-Loop (HITL)** lets you pause the agent before these operations.

## Basic Configuration

```python
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

# Checkpointer is REQUIRED for HITL
checkpointer = MemorySaver()

agent = create_deep_agent(
    checkpointer=checkpointer,
    interrupt_on={
        "write_file": True,    # Pause before file writes
        "edit_file": True,     # Pause before file edits
        "execute": True,       # Pause before shell commands
    }
)
```

## How HITL Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HITL EXECUTION FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. Agent receives task                                                     │
│      │                                                                       │
│      ▼                                                                       │
│   2. Agent decides to call write_file                                        │
│      │                                                                       │
│      ▼                                                                       │
│   3. INTERRUPT! Graph pauses before execution                                │
│      │                                                                       │
│      │ ← State saved to checkpointer                                         │
│      │                                                                       │
│      ▼                                                                       │
│   4. Human reviews pending operation                                         │
│      │                                                                       │
│      ├── APPROVE → Resume, execute operation                                 │
│      │                                                                       │
│      ├── MODIFY → Update tool call, resume                                   │
│      │                                                                       │
│      └── REJECT → Cancel operation, resume with error                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Interrupt Configuration Options

### Simple Boolean

```python
interrupt_on={
    "write_file": True,  # Always interrupt
}
```

### Conditional Interrupts

```python
from langchain.agents.middleware import InterruptOnConfig

interrupt_on={
    "write_file": InterruptOnConfig(
        # Only interrupt for specific paths
        condition=lambda tool_call: "/production/" in tool_call["args"]["file_path"]
    ),
    "execute": InterruptOnConfig(
        # Only interrupt for dangerous commands
        condition=lambda tool_call: "rm" in tool_call["args"]["command"]
    ),
}
```

## Complete HITL Workflow

```python
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

agent = create_deep_agent(
    checkpointer=checkpointer,
    interrupt_on={"write_file": True, "execute": True}
)

# Configuration for tracking conversation
config = {"configurable": {"thread_id": "my-session"}}

# Step 1: Start the agent
result = agent.invoke(
    {"messages": [{"role": "user", "content": "Create a new config file"}]},
    config=config
)

# Step 2: Check if interrupted
if result.get("__interrupt__"):
    print("Agent wants to execute:")
    pending_tool_calls = result["messages"][-1].tool_calls
    for tc in pending_tool_calls:
        print(f"  Tool: {tc['name']}")
        print(f"  Args: {tc['args']}")

    # Step 3: Get human decision
    decision = input("Approve? (y/n/modify): ")

    if decision == "y":
        # Resume with approval
        result = agent.invoke(None, config=config)
    elif decision == "n":
        # Resume with rejection
        from langchain_core.messages import ToolMessage
        rejection = ToolMessage(
            content="Operation rejected by user",
            tool_call_id=pending_tool_calls[0]["id"]
        )
        result = agent.invoke({"messages": [rejection]}, config=config)
```

## Approval Patterns

### Pattern 1: Batch Approval

Multiple tool calls can be pending. Review all at once:

```python
if result.get("__interrupt__"):
    pending = result["messages"][-1].tool_calls

    print(f"Agent wants to execute {len(pending)} operations:")
    for i, tc in enumerate(pending):
        print(f"\n[{i+1}] {tc['name']}")
        print(f"    {tc['args']}")

    choice = input("Approve all? (y/n): ")
    if choice == "y":
        result = agent.invoke(None, config=config)
```

### Pattern 2: Selective Approval

Approve some operations, reject others:

```python
if result.get("__interrupt__"):
    pending = result["messages"][-1].tool_calls
    responses = []

    for tc in pending:
        print(f"\n{tc['name']}: {tc['args']}")
        choice = input("Approve this? (y/n): ")

        if choice == "n":
            responses.append(ToolMessage(
                content="Rejected by user",
                tool_call_id=tc["id"]
            ))

    if responses:
        result = agent.invoke({"messages": responses}, config=config)
    else:
        result = agent.invoke(None, config=config)
```

### Pattern 3: Modification Before Approval

Allow human to modify the operation:

```python
if result.get("__interrupt__"):
    tc = result["messages"][-1].tool_calls[0]

    print(f"Agent wants to write to: {tc['args']['file_path']}")
    print(f"Content preview: {tc['args']['content'][:200]}...")

    new_path = input(f"Change path? (enter for original): ")
    if new_path:
        tc['args']['file_path'] = new_path

    # Resume with modified tool call
    result = agent.invoke(None, config=config)
```

## HITL for Subagents

Subagents can also have HITL:

```python
subagents = [
    {
        "name": "coder",
        "description": "Writes and executes code",
        "system_prompt": "...",
        "tools": [python_repl],
        "interrupt_on": {"execute": True},  # HITL for subagent
    }
]

agent = create_deep_agent(
    subagents=subagents,
    checkpointer=checkpointer,
    interrupt_on={"task": False},  # Don't interrupt task delegation itself
)
```

## Building a HITL UI

Example with simple CLI:

```python
def run_with_hitl(agent, message, config):
    """Run agent with human-in-the-loop approval."""

    result = agent.invoke({"messages": [{"role": "user", "content": message}]}, config)

    while True:
        # Check for interrupts
        if not result.get("__interrupt__"):
            break

        # Display pending operations
        print("\n" + "="*50)
        print("APPROVAL REQUIRED")
        print("="*50)

        pending = result["messages"][-1].tool_calls
        for tc in pending:
            print(f"\nTool: {tc['name']}")
            for key, value in tc['args'].items():
                print(f"  {key}: {value[:100] if isinstance(value, str) else value}")

        # Get decision
        print("\nOptions: [a]pprove, [r]eject, [m]odify")
        choice = input("Choice: ").lower()

        if choice == 'a':
            result = agent.invoke(None, config)
        elif choice == 'r':
            rejections = [
                ToolMessage(content="Rejected", tool_call_id=tc["id"])
                for tc in pending
            ]
            result = agent.invoke({"messages": rejections}, config)
        elif choice == 'm':
            # Implement modification logic
            pass

    return result

# Usage
config = {"configurable": {"thread_id": "interactive-session"}}
result = run_with_hitl(agent, "Refactor the authentication module", config)
```

## Security Best Practices

### 1. Default to Interrupt

```python
# For production, interrupt on all write operations
interrupt_on={
    "write_file": True,
    "edit_file": True,
    "execute": True,
    "task": True,  # Even review subagent tasks
}
```

### 2. Condition-Based Safety

```python
def is_safe_write(tool_call):
    """Only interrupt for non-temp files."""
    path = tool_call["args"]["file_path"]
    safe_prefixes = ["/tmp/", "/working/", "/scratch/"]
    return not any(path.startswith(p) for p in safe_prefixes)

interrupt_on={
    "write_file": InterruptOnConfig(condition=is_safe_write),
}
```

### 3. Audit Logging

```python
def log_approval(tool_call, decision, user):
    """Log all approval decisions for audit."""
    import json
    from datetime import datetime

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_call["name"],
        "args": tool_call["args"],
        "decision": decision,
        "user": user,
    }

    with open("/var/log/agent_approvals.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
```

## Related Tutorials

- [State Management Deep Dive](12_state_management.md)
- [Custom Middleware](14_custom_middleware.md)
- [Error Recovery Patterns](10_error_recovery.md)

## Source Code Reference

- HumanInTheLoopMiddleware: `langchain.agents.middleware.HumanInTheLoopMiddleware`
- InterruptOnConfig: `langchain.agents.middleware.InterruptOnConfig`
- Checkpoint persistence: LangGraph checkpointer documentation
