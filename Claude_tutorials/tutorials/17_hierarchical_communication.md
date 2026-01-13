# Hierarchical Communication Patterns

> Two-way communication across agent hierarchy levels

## Overview

In hierarchical agent systems, communication flows:
- **Vertically**: Orchestrator ↔ Subagent
- **Laterally**: Subagent ↔ Subagent (via files)

Understanding these patterns is crucial for effective orchestration.

## Vertical Communication

### Downward: Task Assignment

```
ORCHESTRATOR → SUBAGENT

Communication Channel: task() tool with description parameter

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  task(                                                                       │
│      description="Research quantum computing trends...",  ← THE MESSAGE     │
│      subagent_type="researcher"                                             │
│  )                                                                           │
│                                                                              │
│  Subagent receives as:                                                       │
│  messages: [HumanMessage("Research quantum computing trends...")]           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Best Practices for Task Descriptions:**

```python
# ❌ BAD: Vague task
task("Do research", "researcher")

# ✓ GOOD: Specific task with clear expectations
task("""
Research quantum computing trends:
1. Focus on 2024 breakthroughs
2. Include academic and industry sources
3. Write findings to /research/quantum.md
4. Include: key developments, companies involved, timeline

Expected output: 500-1000 words with citations
""", "researcher")
```

### Upward: Result Return

```
SUBAGENT → ORCHESTRATOR

Communication Channel: Final message (text) + File updates

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  Subagent's final AIMessage:                                                 │
│  "Research complete. Key findings:                                           │
│   - 3 major breakthroughs identified                                        │
│   - 5 leading companies analyzed                                            │
│   Full report written to /research/quantum.md"                              │
│                                                                              │
│  Orchestrator receives as:                                                   │
│  ToolMessage("Research complete. Key findings:...")                         │
│  + files: {"/research/quantum.md": FileData}                                │
│                                                                              │
│  NOTE: Subagent's internal conversation (50+ messages) is DISCARDED         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Best Practices for Results:**

```python
subagent_prompt = """
## Final Response Format

Your final message should include:
1. Summary of what was accomplished
2. Key findings/results (brief)
3. Location of detailed output files
4. Any issues or limitations

Example:
"Research complete.

Key findings:
- Finding 1 (high confidence)
- Finding 2 (medium confidence)
- Finding 3 (needs verification)

Detailed report: /research/output.md
Data files: /research/data.json

Note: Could not access source X due to paywall."
"""
```

## Lateral Communication

### File-Based Handoff

Subagents cannot communicate directly. They communicate via shared files:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  SUBAGENT A (Researcher)              SUBAGENT B (Writer)                   │
│  ──────────────────────               ─────────────────────                 │
│                                                                              │
│  1. Performs research                                                        │
│  2. Writes to /shared/findings.md     1. Reads /shared/findings.md          │
│  3. Returns to orchestrator           2. Creates report based on findings  │
│                                       3. Writes to /output/report.md        │
│                                                                              │
│  Timeline:                                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  A starts ────► A writes ────► A ends ────► B starts ────► B reads          │
│                                                                              │
│  KEY: Orchestrator ensures A completes before B starts!                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### File Contract Pattern

```python
# Orchestrator establishes file contracts

system_prompt = """
## File Contracts

Before delegating tasks:
1. Define input/output file locations
2. Specify expected format
3. Document in /contracts/

Example Contract:
---
Producer: researcher
Consumer: writer
File: /shared/research_data.md
Format:
  - Sections: Overview, Findings, Sources
  - Max length: 2000 lines
  - Include: citations with URLs
---

Orchestrator enforces sequence:
1. Researcher writes (produces)
2. Verify file exists
3. Writer reads (consumes)
"""
```

## Communication Patterns

### Pattern 1: Sequential Handoff

```
ORCHESTRATOR
     │
     ├──1──► RESEARCHER ──────► writes /data.md
     │                              │
     │ (wait for completion)        │
     │                              ▼
     ├──2──► ANALYST ◄─────── reads /data.md
     │           │
     │           ▼
     │       writes /analysis.md
     │                              │
     │ (wait for completion)        │
     │                              ▼
     └──3──► WRITER ◄──────── reads /analysis.md
                │
                ▼
            writes /report.md
```

```python
# Orchestrator workflow
system_prompt = """
For sequential handoffs:
1. task("Research topic, write to /data.md", "researcher")
2. WAIT for completion
3. Verify /data.md exists: ls("/")
4. task("Analyze /data.md, write to /analysis.md", "analyst")
5. WAIT for completion
6. task("Write report from /analysis.md", "writer")
"""
```

### Pattern 2: Parallel then Merge

```
ORCHESTRATOR
     │
     ├────────┬────────┬────────► (parallel)
     │        │        │
     ▼        ▼        ▼
   RES_A    RES_B    RES_C
     │        │        │
     ▼        ▼        ▼
/data/a.md /data/b.md /data/c.md
     │        │        │
     └────────┼────────┘
              │
              ▼ (after all complete)
           MERGER
              │
              ▼
        /output/combined.md
```

```python
system_prompt = """
For parallel research:
1. Launch all in ONE message:
   - task("Research A, write to /data/a.md", "researcher")
   - task("Research B, write to /data/b.md", "researcher")
   - task("Research C, write to /data/c.md", "researcher")

2. All complete, files ready

3. task("Merge /data/*.md into /output/combined.md", "writer")
"""
```

### Pattern 3: Feedback Loop

```
ORCHESTRATOR
     │
     ├──1──► DRAFTER ──────────► writes /draft.md
     │                              │
     │                              ▼
     ├──2──► REVIEWER ◄────────── reads /draft.md
     │           │
     │           ▼
     │       writes /feedback.md
     │                              │
     │                              ▼
     └──3──► REVISER ◄─────────── reads /draft.md + /feedback.md
                │
                ▼
            writes /final.md
```

## Error Handling in Communication

### Missing File Error

```python
system_prompt = """
## Handling Missing Files

If subagent B expects file from subagent A but it's missing:

1. Check if A completed:
   - Read A's final message
   - Check for errors

2. If A failed:
   - Retry A with adjusted parameters
   - Or use fallback data

3. If A succeeded but file missing:
   - Check file path (typo?)
   - Check if A wrote to different location
   - Read A's output for clues
"""
```

### Format Mismatch

```python
system_prompt = """
## Handling Format Issues

If file exists but format unexpected:

1. Read file to understand actual format
2. Either:
   a. Adjust consumer to handle actual format
   b. Ask producer to rewrite in expected format
   c. Add transformation step
"""
```

## Best Practices

### 1. Clear File Contracts

```python
# Document expected file formats
write_file("/contracts/research_output.md", """
# Research Output Contract

## File: /research/{topic}.md

## Structure:
1. YAML frontmatter with metadata
2. ## Summary section
3. ## Key Findings section (bullet points)
4. ## Sources section (with URLs)

## Constraints:
- Max 1500 lines
- All claims must have source
- Use markdown formatting
""")
```

### 2. Explicit Paths

```python
# Always use absolute paths
# ❌ task("Write to findings.md", "researcher")
# ✓ task("Write to /research/findings.md", "researcher")
```

### 3. Verify Before Consume

```python
system_prompt = """
Before starting a consumer task:
1. ls("/") to verify producer file exists
2. read_file(path, limit=10) to verify format
3. Only then start consumer
"""
```

## Related Tutorials

- [Context Quarantine](06_context_quarantine.md)
- [Parallel Subagents](11_parallel_subagents.md)
- [Architecting Sub-Agent Hierarchies](02_architecting_subagent_hierarchies.md)
