# The Skills System: Progressive Capability Disclosure

> Loading specialized capabilities on-demand via SKILL.md files

## Overview

Skills provide **progressive disclosure** - the agent sees skill descriptions but only loads full instructions when needed. This prevents context bloat while maintaining access to specialized capabilities.

## How Skills Work

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PROGRESSIVE DISCLOSURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SYSTEM PROMPT (always visible):                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Available Skills:                                                    │   │
│  │ - web-research: Structured approach to web research                 │   │
│  │   → Read /skills/user/web-research/SKILL.md for instructions       │   │
│  │ - code-review: Thorough code review methodology                     │   │
│  │   → Read /skills/user/code-review/SKILL.md for instructions        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  SKILL CONTENT (loaded on demand):                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Agent calls: read_file("/skills/user/web-research/SKILL.md")        │   │
│  │                                                                      │   │
│  │ Returns:                                                             │   │
│  │ # Web Research Skill                                                 │   │
│  │ ## When to Use                                                       │   │
│  │ - User asks for research on a topic                                  │   │
│  │ ## Steps                                                             │   │
│  │ 1. Define research questions                                         │   │
│  │ 2. Search for sources...                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Skill File Structure

```
/skills/
├── user/                          # User-level skills
│   ├── web-research/
│   │   ├── SKILL.md              # Required: Skill definition
│   │   └── search_helper.py      # Optional: Supporting files
│   └── code-review/
│       └── SKILL.md
└── project/                       # Project-level skills
    └── deploy/
        ├── SKILL.md
        └── deploy.sh
```

## SKILL.md Format

```markdown
---
name: web-research
description: Structured approach to conducting thorough web research
license: MIT
compatibility: Requires web_search tool
allowed-tools: web_search read_file write_file
---

# Web Research Skill

## When to Use
- User asks you to research a topic
- Need to gather information from multiple sources
- Creating a knowledge synthesis

## Steps

### 1. Define Research Questions
Before searching, identify 3-5 specific questions to answer.
Write questions to /research/questions.md

### 2. Search Strategy
Use targeted searches:
- `"exact phrase"` for specific terms
- `site:example.com` for specific sources
- `filetype:pdf` for academic papers

### 3. Source Evaluation
For each source, assess:
- Authority: Who wrote this?
- Currency: When was it published?
- Relevance: Does it answer our questions?

### 4. Synthesis
Combine findings into /research/synthesis.md with:
- Key findings
- Conflicting information
- Gaps in knowledge
- Citations

## Example

User: "Research the latest in quantum computing"

1. Questions:
   - What are recent breakthroughs?
   - What are current limitations?
   - What are practical applications?

2. Searches:
   - "quantum computing breakthroughs 2024"
   - "quantum supremacy applications"
   - site:arxiv.org quantum computing

3. Output:
   /research/quantum_computing_synthesis.md
```

## Configuring Skills

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    skills=[
        "/skills/user/",      # User skills (base)
        "/skills/project/",   # Project skills (higher priority)
    ],
    system_prompt="You are a research assistant."
)
```

### Source Priority

Later sources override earlier ones if skills have the same name:

```python
skills=[
    "/skills/base/",      # Base skills
    "/skills/user/",      # User customizations (override base)
    "/skills/project/",   # Project-specific (highest priority)
]
```

## Creating Custom Skills

### Step 1: Create Directory Structure

```bash
mkdir -p /skills/user/my-skill
```

### Step 2: Create SKILL.md

```markdown
---
name: my-skill
description: Brief description for progressive disclosure
---

# My Skill

## When to Use
[Conditions for using this skill]

## Steps
[Detailed instructions]

## Examples
[Usage examples]
```

### Step 3: Configure Agent

```python
agent = create_deep_agent(
    skills=["/skills/user/"],
)
```

## Skill Metadata Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Identifier (max 64 chars, lowercase alphanumeric + hyphens) |
| `description` | Yes | What the skill does (max 1024 chars) |
| `license` | No | License name or reference |
| `compatibility` | No | Environment requirements |
| `allowed-tools` | No | Tools the skill is pre-approved to use |
| `metadata` | No | Arbitrary key-value pairs |

## How Agents Use Skills

### System Prompt Injection

The agent sees:

```
## Skills System

You have access to a skills library that provides specialized capabilities.

**User Skills**: `/skills/user/` (higher priority)

**Available Skills:**
- **web-research**: Structured approach to conducting thorough web research
  -> Read `/skills/user/web-research/SKILL.md` for full instructions
- **code-review**: Thorough code review methodology
  -> Read `/skills/user/code-review/SKILL.md` for full instructions

**How to Use Skills (Progressive Disclosure):**
1. Recognize when a skill applies
2. Read the skill's full instructions
3. Follow the skill's instructions
4. Access supporting files if needed
```

### Agent Workflow

```
User: "Can you research quantum computing?"

Agent thinking:
1. "This is a research task"
2. "I have a web-research skill available"
3. "Let me read the full instructions"

Agent action:
read_file("/skills/user/web-research/SKILL.md")

Agent continues:
[Follows the skill's detailed instructions]
```

## Skills vs. Subagents

| Aspect | Skills | Subagents |
|--------|--------|-----------|
| **Context** | Same context as main agent | Isolated context |
| **Execution** | Main agent follows instructions | Separate agent executes |
| **Best for** | Workflows, methodologies | Heavy lifting, parallelization |
| **Loading** | On-demand (progressive) | Pre-compiled at creation |

### Combined Usage

```python
subagents = [
    {
        "name": "researcher",
        "description": "Conducts research following skill-based methodologies",
        "system_prompt": """You are a research specialist.
        You have access to skills in /skills/.
        Read relevant skill files for methodologies.""",
        "tools": [web_search],
    }
]

agent = create_deep_agent(
    skills=["/skills/user/"],
    subagents=subagents,
)
```

## Example Skills

### Web Research Skill

```markdown
---
name: web-research
description: Structured web research methodology
---

# Web Research Skill

## Process
1. Define questions → /research/questions.md
2. Execute searches
3. Evaluate sources
4. Synthesize → /research/synthesis.md
```

### Code Review Skill

```markdown
---
name: code-review
description: Thorough code review checklist
---

# Code Review Skill

## Checklist
- [ ] Logic correctness
- [ ] Error handling
- [ ] Security vulnerabilities
- [ ] Performance concerns
- [ ] Code style
- [ ] Documentation
```

### Data Analysis Skill

```markdown
---
name: data-analysis
description: Data analysis workflow
---

# Data Analysis Skill

## Steps
1. Load and inspect data
2. Clean and preprocess
3. Exploratory analysis
4. Statistical tests
5. Visualization
6. Report findings
```

## Best Practices

### 1. Clear Descriptions

```markdown
# ❌ BAD
description: Does stuff with code

# ✓ GOOD
description: Performs thorough code review with security, performance, and style checks
```

### 2. Actionable Steps

```markdown
# ❌ BAD
## Steps
- Do research
- Write report

# ✓ GOOD
## Steps
1. Define 3-5 specific research questions
2. Execute targeted searches using [techniques]
3. Evaluate each source for authority and relevance
4. Write synthesis to /research/synthesis.md with citations
```

### 3. Include Examples

```markdown
## Example

User: "Research climate change solutions"

Output:
```
/research/
├── questions.md
├── sources.md
└── synthesis.md
```
```

## Related Tutorials

- [Middleware Composition](07_middleware_composition.md)
- [Managing Massive Contexts](03_managing_massive_contexts.md)
- [Memory System](05_long_term_memory.md)
