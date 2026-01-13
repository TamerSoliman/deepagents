# Managing Massive Contexts: Preventing Context Overflow

> Strategies for handling large data without exhausting the context window

## The Problem: Context Window Limits

Every LLM has a maximum context window. When you exceed it:
- Old messages get truncated
- Important context is lost
- Agent behavior becomes erratic

```
Context Window: 200k tokens
─────────────────────────────────────────
│ System prompt          │  5k tokens   │
│ Conversation history   │ 150k tokens  │ ← Growing!
│ Tool results           │  50k tokens  │ ← Large results!
│                        │              │
│ ❌ OVERFLOW - oldest messages dropped │
─────────────────────────────────────────
```

## Solution 1: Filesystem as External Memory

Instead of keeping everything in conversation, write to files:

```python
# ❌ BAD: Keeping large results in context
tool_result = web_search("quantum computing")  # Returns 50k tokens
# This bloats the conversation history

# ✓ GOOD: Write to filesystem
"""
Agent workflow:
1. Search for information
2. Write results to /research/quantum_computing.md
3. Conversation only contains "Wrote findings to /research/quantum_computing.md"
4. Read specific sections when needed
"""
```

### The FilesystemMiddleware Pattern

The FilesystemMiddleware provides this automatically:

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt="""When handling large data:
    1. Write intermediate results to /working/ directory
    2. Only keep summaries in conversation
    3. Read specific sections when needed

    Example:
    - After research: write_file("/working/research.md", full_content)
    - In conversation: "Research complete. See /working/research.md"
    - When needed: read_file("/working/research.md", offset=0, limit=100)
    """
)
```

## Solution 2: Automatic Large Result Eviction

FilesystemMiddleware automatically handles large tool results:

```python
# When a tool returns >20k tokens:
# 1. Content written to /large_tool_results/{tool_call_id}
# 2. Conversation receives truncated preview
# 3. Agent can read full content via read_file()

# This happens automatically - no configuration needed
```

**What the agent sees:**
```
Tool result too large. Saved to: /large_tool_results/abc123
You can read with read_file("/large_tool_results/abc123", offset=0, limit=100)

First 10 lines:
     1  [preview of content]
     2  [preview of content]
    ...
```

## Solution 3: Read Pagination

Never read entire large files. Use pagination:

```python
# ❌ BAD: Reading entire file
read_file("/large_file.md")  # 10,000 lines → context overflow

# ✓ GOOD: Paginated reading
# First, scan the structure
read_file("/large_file.md", offset=0, limit=100)

# Then, read specific sections
read_file("/large_file.md", offset=500, limit=200)  # Lines 500-700
read_file("/large_file.md", offset=2000, limit=100)  # Lines 2000-2100
```

### System Prompt for Pagination

```python
agent = create_deep_agent(
    system_prompt="""## File Reading Best Practices

    For large files (>500 lines):
    1. First scan: read_file(path, limit=100) to see structure
    2. Targeted read: read_file(path, offset=X, limit=200) for specific sections
    3. Full read: ONLY when editing and you need exact content

    Pattern:
    - Explore structure first
    - Identify relevant sections
    - Read only what you need
    """
)
```

## Solution 4: Automatic Summarization

The SummarizationMiddleware compresses old conversations:

```python
# Configured in create_deep_agent() by default

# When context reaches 85% of max:
# 1. Old messages (except recent 6) get summarized
# 2. Summary replaces original messages
# 3. Recent context preserved

# Configuration (automatic based on model):
trigger = ("fraction", 0.85)  # Summarize at 85% capacity
keep = ("messages", 6)        # Keep last 6 messages intact
```

### How Summarization Works

```
BEFORE SUMMARIZATION:
─────────────────────────────────────────
│ Message 1: User asks about X          │
│ Message 2: Agent responds             │
│ Message 3: Tool call result           │
│ Message 4: Agent processes            │
│ ... (100 more messages) ...           │
│ Message 105: Recent user message      │
│ Message 106: Recent agent response    │
─────────────────────────────────────────

AFTER SUMMARIZATION:
─────────────────────────────────────────
│ Summary: "Previous conversation       │
│ covered X, Y, Z. Key findings: ..."   │
│ Message 105: Recent user message      │
│ Message 106: Recent agent response    │
─────────────────────────────────────────
```

## Solution 5: Subagent Context Isolation

Use subagents to isolate context-heavy work:

```python
# Main agent has limited context for coordination
# Subagents handle heavy lifting in isolation

agent = create_deep_agent(
    system_prompt="""For context-heavy tasks, delegate to subagents:

    - task("Read and analyze large document", "general-purpose")
    - Subagent works in isolated context
    - Only summary returns to you

    This prevents your context from being consumed by
    intermediate steps.
    """
)
```

### Context Quarantine in Action

```
MAIN AGENT CONTEXT:
─────────────────────────
│ Task: "Analyze docs"   │
│ Result: "Summary..."   │  ← Only summary
─────────────────────────

SUBAGENT CONTEXT (isolated, discarded after):
─────────────────────────
│ Task: "Analyze docs"   │
│ Read doc1.md (500 KB)  │
│ Read doc2.md (300 KB)  │
│ Analysis steps...      │
│ Final: "Summary..."    │  → Returns to main
─────────────────────────
```

## Solution 6: Strategic File Organization

Organize files for efficient access:

```
/working/                 # Temporary, current task
  ├── notes.md
  └── scratch.md

/research/                # Research findings
  ├── topic_a/
  │   ├── sources.md
  │   └── summary.md      # ← Read this for overview
  └── topic_b/
      └── ...

/output/                  # Final deliverables
  └── report.md

/archive/                 # Completed work (rarely accessed)
  └── ...
```

**Access Pattern:**
1. Check `/research/{topic}/summary.md` first
2. Only dive into details if needed
3. Keep `/working/` small and focused

## Code Example: Large Document Analysis

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt="""## Context Management Protocol

    For large documents (>500 lines):
    1. Write full content to /working/full_document.md
    2. Create /working/summary.md with key points
    3. Reference summary in conversation
    4. Read full document sections only when needed

    For research tasks:
    1. Delegate to subagent for heavy lifting
    2. Subagent writes to /research/{topic}.md
    3. You read only the summary sections

    Never keep >1000 lines of content in conversation.
    Use the filesystem as your external memory.
    """
)
```

## Monitoring Context Usage

While deep agents handle this automatically, you can monitor:

```python
# Check message count
result = agent.invoke({"messages": [...]})
message_count = len(result.get("messages", []))

# Check file count
files = result.get("files", {})
total_file_size = sum(
    len("\n".join(f["content"]))
    for f in files.values()
)
```

## Summary: Context Management Checklist

| Strategy | When to Use |
|----------|-------------|
| **Filesystem storage** | Any intermediate data |
| **Auto-eviction** | Large tool results (automatic) |
| **Pagination** | Reading any file >500 lines |
| **Summarization** | Long conversations (automatic) |
| **Subagent isolation** | Context-heavy sub-tasks |
| **Strategic organization** | All file operations |

## Related Tutorials

- [Tool Result Eviction](16_tool_result_eviction.md)
- [File Pagination Patterns](15_file_pagination.md)
- [Summarization Strategies](18_summarization_strategies.md)
- [Context Quarantine](06_context_quarantine.md)
