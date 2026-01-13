# Architectural Reference Table

> Mapping use cases to deepagents configurations

## Quick Reference: Use Case → Configuration

| Use Case | Middleware | Backend | Subagents | Key Tools | Notes |
|----------|------------|---------|-----------|-----------|-------|
| **Deep Research** | Memory, Skills | Composite (State + Store) | researcher, analyst, writer | web_search, read_file | Parallel research, sequential synthesis |
| **Code Refactoring** | HITL | Filesystem | analyzer, refactorer, validator | edit_file, execute | Human approval for changes |
| **Multi-Document Analysis** | Summarization | Composite | doc-analyzer, synthesizer | read_file (paginated) | Batch processing with context quarantine |
| **Customer Support** | Memory | Store | knowledge-base, ticket-handler | read_file, edit_file | Persistent preferences |
| **Content Creation** | Skills | State | researcher, writer, editor | write_file | Pipeline: research → draft → edit |
| **Data Pipeline** | Custom logging | Filesystem | extractor, transformer, loader | execute | ETL with validation |
| **Code Review** | HITL | Filesystem | security-checker, style-checker | read_file, grep | Parallel checks, manual approval |
| **Personal Assistant** | Memory | Store | scheduler, researcher, writer | Various | Cross-session memory |
| **DevOps Automation** | HITL | Filesystem (sandboxed) | monitor, deployer, rollback | execute | Human approval for deployments |
| **Report Generation** | Skills, Memory | Composite | data-gatherer, analyst, writer | read_file, write_file | Template-based with skills |

## Detailed Configuration Guide

### 1. Deep Research Project

```python
subagents = [
    {"name": "researcher", "description": "Web research", "tools": [web_search]},
    {"name": "analyst", "description": "Data analysis", "tools": [execute]},
    {"name": "writer", "description": "Report writing", "tools": []},
]

agent = create_deep_agent(
    subagents=subagents,
    backend=lambda rt: CompositeBackend(
        default=StateBackend(rt),
        routes={"/memories/": StoreBackend(rt)}
    ),
    store=persistent_store,
    memory=["/memories/preferences.md"],
    system_prompt="Coordinate research using specialists..."
)
```

**Key Patterns:**
- Parallel research subagents
- Sequential synthesis
- Persistent memory for learned preferences

---

### 2. Code Refactoring

```python
subagents = [
    {"name": "analyzer", "description": "Find code smells", "tools": []},
    {"name": "refactorer", "description": "Apply changes", "tools": []},
    {"name": "validator", "description": "Run tests", "tools": [execute]},
]

agent = create_deep_agent(
    subagents=subagents,
    backend=FilesystemBackend(root_dir="/project"),
    checkpointer=MemorySaver(),
    interrupt_on={"edit_file": True},
    system_prompt="Safely refactor code with validation..."
)
```

**Key Patterns:**
- Human approval for edits
- Validation after each change
- Real filesystem access

---

### 3. Multi-Document Analysis

```python
subagents = [
    {"name": "doc-analyzer", "description": "Analyze single document", "tools": []},
    {"name": "synthesizer", "description": "Cross-reference and synthesize", "tools": []},
]

agent = create_deep_agent(
    subagents=subagents,
    backend=lambda rt: CompositeBackend(
        default=StateBackend(rt),
        routes={"/documents/": FilesystemBackend(root_dir="/data/docs")}
    ),
    system_prompt="Process documents in batches, synthesize findings..."
)
```

**Key Patterns:**
- Batch parallel processing
- Context quarantine per document
- Pagination for large documents

---

### 4. Customer Support Bot

```python
agent = create_deep_agent(
    backend=lambda rt: StoreBackend(rt),
    store=persistent_store,
    memory=["/memories/user/preferences.md"],
    system_prompt="""Remember user preferences.
    Update memory when user shares lasting information.
    Reference past interactions."""
)
```

**Key Patterns:**
- Persistent memory across sessions
- Preference learning
- Cross-conversation context

---

### 5. Content Creation Pipeline

```python
subagents = [
    {"name": "researcher", "description": "Gather information", "tools": [web_search]},
    {"name": "writer", "description": "Create drafts", "tools": []},
    {"name": "editor", "description": "Polish content", "tools": []},
]

agent = create_deep_agent(
    subagents=subagents,
    skills=["/skills/writing/"],
    system_prompt="Follow writing skills for structured content creation..."
)
```

**Key Patterns:**
- Sequential pipeline
- Skill-guided workflows
- Multiple revision passes

---

### 6. Data Pipeline

```python
subagents = [
    {"name": "extractor", "description": "Extract data from sources", "tools": [execute]},
    {"name": "transformer", "description": "Clean and transform data", "tools": [execute]},
    {"name": "loader", "description": "Load to destination", "tools": [execute]},
]

agent = create_deep_agent(
    subagents=subagents,
    backend=FilesystemBackend(root_dir="/data"),
    checkpointer=MemorySaver(),
    system_prompt="ETL pipeline with validation at each step..."
)
```

