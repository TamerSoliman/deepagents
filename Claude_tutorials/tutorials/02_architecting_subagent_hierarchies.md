# Architecting Sub-Agent Hierarchies

> Distributing scope across specialized agents with orchestrated control flow

## Overview

Complex tasks benefit from **division of labor**. Instead of one agent doing everything, you create a hierarchy where a **main orchestrator** coordinates **specialized subagents** that handle specific domains.

## The Hierarchical Model

```
                    ┌─────────────────────────┐
                    │     ORCHESTRATOR        │
                    │  (Coordinates, decides, │
                    │   synthesizes)          │
                    └───────────┬─────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            │                   │                   │
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │  RESEARCHER   │   │    WRITER     │   │   ANALYST     │
    │  - web_search │   │  - edit_file  │   │  - execute    │
    │  - read_file  │   │  - write_file │   │  - read_file  │
    └───────────────┘   └───────────────┘   └───────────────┘
```

## Defining Specialized Subagents

```python
from deepagents import create_deep_agent

# Define specialized subagents
subagents = [
    {
        "name": "researcher",
        "description": "Conducts thorough web research, finds papers, analyzes sources",
        "system_prompt": """You are a research specialist.

        Your job is to:
        1. Search for information using web_search
        2. Read and analyze documents
        3. Synthesize findings into clear summaries

        Always cite your sources with URLs.
        Write findings to /research/findings.md for the orchestrator.""",
        "tools": [web_search_tool],
    },
    {
        "name": "writer",
        "description": "Creates polished written content from research materials",
        "system_prompt": """You are a professional writer.

        Your job is to:
        1. Read research from /research/*.md
        2. Create well-structured documents
        3. Write output to /output/*.md

        Focus on clarity, structure, and readability.""",
        "tools": [],  # Uses default filesystem tools
    },
    {
        "name": "analyst",
        "description": "Performs data analysis, runs computations, generates insights",
        "system_prompt": """You are a data analyst.

        Your job is to:
        1. Read data from /data/*.json or /data/*.csv
        2. Perform analysis using Python
        3. Generate insights and visualizations
        4. Write results to /analysis/results.md""",
        "tools": [python_repl_tool],
    },
]

# Create orchestrator with subagents
orchestrator = create_deep_agent(
    system_prompt="""You are a project coordinator.

    Coordinate the following specialists via the task() tool:
    - researcher: For gathering information
    - writer: For creating documents
    - analyst: For data analysis

    Your role is to:
    1. Break down user requests into sub-tasks
    2. Delegate to appropriate specialists
    3. Synthesize results into final deliverables

    Parallelize independent tasks for efficiency.""",
    subagents=subagents,
)
```

## Communication Patterns

### Pattern 1: Sequential Pipeline

Task flows from one agent to the next:

```
ORCHESTRATOR
    │
    ▼
RESEARCHER: "Research topic X"
    │ writes /research/findings.md
    │
    ▼
ORCHESTRATOR: reads findings, decides next step
    │
    ▼
WRITER: "Write report based on /research/findings.md"
    │ writes /output/report.md
    │
    ▼
ORCHESTRATOR: delivers final report
```

**Code:**
```python
# Orchestrator's workflow
result = agent.invoke({
    "messages": [{"role": "user", "content": "Research and write about quantum computing"}]
})

# The orchestrator will:
# 1. task("Research quantum computing advances", "researcher")
# 2. Wait for researcher to complete
# 3. task("Write report from /research/findings.md", "writer")
# 4. Synthesize and present results
```

### Pattern 2: Parallel Execution

Independent tasks run simultaneously:

```
ORCHESTRATOR
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  ▼
RESEARCHER         RESEARCHER         RESEARCHER
"Research A"       "Research B"       "Research C"
    │                  │                  │
    └──────────────────┴──────────────────┘
                       │
                       ▼
                 ORCHESTRATOR
              (synthesizes all)
```

**Code:**
```python
# Orchestrator makes PARALLEL task calls in ONE message
# (LangGraph handles concurrent execution)

# The model will output:
# Tool Call 1: task("Research topic A", "researcher")
# Tool Call 2: task("Research topic B", "researcher")
# Tool Call 3: task("Research topic C", "researcher")

# All three execute concurrently, results collected together
```

### Pattern 3: File-Based Handoff

Agents communicate via shared filesystem:

```
RESEARCHER                          WRITER
    │                                  │
    │ writes /shared/data.json         │
    │───────────────────────────────────│
    │                                  │
    │                    reads /shared/data.json
    │                                  │
    │                    writes /output/report.md
```

