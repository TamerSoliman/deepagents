# Summarization Strategies

> Compacting conversation history to prevent context overflow

## Overview

Long-running agents accumulate conversation history. Without summarization, context eventually overflows. Summarization compacts older messages while preserving essential information.

## The Context Growth Problem

```
Turn 1:  ████ (2k tokens)
Turn 5:  ████████████ (8k tokens)
Turn 10: ████████████████████████ (20k tokens)
Turn 20: ████████████████████████████████████████████████ (50k tokens)
Turn 30: OVERFLOW! (100k+ tokens)

Without summarization, context grows linearly with conversation length.
```

## Summarization Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SUMMARIZATION TRIGGER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Context Size Check (before each turn)                                       │
│       │                                                                      │
│       ├── < threshold (80% of limit) ──► Continue normally                  │
│       │                                                                      │
│       └── >= threshold ──► SUMMARIZE                                        │
│               │                                                              │
│               ▼                                                              │
│       ┌─────────────────────────────────────────┐                           │
│       │ Summarization Process                    │                           │
│       │                                          │                           │
│       │ 1. Select messages to summarize         │                           │
│       │    (older messages, preserve recent)    │                           │
│       │                                          │                           │
│       │ 2. Generate summary                      │                           │
│       │    (condensed version of content)       │                           │
│       │                                          │                           │
│       │ 3. Replace original with summary        │                           │
│       │    (dramatic token reduction)           │                           │
│       └─────────────────────────────────────────┘                           │
│               │                                                              │
│               ▼                                                              │
│       [System] + [Summary] + [Recent Messages] = Compacted Context          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Summarization Strategies

### Strategy 1: Rolling Window Summary

Keep recent N messages, summarize the rest:

```
BEFORE:
[Sys] [M1] [M2] [M3] [M4] [M5] [M6] [M7] [M8] [M9] [M10]
       └──────────────────┬────────────────────┘
                   80k tokens total

AFTER (keep last 4):
[Sys] [Summary of M1-M6] [M7] [M8] [M9] [M10]
       └──────┬─────────┘
         2k tokens         + recent messages
                           = 20k tokens total
```

```python
system_prompt = """
## Conversation Summarization

When context grows large, I will summarize older messages.
The summary preserves:
- Key decisions made
- Important facts learned
- Current task state
- Relevant file locations

Recent messages remain intact for context continuity.
"""
```

### Strategy 2: Hierarchical Summarization

Summarize summaries as they accumulate:

```
Level 0 (raw messages):
[M1] [M2] [M3] [M4] [M5] [M6] [M7] [M8] [M9] [M10] [M11] [M12]

Level 1 (first summarization):
[Summary A: M1-M4] [Summary B: M5-M8] [M9] [M10] [M11] [M12]

Level 2 (second summarization):
[Meta-Summary: A+B] [Summary C: M9-M10] [M11] [M12]

Each level = 4x compression
```

### Strategy 3: Importance-Based Summarization

Weight messages by importance:

```python
# Message importance factors:
importance_weights = {
    "tool_results": 0.8,      # Usually important
    "user_requests": 1.0,     # Always important
    "agent_reasoning": 0.4,   # Less critical
    "error_messages": 0.9,    # Important for debugging
}

# High importance → Keep longer
# Low importance → Summarize sooner
```

### Strategy 4: Task-Aware Summarization

Summarize completed tasks more aggressively:

```
Active Task Context:
[Task Start] [Research] [Analysis] [Current Work...]
         └──────────────────────────────────────────┘
                    Keep detailed (active)

Completed Task Context:
[Task Start] [... 50 messages ...] [Task Complete] → [Summary: "Completed X"]
         └────────────────────────────────────────┘
              Aggressively compress (done)
```

## What to Preserve in Summaries

### Always Preserve