**Key Patterns:**
- Stage-based processing
- Checkpoint for recovery
- File-based data handoff

---

### 7. Code Review System

```python
subagents = [
    {"name": "security-checker", "description": "Security vulnerabilities", "tools": []},
    {"name": "style-checker", "description": "Code style and conventions", "tools": []},
    {"name": "performance-checker", "description": "Performance issues", "tools": []},
]

agent = create_deep_agent(
    subagents=subagents,
    backend=FilesystemBackend(root_dir="/project"),
    system_prompt="Parallel code review, then consolidate findings..."
)
```

**Key Patterns:**
- Parallel specialized checks
- Consolidated report
- No file modifications

---

### 8. Personal Assistant

```python
agent = create_deep_agent(
    subagents=[
        {"name": "scheduler", "description": "Calendar management", "tools": [calendar_api]},
        {"name": "researcher", "description": "Information lookup", "tools": [web_search]},
    ],
    backend=lambda rt: CompositeBackend(
        default=StateBackend(rt),
        routes={"/memories/": StoreBackend(rt)}
    ),
    store=persistent_store,
    memory=["/memories/user/profile.md", "/memories/user/preferences.md"],
    system_prompt="Personal assistant with persistent memory..."
)
```

**Key Patterns:**
- Multi-capability delegation
- Persistent user profile
- Learning from interactions

---

### 9. DevOps Automation

```python
subagents = [
    {"name": "monitor", "description": "Check system health", "tools": [execute]},
    {"name": "deployer", "description": "Deploy changes", "tools": [execute]},
    {"name": "rollback", "description": "Revert changes", "tools": [execute]},
]

agent = create_deep_agent(
    subagents=subagents,
    backend=FilesystemBackend(root_dir="/deployment"),
    checkpointer=MemorySaver(),
    interrupt_on={"execute": True},  # Human approval for all commands
    system_prompt="Safe deployment with human approval..."
)
```

**Key Patterns:**
- Human-in-the-loop for safety
- Rollback capability
- Checkpointed state

---

### 10. Report Generation

```python
agent = create_deep_agent(
    subagents=[
        {"name": "data-gatherer", "description": "Collect data", "tools": [db_query]},
        {"name": "analyst", "description": "Analyze data", "tools": [execute]},
        {"name": "writer", "description": "Generate report", "tools": []},
    ],
    skills=["/skills/reporting/"],
    backend=lambda rt: CompositeBackend(
        default=StateBackend(rt),
        routes={"/templates/": FilesystemBackend(root_dir="/templates")}
    ),
    system_prompt="Template-based report generation..."
)
```

**Key Patterns:**
- Template-driven output
- Data → Analysis → Report pipeline
- Skill-guided formatting

---

## Component Selection Matrix

### When to Use Each Backend

| Scenario | StateBackend | StoreBackend | FilesystemBackend | CompositeBackend |
|----------|:------------:|:------------:|:-----------------:|:----------------:|
| Quick prototype | ✓ | | | |
| Persistent memory | | ✓ | | |
| Real file editing | | | ✓ | |
| Mixed requirements | | | | ✓ |
| Cross-thread sharing | | ✓ | | |
| Command execution | | | ✓ | |

### When to Use Subagents

| Scenario | Use Subagents? | Pattern |
|----------|:--------------:|---------|
| Simple task | No | Direct execution |
| Multi-step research | Yes | Researcher subagent |
| Heavy computation | Yes | Context quarantine |
| Parallel work | Yes | Multiple parallel subagents |
| Sensitive operations | Maybe | With HITL |

### When to Use HITL

| Scenario | HITL Recommended | Tools to Interrupt |
|----------|:----------------:|-------------------|
| Production code changes | Yes | edit_file, write_file |
| System commands | Yes | execute |
| API calls with side effects | Yes | custom tools |
| Read-only research | No | - |
| Sandbox environment | Optional | - |

## Source Code Quick Reference

| Component | Location |
|-----------|----------|
| create_deep_agent | `libs/deepagents/deepagents/graph.py` |
| FilesystemMiddleware | `libs/deepagents/deepagents/middleware/filesystem.py` |
| SubAgentMiddleware | `libs/deepagents/deepagents/middleware/subagents.py` |
| MemoryMiddleware | `libs/deepagents/deepagents/middleware/memory.py` |
| SkillsMiddleware | `libs/deepagents/deepagents/middleware/skills.py` |
| StateBackend | `libs/deepagents/deepagents/backends/state.py` |
| StoreBackend | `libs/deepagents/deepagents/backends/store.py` |
| FilesystemBackend | `libs/deepagents/deepagents/backends/filesystem.py` |
| CompositeBackend | `libs/deepagents/deepagents/backends/composite.py` |
| BackendProtocol | `libs/deepagents/deepagents/backends/protocol.py` |