**Best Practice:** Use structured file paths:
```
/research/         # Researcher output
/analysis/         # Analyst output
/drafts/           # Writer drafts
/output/           # Final deliverables
/shared/           # Cross-agent data
```

## Context Quarantine in Action

When orchestrator calls `task("Do X", "researcher")`:

**What researcher RECEIVES:**
```
messages: [HumanMessage("Do X")]  ← Fresh, only the task
files: {"/research/...": ...}     ← Shared filesystem
```

**What researcher does NOT receive:**
```
❌ Orchestrator's conversation history
❌ Orchestrator's todo list
❌ Other agents' conversations
```

**What returns to orchestrator:**
```
ToolMessage("Research complete. Key findings: ...")
files: {"/research/findings.md": ...}  ← Any new files
```

## Specialized Tool Assignment

Each subagent should have **minimal, focused tools**:

```python
# ❌ BAD: Subagent with too many tools
{
    "name": "researcher",
    "tools": [web_search, email, calendar, code_execution, ...],  # Unfocused
}

# ✓ GOOD: Focused tool set
{
    "name": "researcher",
    "tools": [web_search, pdf_reader],  # Research-specific
}

# The general-purpose agent (always available) handles edge cases
```

## Orchestration Strategies

### Strategy 1: Task-Based Decomposition

Break work into independent tasks:

```python
system_prompt = """
When you receive a complex request:
1. Identify 3-5 independent sub-tasks
2. Assign each to the most appropriate specialist
3. Parallelize where possible
4. Synthesize results

Example breakdown:
"Write a market analysis report"
→ task("Research market trends", "researcher")
→ task("Research competitor analysis", "researcher")  # Parallel
→ task("Analyze market data", "analyst")
→ task("Write report from findings", "writer")  # Sequential, after research
"""
```

### Strategy 2: Iterative Refinement

Multiple passes for quality:

```python
system_prompt = """
For high-quality outputs:
1. First pass: Get initial content
2. Review and identify gaps
3. Second pass: Fill gaps
4. Final review and polish

Example:
→ task("Write initial draft", "writer")
→ Review draft, identify missing sections
→ task("Research missing topic X", "researcher")
→ task("Revise draft with new info", "writer")
"""
```

### Strategy 3: Expert Consultation

Pull in specialists as needed:

```python
system_prompt = """
When you encounter specialized needs:
1. Identify the domain
2. Delegate to appropriate expert
3. Integrate their response

Don't try to do everything yourself.
Specialists produce better results in their domains.
"""
```

## Error Handling

Subagents can fail. Handle gracefully:

```python
system_prompt = """
If a subagent returns an error or incomplete result:
1. Analyze what went wrong
2. Provide more specific instructions
3. Retry with adjusted parameters
4. If still failing, try a different approach

Never just pass errors to the user without attempting recovery.
"""
```

## Monitoring Subagent Work

Since subagent conversations are hidden, use files for transparency:

```python
# Subagent system prompt
system_prompt = """
Always write your progress to /status/{task_name}.md:
- What you're doing
- What you've found
- Any blockers

This helps the orchestrator understand your work.
"""
```

## Complete Example: Research Project

```python
from deepagents import create_deep_agent

subagents = [
    {
        "name": "researcher",
        "description": "Searches and analyzes academic sources",
        "system_prompt": """You are an academic researcher.

        For each research task:
        1. Search for peer-reviewed sources
        2. Read and summarize key papers
        3. Write findings to /research/{topic}.md
        4. Include citations and source URLs

        Be thorough but focused on the specific question.""",
        "tools": [web_search, pdf_reader],
    },
    {
        "name": "writer",
        "description": "Creates publication-quality documents",
        "system_prompt": """You are a technical writer.

        For each writing task:
        1. Read source materials from /research/
        2. Create well-structured document
        3. Write to /output/{document}.md
        4. Include proper citations

        Focus on clarity and academic tone.""",
        "tools": [],
    },
]

agent = create_deep_agent(
    system_prompt="""You coordinate research projects.

    For research requests:
    1. Break into research questions
    2. Delegate research tasks (parallelize independent questions)
    3. Wait for all research to complete
    4. Delegate writing with all research as input
    5. Review and deliver final document

    Use /research/ for intermediate work, /output/ for deliverables.""",
    subagents=subagents,
)
```

## Related Tutorials

- [Context Quarantine Deep Dive](06_context_quarantine.md)
- [Parallel Subagents](11_parallel_subagents.md)
- [Hierarchical Communication](17_hierarchical_communication.md)
- [The Planning Loop Pattern](01_planning_loop_pattern.md)
