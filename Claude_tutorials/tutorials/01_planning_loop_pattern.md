# The Planning Loop Pattern: Plan-Act-Update for Long-Horizon Tasks

> Maintaining coherence across 50+ step tasks using explicit task tracking

## Overview

The **Plan-Act-Update** loop is the foundational pattern that enables deep agents to maintain coherence during long-running tasks. Without explicit planning, agents tend to lose track of their goals after 10-15 steps.

## The Problem: Context Drift

```
Step 1:  "Research topic X" ✓
Step 5:  "Found 3 relevant papers" ✓
Step 10: "Summarized paper 1" ✓
Step 15: "Wait, what was I doing again?" ✗
```

As conversations grow, the original objective gets buried under tool calls and intermediate results. The agent loses sight of the big picture.

## The Solution: Explicit Task Tracking

The `write_todos` tool provides a persistent task list that survives context changes:

```python
from deepagents import create_deep_agent

# TodoListMiddleware is included by default
agent = create_deep_agent(
    system_prompt="You are a research assistant."
)
```

## The Plan-Act-Update Cycle

### Phase 1: PLAN

When receiving a complex task, immediately create a task list:

```
User: "Research quantum computing advances and write a summary report"

Agent's first action:
Tool Call: write_todos([
    {"content": "Search for recent quantum computing papers", "status": "pending"},
    {"content": "Read and summarize top 5 papers", "status": "pending"},
    {"content": "Identify key themes and breakthroughs", "status": "pending"},
    {"content": "Write summary report", "status": "pending"},
    {"content": "Review and refine report", "status": "pending"},
])
```

### Phase 2: ACT

Before starting work, mark the current task as in_progress:

```
Tool Call: write_todos([
    {"content": "Search for recent quantum computing papers", "status": "in_progress"},
    {"content": "Read and summarize top 5 papers", "status": "pending"},
    ...
])
```

Then execute the task using available tools (web_search, read_file, etc.)

### Phase 3: UPDATE

After completing work, mark completed and move to next task:

```
Tool Call: write_todos([
    {"content": "Search for recent quantum computing papers", "status": "completed"},
    {"content": "Read and summarize top 5 papers", "status": "in_progress"},
    ...
])
```

## Code Example: Research Task

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt="""You are a research assistant.

    CRITICAL: Use the Plan-Act-Update loop for all multi-step tasks:
    1. PLAN: Create todos when you receive a task
    2. ACT: Mark task in_progress, then work on it
    3. UPDATE: Mark completed, update todos with new discoveries

    Always keep exactly ONE task in_progress at a time.
    """
)

# The agent will now naturally follow the PAU loop
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Research the latest advances in transformer architectures"
    }]
})
```

## Best Practices

### 1. Task Granularity

**Too Coarse:**
```
- "Do all the research" ← Too vague
```

**Too Fine:**
```
- "Open browser"
- "Type search query"
- "Press enter"
← Too detailed
```

**Just Right:**
```
- "Search for transformer architecture papers (2024)"
- "Summarize paper: 'Attention is All You Need v2'"
- "Compare findings across papers"
- "Write synthesis report"
```

### 2. Discovery-Driven Updates

As you work, you'll discover new tasks. Add them immediately:

```
Initial Plan:
- "Research X" (in_progress)
- "Write report"

Discovery: "X has 3 sub-components that need separate research"

Updated Plan:
- "Research X" (completed)
- "Research X.1: Component A" (pending)
- "Research X.2: Component B" (pending)
- "Research X.3: Component C" (pending)
- "Synthesize X findings" (pending)
- "Write report" (pending)
```

### 3. Single In-Progress Rule

**Never** have multiple tasks in_progress simultaneously. This maintains focus:

```
❌ BAD:
- "Research A" (in_progress)
- "Research B" (in_progress)  ← Confusing

✓ GOOD:
- "Research A" (in_progress)
- "Research B" (pending)
```

### 4. Completion Criteria

Only mark a task completed when FULLY done:

```
❌ BAD: Mark "Research X" completed after finding 1 paper

✓ GOOD: Mark "Research X" completed after thorough search,
        add new task "Deep dive on promising paper Y" if needed
```

## Integration with Subagents

When delegating to subagents, they also have TodoListMiddleware:

```python
# Main agent's todos
- "Coordinate research project" (in_progress)
- "Synthesize results" (pending)

# Subagent (spawned via task()) has its own todos
- "Search for papers on topic A" (in_progress)
- "Summarize findings" (pending)
```

Each subagent maintains independent task tracking within its isolated context.

## Debugging: Viewing the Todo State

The todo list is part of the agent state:

```python
result = agent.invoke({"messages": [...]})

# Access todos from state
todos = result.get("todos", [])
for todo in todos:
    print(f"[{todo['status']}] {todo['content']}")
```

## Anti-Patterns to Avoid

### 1. Forgetting to Update

```
- "Task A" (in_progress)  ← Started but never completed
- "Task B" (pending)
- "Task C" (pending)

[Agent moves on without updating]
```

**Fix:** Always update before moving to next task.

### 2. Overloading with Tasks

```
- 50 pending tasks  ← Overwhelming
```

**Fix:** Keep active list to 5-10 items. Archive completed tasks.

### 3. Vague Tasks

```
- "Do stuff" (pending)  ← Not actionable
```

**Fix:** Tasks should be specific and completeable.

## Related Tutorials

- [Architecting Sub-Agent Hierarchies](02_architecting_subagent_hierarchies.md)
- [Managing Massive Contexts](03_managing_massive_contexts.md)
- [State Management Deep Dive](12_state_management.md)

## Source Code Reference

- TodoListMiddleware: `langchain.agents.middleware.TodoListMiddleware`
- write_todos tool: Automatically added by TodoListMiddleware
- State schema: `todos: list[Todo]` in agent state
