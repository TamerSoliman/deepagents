# Prompt Caching Strategies

> Optimizing token usage through intelligent caching

## Overview

In long-running agents, the same system prompts and context are sent repeatedly. Prompt caching reduces redundant token processing.

## Caching Mechanism

```
WITHOUT CACHING:
──────────────────────────────────────────────────────────────────────────────
Turn 1: [System Prompt (5000 tokens)] + [User Message] → Process ALL
Turn 2: [System Prompt (5000 tokens)] + [History] + [User Message] → Process ALL
Turn 3: [System Prompt (5000 tokens)] + [History] + [User Message] → Process ALL
Total processed: 15,000+ tokens just for system prompt

WITH CACHING:
──────────────────────────────────────────────────────────────────────────────
Turn 1: [System Prompt (5000 tokens)] + [User Message] → Cache system prompt
Turn 2: [CACHED] + [History] + [User Message] → Reuse cached portion
Turn 3: [CACHED] + [History] + [User Message] → Reuse cached portion
Total processed: 5,000 tokens for system prompt + cache hits
──────────────────────────────────────────────────────────────────────────────
```

## What Gets Cached

### 1. System Prompts

The largest cacheable component:

```python
system_prompt = """
[Large, stable system instructions...]
[Tool descriptions...]
[Behavior guidelines...]
"""

# This entire block can be cached across turns
```

### 2. Memory Files (AGENTS.md)

Loaded once, cached for session:

```python
# MemoryMiddleware loads memory files into system prompt
# These remain stable within a conversation
memory_content = read_file("/memories/AGENTS.md")
# Content injected once, cached thereafter
```

### 3. Skills Content

When skills are loaded, they become cacheable:

```python
# First turn: Load skill
# skill_content added to system prompt

# Subsequent turns:
# skill_content is now cached as part of system prompt
```

## Cache-Friendly Patterns

### Pattern 1: Front-Load Stable Content

```python
system_prompt = """
# STABLE SECTION (cacheable) ─────────────────────────────
[Core instructions that never change]
[Tool definitions]
[Behavioral guidelines]
[Skills content]
[Memory content]

# DYNAMIC SECTION (not cached) ───────────────────────────
Current task: {task}
Previous results: {results}
"""

# Put stable content FIRST for optimal cache hits
```

### Pattern 2: Minimize System Prompt Changes

```python
# ❌ BAD: Changing system prompt each turn
def get_system_prompt(turn_number):
    return f"Turn {turn_number}: Do the thing..."  # Cache invalidated!

# ✓ GOOD: Stable system prompt
system_prompt = "Core instructions that remain constant..."
# Pass dynamic info through messages, not system prompt
```

### Pattern 3: Batch Memory Loading

```python
# ❌ BAD: Loading different memories each turn
# Turn 1: Load /memories/a.md
# Turn 2: Load /memories/b.md
# Cache invalidated each turn!

# ✓ GOOD: Load all needed memories upfront
memory_files = [
    "/memories/AGENTS.md",
    "/memories/preferences.md",
    "/memories/context.md"
]
# All loaded at start, cached together
```

## Cache Breakpoints

Understanding what invalidates the cache:

```
CACHE PRESERVED (prefix unchanged):
──────────────────────────────────────────────────────────────────────────────
[System Prompt] → [Memory] → [Skills] → [Message 1] → [Message 2]
                                                       ↑
                                                   New content here
                                                   doesn't break cache

CACHE INVALIDATED (prefix changed):
──────────────────────────────────────────────────────────────────────────────
[System Prompt] → [NEW Memory] → [Skills] → [Message 1]
                  ↑
              Change here invalidates
              everything after it
──────────────────────────────────────────────────────────────────────────────
```

## Subagent Caching Considerations

### Each Subagent Has Its Own Cache

```
ORCHESTRATOR               SUBAGENT A              SUBAGENT B
─────────────             ────────────            ────────────
[Orch Prompt] ─ cached    [SubA Prompt] ─ cached  [SubB Prompt] ─ cached
     │                         │                       │
     ▼                         ▼                       ▼
[Turn 1]                  [Turn 1]                [Turn 1]
[Turn 2]                  [Turn 2]                [Turn 2]
...                       (ends)                  (ends)

Note: Subagent caches are SHORT-LIVED (conversation ends quickly)
Orchestrator cache is LONG-LIVED (persists across many turns)
```

### Optimizing Subagent Prompts

```python
# Subagent prompts should be concise (short conversations)
# Less benefit from caching

subagent = {
    "name": "researcher",
    "description": "Focused web research",  # Keep brief
    "system_prompt": "Research the given topic. Write findings to specified file."
    # Don't over-engineer subagent prompts
}
```

## Measuring Cache Effectiveness

### Token Usage Pattern

```
Ideal pattern (good caching):
──────────────────────────────────────────────────────────────────────────────
Turn 1: Input: 5000 tokens  (system prompt + message)
Turn 2: Input: 1200 tokens  (cached prompt + new message)
Turn 3: Input: 1500 tokens  (cached prompt + more history)

Problem pattern (poor caching):
──────────────────────────────────────────────────────────────────────────────
Turn 1: Input: 5000 tokens
Turn 2: Input: 5500 tokens  (no cache hit, rebuilt prompt)
Turn 3: Input: 6000 tokens  (no cache hit, rebuilt prompt)
```

## Best Practices

### 1. Structure Prompts for Caching

```python
# Good structure:
system_prompt = """
## Core Instructions (STABLE - cacheable)
{core_instructions}

## Tool Definitions (STABLE - cacheable)
{tool_definitions}

## Loaded Skills (STABLE within session)
{skills_content}

## Memory (STABLE within session)
{memory_content}
"""
# Dynamic content goes in messages, not system prompt
```

### 2. Avoid Dynamic System Prompts

```python
# ❌ Don't do this
system_prompt = f"The time is {datetime.now()}. Instructions..."

# ✓ Do this instead
system_prompt = "Core instructions..."
# Pass time in message: "Current time: {datetime.now()}"
```

### 3. Consistent Memory Loading Order

```python
# Always load memories in the same order
memory_paths = sorted(["/memories/a.md", "/memories/b.md"])
# Sorting ensures consistent ordering = consistent cache key
```

## Related Tutorials

- [Managing Massive Contexts](03_managing_massive_contexts.md)
- [Skills System](09_skills_system.md)
- [Long-Term Memory](05_long_term_memory.md)
