# Multi-Document Analysis Pattern

> Analyzing and synthesizing information across many documents

## Overview

When working with multiple documents, deep agents need to:
1. Process documents without context overflow
2. Extract relevant information
3. Cross-reference findings
4. Synthesize insights

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-DOCUMENT ANALYSIS ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         DOCUMENT QUEUE                                │   │
│  │  /documents/doc1.pdf, doc2.pdf, doc3.pdf, ..., doc50.pdf            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│                    ┌───────────────────────────────┐                        │
│                    │      ANALYSIS COORDINATOR     │                        │
│                    │  - Distributes documents      │                        │
│                    │  - Collects summaries         │                        │
│                    │  - Cross-references           │                        │
│                    │  - Synthesizes report         │                        │
│                    └───────────────┬───────────────┘                        │
│                                    │                                         │
│            ┌───────────────────────┼───────────────────────┐                │
│            │                       │                       │                │
│            ▼                       ▼                       ▼                │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│   │  DOC ANALYZER 1 │    │  DOC ANALYZER 2 │    │  DOC ANALYZER 3 │        │
│   │  (Context       │    │  (Context       │    │  (Context       │        │
│   │   Quarantined)  │    │   Quarantined)  │    │   Quarantined)  │        │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘        │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         SUMMARY STORAGE                               │   │
│  │  /summaries/doc1_summary.md, doc2_summary.md, ...                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The Challenge: Context Limits

```
50 documents × 20 pages × 500 tokens/page = 500,000 tokens
Context window: 200,000 tokens

❌ Cannot read all documents into context!
✓ Must process incrementally with isolated subagents
```

## Implementation

### Document Analyzer Subagent

```python
subagents = [
    {
        "name": "doc-analyzer",
        "description": "Analyzes a single document and produces structured summary",
        "system_prompt": """You are a document analyzer.

        Your task: Analyze ONE document and produce a structured summary.

        Input: Document path will be provided

        Process:
        1. Read document using pagination (never full read)
           - read_file(path, limit=100) for overview
           - read_file(path, offset=X, limit=100) for sections
        2. Extract key information
        3. Write structured summary

        Output format (/summaries/{doc_name}_summary.md):
        ---
        document: [original path]
        pages: [number]
        date: [if found]
        type: [report/paper/article/etc]
        ---

        # Summary

        ## Key Points
        - [Main point 1]
        - [Main point 2]
        - [Main point 3]

        ## Important Data
        - [Statistic/fact 1]
        - [Statistic/fact 2]

        ## Quotes
        > "[Important quote]" (page X)

        ## Related Topics
        - [Topic 1]
        - [Topic 2]

        ## Questions Raised
        - [Question that needs cross-referencing]
        """,
        "tools": [],
    },
    {
        "name": "synthesizer",
        "description": "Cross-references summaries and creates synthesis report",
        "system_prompt": """You are a synthesis specialist.

        Your task: Create a coherent synthesis from multiple document summaries.

        Process:
        1. Read all summaries from /summaries/
        2. Identify common themes
        3. Find contradictions/agreements
        4. Extract key insights
        5. Write synthesis report

        Output (/output/synthesis.md):
        # Document Synthesis Report

        ## Overview
        [Number of documents, types, date range]

        ## Common Themes
        ### Theme 1
        - Supported by: [doc1, doc3, doc7]
        - Key finding: [...]

        ## Points of Agreement
        [What multiple documents agree on]

        ## Points of Conflict
        [Where documents disagree, with citations]

        ## Key Statistics
        | Metric | Value | Source |
        |--------|-------|--------|

        ## Synthesis
        [Integrated narrative combining all findings]

        ## Knowledge Gaps
        [What the documents don't cover]
        """,
        "tools": [],
    },
]
```

### Analysis Coordinator

