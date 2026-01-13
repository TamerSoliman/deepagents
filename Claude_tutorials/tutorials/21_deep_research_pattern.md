# Deep Research Pattern

> Comprehensive research workflow using hierarchical agents

## Overview

Deep research requires systematic information gathering, evaluation, and synthesis. This pattern shows how to coordinate multiple agents for thorough research.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DEEP RESEARCH ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                    ┌─────────────────────────────┐                          │
│                    │     RESEARCH COORDINATOR    │                          │
│                    │                             │                          │
│                    │  - Defines research plan    │                          │
│                    │  - Assigns to specialists   │                          │
│                    │  - Synthesizes findings     │                          │
│                    └──────────────┬──────────────┘                          │
│                                   │                                          │
│            ┌──────────────────────┼──────────────────────┐                  │
│            │                      │                      │                  │
│            ▼                      ▼                      ▼                  │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐          │
│   │    SEARCHER     │   │    ANALYST      │   │    WRITER       │          │
│   │                 │   │                 │   │                 │          │
│   │ - Web search    │   │ - Data analysis │   │ - Report writing│          │
│   │ - Source finding│   │ - Fact checking │   │ - Synthesis     │          │
│   │ - Document read │   │ - Comparison    │   │ - Citation      │          │
│   └─────────────────┘   └─────────────────┘   └─────────────────┘          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Implementation

### Specialized Subagents

```python
from deepagents import create_deep_agent

subagents = [
    {
        "name": "searcher",
        "description": "Searches the web for information on specific topics",
        "system_prompt": """You are a research searcher.

        Your job:
        1. Execute targeted web searches
        2. Find authoritative sources
        3. Extract relevant information
        4. Document sources with URLs

        Output: Write findings to /research/{topic}/sources.md

        Format:
        ## Source: [Title]
        URL: [url]
        Key Points:
        - [point 1]
        - [point 2]
        Relevance: [why this matters]
        """,
        "tools": [web_search_tool],
    },
    {
        "name": "analyst",
        "description": "Analyzes and fact-checks research findings",
        "system_prompt": """You are a research analyst.

        Your job:
        1. Read findings from /research/
        2. Cross-reference claims
        3. Identify contradictions
        4. Evaluate source quality
        5. Extract key insights

        Output: Write analysis to /analysis/{topic}.md

        Include:
        - Verified facts
        - Conflicting information
        - Source reliability assessment
        - Knowledge gaps
        """,
        "tools": [],  # Uses filesystem tools
    },
    {
        "name": "writer",
        "description": "Writes polished research reports",
        "system_prompt": """You are a research writer.

        Your job:
        1. Read from /research/ and /analysis/
        2. Synthesize into coherent narrative
        3. Organize by themes
        4. Include proper citations
        5. Highlight key findings

        Output: Write to /output/report.md

        Structure:
        1. Executive Summary
        2. Key Findings
        3. Detailed Analysis
        4. Conclusions
        5. References
        """,
        "tools": [],
    },
]
```

### Research Coordinator

```python
agent = create_deep_agent(
    subagents=subagents,
    system_prompt="""You are a research coordinator.

    ## Research Protocol

    ### Phase 1: Planning
    1. Analyze the research question
    2. Break into 3-5 specific sub-questions
    3. Write plan to /research/plan.md

    ### Phase 2: Information Gathering (PARALLEL)
    For each sub-question:
    - task("Search for [specific topic]", "searcher")

    Launch all searcher tasks in ONE message for parallel execution.

    ### Phase 3: Analysis
    After all searchers complete:
    - task("Analyze findings in /research/", "analyst")

    ### Phase 4: Synthesis
    After analysis:
    - task("Write report from /research/ and /analysis/", "writer")

    ### Phase 5: Review
    - Read /output/report.md
    - Check for completeness
    - Fill any gaps
    - Deliver to user

    ## File Organization
    /research/
      ├── plan.md
      ├── topic_1/sources.md
      ├── topic_2/sources.md
      └── ...
    /analysis/
      └── findings.md
    /output/
      └── report.md
    """,
)
```

## Research Workflow

### Step-by-Step Execution

