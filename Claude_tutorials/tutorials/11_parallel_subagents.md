# Parallel Subagent Execution

> Maximizing efficiency by running independent tasks concurrently

## Overview

When tasks are independent, run them in parallel to save time:

```
SEQUENTIAL (slow):
───────────────────────────────────────────────────────────
Task A: ████████████ (30s)
                     Task B: ████████████ (30s)
                                          Task C: ████████████ (30s)
Total: 90 seconds
───────────────────────────────────────────────────────────

PARALLEL (fast):
───────────────────────────────────────────────────────────
Task A: ████████████ (30s)
Task B: ████████████ (30s)
Task C: ████████████ (30s)
Total: 30 seconds
───────────────────────────────────────────────────────────
```

## Triggering Parallel Execution

When the model outputs multiple tool calls in ONE message, they execute concurrently:

```python
# Model output with parallel tool calls:
AIMessage(
    content="Let me research these topics in parallel...",
    tool_calls=[
        {"name": "task", "args": {"description": "Research A", "subagent_type": "researcher"}},
        {"name": "task", "args": {"description": "Research B", "subagent_type": "researcher"}},
        {"name": "task", "args": {"description": "Research C", "subagent_type": "researcher"}},
    ]
)
# All three execute simultaneously!
```

## Prompting for Parallelization

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt="""## Parallelization

    ALWAYS parallelize when tasks are independent:

    1. Identify Independent Tasks
       - Tasks with no data dependencies
       - Tasks that don't need each other's output

    2. Launch in Parallel
       - Issue ALL task() calls in ONE message
       - This triggers concurrent execution

    3. Synthesize Results
       - Wait for all results
       - Combine into final output

    Example - Independent Research:
    - "Research topic A" (no dependency)
    - "Research topic B" (no dependency)
    - "Research topic C" (no dependency)
    → Launch ALL THREE in one message!

    Example - Dependent Tasks (DO NOT parallelize):
    - "Research topic A" → produces findings
    - "Analyze findings from A" → needs A's output
    → These MUST be sequential!
    """
)
```

## Identifying Independent Tasks

### Independent (CAN parallelize):

```
User: "Research Apple, Microsoft, and Google's AI strategies"

Tasks:
1. task("Research Apple's AI strategy", "researcher")
2. task("Research Microsoft's AI strategy", "researcher")
3. task("Research Google's AI strategy", "researcher")

These are INDEPENDENT - no task needs another's output.
→ PARALLELIZE!
```

### Dependent (CANNOT parallelize):

```
User: "Research quantum computing, then write a report based on the findings"

Tasks:
1. task("Research quantum computing", "researcher")
2. task("Write report from /research/findings.md", "writer")

Task 2 DEPENDS on Task 1's output.
→ SEQUENTIAL!
```

## Parallel Patterns

### Pattern 1: Fan-Out/Fan-In

```
                    ┌─────────────────┐
                    │  ORCHESTRATOR   │
                    │  (distributes)  │
                    └───────┬─────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
       ┌─────────┐     ┌─────────┐     ┌─────────┐
       │ WORKER1 │     │ WORKER2 │     │ WORKER3 │
       └────┬────┘     └────┬────┘     └────┬────┘
            │               │               │
            └───────────────┼───────────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │  ORCHESTRATOR   │
                    │  (synthesizes)  │
                    └─────────────────┘
```

```python
system_prompt = """
For multi-part research:

1. FAN-OUT: Launch all research tasks in parallel
   - One message with multiple task() calls

2. WAIT: All results return together

3. FAN-IN: Synthesize all findings
   - Read from each subagent's output files
   - Combine into coherent summary
"""
```

### Pattern 2: Pool of Workers

```python
# Same subagent type, different inputs
system_prompt = """
When analyzing multiple documents:
- task("Analyze doc1.pdf", "analyst")
- task("Analyze doc2.pdf", "analyst")
- task("Analyze doc3.pdf", "analyst")

All use 'analyst' subagent but process different inputs.
Launch all in one message for parallel execution.
"""
```

### Pattern 3: Specialist Teams

```python
# Different subagent types, same project
system_prompt = """
For a comprehensive project:
- task("Research market trends", "researcher")
- task("Analyze competitor data", "analyst")
- task("Draft executive summary outline", "writer")

Different specialists work simultaneously.
Launch all in one message.
"""
```

## Communication Between Parallel Tasks

Parallel subagents CANNOT communicate directly. Use files:

```python
system_prompt = """
## Parallel Task Communication

Subagents running in parallel can share data via files:

Setup Phase (sequential):
1. Write shared config to /shared/config.json

Parallel Phase:
2. task("Process using /shared/config.json", "worker") × N

Synthesis Phase (sequential):
3. Each worker writes to /results/worker_N.json
4. Orchestrator reads and combines all results

KEY: The /shared/ directory is visible to all subagents.
"""
```

## Error Handling in Parallel Tasks

When one parallel task fails:

```python
system_prompt = """
## Parallel Error Handling

If one parallel task fails:

1. Other tasks continue (they're independent)
2. You receive error for failed task
3. Handle failed task separately:
   - Retry with adjusted parameters
   - Fall back to alternative approach
   - Note partial completion

Example:
- task("Research A") → Success
- task("Research B") → Error: rate limit
- task("Research C") → Success

Action: Retry B after brief pause, synthesize A and C immediately.
"""
```

## Performance Tips

### 1. Right-Size Parallelism

```python
# ❌ TOO MUCH: 20 parallel tasks
# May overwhelm API limits, memory

# ✓ GOOD: 3-5 parallel tasks
# Manageable, significant speedup
```

### 2. Balance Task Sizes

```python
# ❌ UNBALANCED: Mixed task sizes
# task("Quick lookup")         → 5 seconds
# task("Deep research")        → 5 minutes
# Total time = slowest task

# ✓ BALANCED: Similar task sizes
# task("Research section 1")   → ~2 minutes
# task("Research section 2")   → ~2 minutes
# task("Research section 3")   → ~2 minutes
# Efficient parallel execution
```

### 3. Consider Dependencies Early

```python
# Plan your task graph:
#
#     [A] [B] [C]    ← Independent, parallelize
#       \  |  /
#        [D]         ← Depends on A,B,C, wait
#         |
#        [E]         ← Depends on D, sequential
```

## Complete Example

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt="""You are a research coordinator.

    ## Parallelization Protocol

    1. ANALYZE the request for parallelizable tasks
    2. IDENTIFY dependencies (what needs what)
    3. GROUP independent tasks
    4. LAUNCH parallel tasks in ONE message
    5. SYNTHESIZE results after all complete

    ## Example Workflow

    User: "Compare the AI strategies of 5 tech companies"

    Analysis:
    - Each company research is INDEPENDENT
    - Comparison requires ALL research

    Execution:
    Message 1: [5 parallel task() calls for research]
    Message 2: [After all complete, synthesize comparison]

    ## File Convention

    Parallel tasks write to: /research/{company}/findings.md
    Synthesis writes to: /output/comparison.md
    """
)
```

## Related Tutorials

- [Architecting Sub-Agent Hierarchies](02_architecting_subagent_hierarchies.md)
- [Context Quarantine](06_context_quarantine.md)
- [Hierarchical Communication](17_hierarchical_communication.md)