```python
agent = create_deep_agent(
    subagents=subagents,
    system_prompt="""You are a multi-document analysis coordinator.

    ## Analysis Protocol

    ### Phase 1: Document Inventory
    1. List all documents in /documents/
    2. Write inventory to /inventory.md

    ### Phase 2: Parallel Analysis
    Process documents in batches of 5:

    Batch 1:
    - task("Analyze /documents/doc1.pdf", "doc-analyzer")
    - task("Analyze /documents/doc2.pdf", "doc-analyzer")
    - task("Analyze /documents/doc3.pdf", "doc-analyzer")
    - task("Analyze /documents/doc4.pdf", "doc-analyzer")
    - task("Analyze /documents/doc5.pdf", "doc-analyzer")
    [Launch all 5 in ONE message for parallel execution]

    Wait for completion, then next batch.

    ### Phase 3: Synthesis
    After all documents analyzed:
    task("Synthesize all summaries in /summaries/", "synthesizer")

    ### Phase 4: Review
    Read synthesis report
    Fill any gaps with targeted re-analysis

    ## File Organization
    /documents/       # Input documents
    /summaries/       # Individual document summaries
    /output/          # Final synthesis
    /inventory.md     # Document listing

    ## Context Management
    - NEVER read full documents into main context
    - Delegate ALL document reading to subagents
    - Only read summaries (much smaller)
    - Subagent context is quarantined and discarded
    """,
)
```

## Processing Strategies

### Strategy 1: Batch Processing

```python
system_prompt = """
## Batch Processing

For large document sets (>10 docs):
1. Process in batches of 5 (parallel)
2. Wait for batch completion
3. Start next batch
4. Track progress in /progress.md

Why batches?
- Manageable parallelism
- Can track progress
- Can handle failures per-batch
"""
```

### Strategy 2: Priority-Based

```python
system_prompt = """
## Priority Processing

1. Quick scan all documents (title, abstract only)
2. Prioritize by relevance
3. Analyze high-priority first
4. Analyze others if time permits

Use when:
- Time constrained
- Looking for specific information
- Documents vary in relevance
"""
```

### Strategy 3: Incremental Synthesis

```python
system_prompt = """
## Incremental Synthesis

After each batch:
1. Run partial synthesis
2. Identify emerging themes
3. Adjust analysis focus for remaining docs

Benefits:
- Early insights
- Adaptive analysis
- Better final synthesis
"""
```

## Handling Large Documents

### Pagination Pattern

```python
doc_analyzer_prompt = """
## Reading Large Documents

NEVER: read_file(path)  # Full read = context overflow

ALWAYS use pagination:
1. read_file(path, limit=50)  # Table of contents, intro
2. Identify sections of interest
3. read_file(path, offset=X, limit=100)  # Each section
4. Skip irrelevant sections

For 1000-line document:
- Read lines 1-50 (structure)
- Read lines 100-200 (intro)
- Read lines 500-600 (key section)
- Skip lines 600-900 (appendix)
- Read lines 900-950 (conclusion)

Total: ~300 lines read instead of 1000
"""
```

### Summary Compression

```python
doc_analyzer_prompt = """
## Summary Size Limits

Each summary must be:
- Max 100 lines
- Focus on extractable facts
- Skip verbose descriptions
- Use bullet points

This ensures coordinator can read all summaries.
"""
```

## Cross-Reference Patterns

### Finding Agreements

```python
synthesizer_prompt = """
## Identifying Agreement

When multiple documents discuss same topic:
1. Note the common claim
2. List supporting documents
3. Note any nuance differences
4. Assign confidence based on source count

Format:
### Claim: [Statement]
- Supported by: doc1 (page 5), doc3 (page 12), doc7 (page 3)
- Confidence: HIGH (3+ sources)
"""
```

### Finding Contradictions

```python
synthesizer_prompt = """
## Identifying Contradictions

When documents disagree:
1. State both positions clearly
2. Note the source of each
3. Analyze possible reasons for difference
4. Flag for user attention

Format:
### Conflict: [Topic]
- Position A: [claim] (doc1, doc4)
- Position B: [claim] (doc2, doc5)
- Possible explanation: [methodology difference, time period, etc.]
"""
```

## Complete Example

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend

def backend_factory(rt):
    return CompositeBackend(
        default=StateBackend(rt),
        routes={
            "/documents/": FilesystemBackend(root_dir="/data/docs"),
            "/output/": FilesystemBackend(root_dir="/data/output"),
        }
    )

analysis_agent = create_deep_agent(
    subagents=subagents,
    backend=backend_factory,
    system_prompt=COORDINATOR_PROMPT,
)

result = analysis_agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Analyze all quarterly reports and identify trends"
    }]
})

# Final synthesis available at /output/synthesis.md
```

## Related Tutorials

- [Managing Massive Contexts](03_managing_massive_contexts.md)
- [Parallel Subagents](11_parallel_subagents.md)
- [Context Quarantine](06_context_quarantine.md)