```
User: "Research the impact of AI on healthcare"

COORDINATOR:

1. Planning Phase
   write_file("/research/plan.md", """
   # Research Plan: AI in Healthcare

   ## Questions
   1. What are current AI applications in healthcare?
   2. What are the clinical outcomes?
   3. What are adoption barriers?
   4. What are ethical considerations?
   5. What are future trends?
   """)

2. Search Phase (PARALLEL)
   task("Search for current AI applications in healthcare: diagnosis, treatment, admin", "searcher")
   task("Search for clinical outcomes and efficacy studies of AI healthcare tools", "searcher")
   task("Search for barriers to AI adoption in healthcare: cost, regulation, training", "searcher")
   task("Search for ethical considerations: bias, privacy, accountability", "searcher")
   task("Search for future trends in AI healthcare: predictions, emerging tech", "searcher")

   [All 5 tasks run concurrently]

3. Analysis Phase
   task("Analyze all findings in /research/, cross-reference claims, identify themes", "analyst")

4. Writing Phase
   task("Write comprehensive report synthesizing /research/ and /analysis/", "writer")

5. Review Phase
   read_file("/output/report.md")
   [Check completeness, fill gaps if needed]
   Present to user
```

## Advanced Patterns

### Iterative Deepening

```python
system_prompt = """
## Iterative Research

Round 1: Broad search
- General overview of the topic
- Identify key themes

Round 2: Deep dive (based on Round 1 findings)
- Focus on most important themes
- Search for specific details

Round 3: Gap filling
- Identify missing information
- Targeted searches to fill gaps

Each round builds on previous findings.
"""
```

### Source Prioritization

```python
searcher_prompt = """
## Source Priority

1. Academic papers (highest credibility)
   - Search site:arxiv.org, site:scholar.google.com
2. Government/institutional reports
   - Search site:gov, site:edu, site:who.int
3. Industry reports
   - Search site:mckinsey.com, site:gartner.com
4. Quality journalism
   - Search site:nature.com, site:nytimes.com
5. General web (verify carefully)

Always document source type and reliability.
"""
```

### Fact Verification

```python
analyst_prompt = """
## Verification Protocol

For each claim:
1. Find corroborating source
2. Check for contradicting evidence
3. Assess source independence
4. Rate confidence: HIGH/MEDIUM/LOW

Flag claims that:
- Only appear in one source
- Come from potentially biased sources
- Contradict other findings
"""
```

## Output Quality

### Report Structure

```markdown
# Research Report: [Topic]

## Executive Summary
[2-3 paragraph overview]

## Key Findings
- Finding 1 (confidence: HIGH)
- Finding 2 (confidence: HIGH)
- Finding 3 (confidence: MEDIUM)

## Detailed Analysis

### Theme 1
[Analysis with citations]

### Theme 2
[Analysis with citations]

## Methodology
[How research was conducted]

## Limitations
[What wasn't covered, confidence gaps]

## References
1. [Source 1] - URL
2. [Source 2] - URL
```

### Citation Format

```python
writer_prompt = """
## Citation Requirements

In-text: "According to [Source Name]..."
or "Research shows [claim] ([Source Name], [Year])"

Reference section:
- [Author/Org]. [Title]. [URL]. Accessed [Date].

Every factual claim needs a citation.
"""
```

## Complete Example

```python
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

# Create research agent with checkpointing
checkpointer = MemorySaver()

research_agent = create_deep_agent(
    subagents=subagents,  # searcher, analyst, writer
    checkpointer=checkpointer,
    interrupt_on={"task": False},  # Don't interrupt subagent calls
    system_prompt=COORDINATOR_PROMPT,
)

# Execute research
result = research_agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Research the environmental impact of cryptocurrency mining"
    }]
}, config={"configurable": {"thread_id": "crypto-research"}})

# Access final report
report = result["files"].get("/output/report.md")
```

## Related Tutorials

- [Architecting Sub-Agent Hierarchies](02_architecting_subagent_hierarchies.md)
- [Parallel Subagents](11_parallel_subagents.md)
- [Managing Massive Contexts](03_managing_massive_contexts.md)