```python
summary_must_include = """
1. DECISIONS MADE
   - "Decided to use React instead of Vue"
   - "Chose PostgreSQL for database"

2. KEY FACTS DISCOVERED
   - "API rate limit is 100 req/min"
   - "Bug is in authentication module"

3. FILE LOCATIONS
   - "Research saved to /research/findings.md"
   - "Modified files: src/auth.py, tests/test_auth.py"

4. CURRENT STATE
   - "3 of 5 tasks completed"
   - "Waiting for user approval on deploy"

5. ERRORS ENCOUNTERED
   - "Build failed due to missing dependency"
   - "Test suite has 2 failing tests"
"""
```

### Safe to Compress

```python
safe_to_summarize = """
1. DETAILED REASONING
   - Long explanations → Brief conclusion

2. INTERMEDIATE STEPS
   - "Tried X, Y, Z" → "After trying alternatives, chose Z"

3. VERBOSE TOOL OUTPUTS
   - Full file contents → "Read config.yaml (database settings)"

4. EXPLORATORY WORK
   - Search attempts → "Found relevant code in src/utils/"
"""
```

## Implementing Summarization

### Basic Summarization Middleware

```python
class SummarizationMiddleware:
    def __init__(self, threshold_tokens: int = 80000):
        self.threshold = threshold_tokens

    def before_agent(self, messages, config):
        token_count = self._count_tokens(messages)

        if token_count > self.threshold:
            messages = self._summarize(messages)

        return messages, config

    def _summarize(self, messages):
        # Keep system message
        system = messages[0]

        # Keep last N messages
        recent = messages[-8:]

        # Summarize the rest
        to_summarize = messages[1:-8]
        summary = self._generate_summary(to_summarize)

        return [system, summary] + list(recent)
```

### Integration with File System

Leverage the virtual filesystem to offload context:

```python
system_prompt = """
## Long-Term Storage Strategy

Before summarizing, save important details to files:

1. Save detailed findings:
   write_file("/summaries/turn_50.md", detailed_content)

2. Keep brief reference in context:
   "Detailed findings saved to /summaries/turn_50.md"

3. Later, if needed:
   read_file("/summaries/turn_50.md")

This gives you infinite context through file storage.
"""
```

## Summarization vs File Storage

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONTEXT MANAGEMENT OPTIONS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Option 1: SUMMARIZATION                                                     │
│  ─────────────────────────                                                   │
│  - Keeps info in messages                                                    │
│  - Lossy compression                                                         │
│  - Automatic access                                                          │
│  - Good for: Working memory                                                  │
│                                                                              │
│  Option 2: FILE OFFLOAD                                                      │
│  ──────────────────────                                                      │
│  - Moves info to files                                                       │
│  - Lossless storage                                                          │
│  - Requires read_file to access                                              │
│  - Good for: Detailed records                                                │
│                                                                              │
│  Option 3: HYBRID (Best)                                                     │
│  ────────────────────────                                                    │
│  - Summary in messages (what happened)                                       │
│  - Details in files (full records)                                           │
│  - Balance of access and completeness                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Best Practices

### 1. Summarize Proactively

```python
# Don't wait for overflow
# Summarize when reaching 70-80% capacity
threshold = context_limit * 0.75
```

### 2. Preserve Recency

```python
# Always keep recent messages intact
# Agent needs immediate context for coherent responses
keep_recent = 5  # Last 5 exchanges minimum
```

### 3. Include Meta-Information

```python
summary_template = """
## Conversation Summary (turns 1-{end_turn})

### Key Events:
{key_events}

### Decisions Made:
{decisions}

### Current State:
{current_state}

### Files Created/Modified:
{file_changes}

---
(Full conversation continues below)
"""
```

### 4. Test Summary Quality

```python
# Periodically verify summaries capture essential info
# Agent should be able to continue coherently with just summary
```

## Related Tutorials

- [Managing Massive Contexts](03_managing_massive_contexts.md)
- [Long-Term Memory](05_long_term_memory.md)
- [Tool Result Eviction](16_tool_result_eviction.md)
