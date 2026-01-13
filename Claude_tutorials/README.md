# Deep Agents Architecture: A Complete Guide

> Moving from "Simple Loop" Agents to "Managerial" Agents with Long-Horizon Orchestration

This documentation provides a comprehensive analysis of the `deepagents` library, demonstrating how to build sophisticated agentic systems capable of managing long-running, multi-step tasks through hierarchical delegation, persistent memory, and context management.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [The Four Pillars](#the-four-pillars)
3. [Middleware System](#middleware-system)
4. [Directory Structure](#directory-structure)
5. [Quick Start](#quick-start)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEEP AGENT ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     create_deep_agent() Factory                      │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                    MIDDLEWARE STACK                          │    │    │
│  │  │  ┌─────────────────────────────────────────────────────────┐│    │    │
│  │  │  │ 1. TodoListMiddleware        → Planning (write_todos)   ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 2. MemoryMiddleware          → Memory (AGENTS.md)       ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 3. SkillsMiddleware          → Skills (SKILL.md)        ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 4. FilesystemMiddleware      → Virtual FS (7 tools)     ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 5. SubAgentMiddleware        → Delegation (task tool)   ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 6. SummarizationMiddleware   → Context Management       ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 7. AnthropicCachingMiddleware → Performance             ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 8. PatchToolCallsMiddleware  → Error Recovery           ││    │    │
│  │  │  ├─────────────────────────────────────────────────────────┤│    │    │
│  │  │  │ 9. HumanInTheLoopMiddleware  → HITL Approval            ││    │    │
│  │  │  └─────────────────────────────────────────────────────────┘│    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     BACKEND STORAGE LAYER                            │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │    │
│  │  │StateBackend │  │StoreBackend │  │FilesystemBknd│  │Composite  │  │    │
│  │  │ (Ephemeral) │  │ (Persist)   │  │  (Disk)      │  │(Router)   │  │    │
│  │  └─────────────┘  └─────────────┘  └──────────────┘  └───────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     HIERARCHICAL AGENT SYSTEM                        │    │
│  │                                                                       │    │
│  │    ┌─────────────────────────────────────────────────────────────┐   │    │
│  │    │                    MAIN ORCHESTRATOR                         │   │    │
│  │    │  • Full middleware stack                                     │   │    │
│  │    │  • Access to all tools + subagents                          │   │    │
│  │    │  • Manages state and context                                │   │    │
│  │    └──────────────┬──────────────────────┬───────────────────────┘   │    │
│  │                   │                      │                           │    │
│  │         ┌─────────▼─────────┐  ┌─────────▼─────────┐                │    │
│  │         │  SUBAGENT: task   │  │  SUBAGENT: task   │                │    │
│  │         │  ┌─────────────┐  │  │  ┌─────────────┐  │                │    │
│  │         │  │ Isolated    │  │  │  │ Specialized │  │                │    │
│  │         │  │ Context     │  │  │  │ Tools       │  │                │    │
│  │         │  │ Quarantine  │  │  │  │ & Prompt    │  │                │    │
│  │         │  └─────────────┘  │  │  └─────────────┘  │                │    │
│  │         └───────────────────┘  └───────────────────┘                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Design Principles

1. **Middleware-Based Composition**: Each capability (planning, memory, delegation) is implemented as a composable middleware layer
2. **Context Quarantine**: Subagents operate in isolated contexts to prevent context overflow
3. **Backend Abstraction**: Storage is abstracted through backends (ephemeral, persistent, filesystem)
4. **Progressive Disclosure**: Skills and capabilities are revealed only when needed

---

## The Four Pillars

### 1. Planning (TodoListMiddleware)

**Purpose**: Maintain coherence over 50+ step tasks through explicit task tracking.

**Key Tool**: `write_todos`

```python
# The Plan-Act-Update Loop
# 1. PLAN: Create todos for the task
# 2. ACT: Work on tasks, mark as in_progress
# 3. UPDATE: Mark completed, add new tasks discovered
```

**Source**: `langchain.agents.middleware.TodoListMiddleware`

---

### 2. Memory (Multiple Systems)

**A. MemoryMiddleware** - Session context from AGENTS.md files
- Loads at startup
- Persists across conversation
- Guidelines for when to update

**B. Virtual Filesystem** - Working memory during tasks
- `StateBackend`: Ephemeral (per-thread)
- `StoreBackend`: Persistent (cross-thread)
- `FilesystemBackend`: Real disk access
- `CompositeBackend`: Route by path prefix

**Source**: `deepagents/middleware/memory.py`, `deepagents/backends/`

---

### 3. Delegation & Orchestration (SubAgentMiddleware)

**Purpose**: Distribute complex tasks to specialized, isolated subagents.

**Key Tool**: `task`

```python
# Context Quarantine Pattern
# 1. Main agent identifies task for delegation
# 2. task() spawns ephemeral subagent with isolated state
# 3. Subagent completes work autonomously
# 4. Only final result returned (context purified)
```

**State Isolation**:
```python
_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response"}
# Subagent receives: files, memory_contents, skills_metadata
# Subagent does NOT receive: conversation history, todo state
```

**Source**: `deepagents/middleware/subagents.py`

---

### 4. Instruction (System Prompts)

Each middleware injects specialized instructions:

| Middleware | System Prompt Focus |
|------------|---------------------|
| FilesystemMiddleware | File operations, path conventions |
| MemoryMiddleware | When/how to update memories |
| SkillsMiddleware | Progressive skill disclosure |
| SubAgentMiddleware | When to delegate, parallelization |

---

## Middleware System

### Middleware Lifecycle Hooks

```python
class AgentMiddleware:
    # Before agent starts
    def before_agent(state, runtime, config) -> StateUpdate | None

    # Modify system prompt and tools
    def wrap_model_call(request, handler) -> ModelResponse

    # Intercept tool execution
    def wrap_tool_call(request, handler) -> ToolMessage | Command
```

### Middleware Stack Execution Order

```
Request → TodoList → Memory → Skills → Filesystem → SubAgent → Summarization → Caching → PatchTools → HITL → Model
                                                                                                              ↓
Response ← TodoList ← Memory ← Skills ← Filesystem ← SubAgent ← Summarization ← Caching ← PatchTools ← HITL ← Model
```

---

## Directory Structure

```
Claude_tutorials/
├── README.md                          # This file
├── annotated_code/
│   ├── 01_create_deep_agent.py        # Annotated factory function
│   ├── 02_filesystem_middleware.py    # Annotated virtual FS
│   ├── 03_subagent_middleware.py      # Annotated delegation
│   ├── 04_memory_middleware.py        # Annotated memory system
│   └── 05_backends.py                 # Annotated storage backends
├── tutorials/
│   ├── 01_planning_loop_pattern.md
│   ├── 02_architecting_subagent_hierarchies.md
│   ├── 03_managing_massive_contexts.md
│   ├── 04_human_in_the_loop.md
│   ├── 05_long_term_memory.md
│   ├── 06_context_quarantine.md
│   ├── 07_middleware_composition.md
│   ├── 08_backend_selection.md
│   ├── 09_skills_system.md
│   ├── 10_error_recovery.md
│   ├── 11_parallel_subagents.md
│   ├── 12_state_management.md
│   ├── 13_prompt_caching.md
│   ├── 14_custom_middleware.md
│   ├── 15_file_pagination.md
│   ├── 16_tool_result_eviction.md
│   ├── 17_hierarchical_communication.md
│   ├── 18_summarization_strategies.md
│   ├── 19_custom_backends.md
│   ├── 20_composite_routing.md
│   ├── 21_deep_research_pattern.md
│   ├── 22_code_refactoring_pattern.md
│   ├── 23_multi_document_analysis.md
│   ├── 24_building_custom_tools.md
│   └── 25_testing_deep_agents.md
└── reference/
    └── architectural_reference_table.md
```

---

## Quick Start

### Basic Deep Agent

```python
from deepagents import create_deep_agent

# Simplest form - includes all default capabilities
agent = create_deep_agent(
    system_prompt="You are a helpful research assistant."
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "Research quantum computing"}]
})
```

### With Memory and Skills

```python
agent = create_deep_agent(
    system_prompt="You are an expert coder.",
    memory=["/memory/AGENTS.md"],           # Load AGENTS.md for context
    skills=["/skills/user/", "/skills/project/"],  # Load skill libraries
)
```

### With Custom Subagents

```python
subagents = [
    {
        "name": "researcher",
        "description": "Conducts thorough web research",
        "system_prompt": "You are a research specialist...",
        "tools": [web_search_tool],
    },
    {
        "name": "writer",
        "description": "Creates polished written content",
        "system_prompt": "You are a professional writer...",
        "tools": [edit_file_tool],
    }
]

agent = create_deep_agent(
    subagents=subagents,
    system_prompt="Coordinate research and writing tasks."
)
```

### With Persistent Storage

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

# Hybrid backend: ephemeral by default, persistent for /memories/
backend = lambda rt: CompositeBackend(
    default=StateBackend(rt),
    routes={"/memories/": StoreBackend(rt)}
)

agent = create_deep_agent(
    backend=backend,
    store=my_persistent_store,  # LangGraph BaseStore
)
```

### With Human-in-the-Loop

```python
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    checkpointer=MemorySaver(),
    interrupt_on={"write_file": True, "execute": True}  # Pause for approval
)
```

---

## Next Steps

1. **Understand the Orchestration Loop**: Start with `annotated_code/01_create_deep_agent.py`
2. **Learn Context Management**: Read `tutorials/03_managing_massive_contexts.md`
3. **Master Subagent Delegation**: Study `tutorials/02_architecting_subagent_hierarchies.md`
4. **Implement Human Oversight**: Follow `tutorials/04_human_in_the_loop.md`

---

## Key Source Files Reference

| Component | Path |
|-----------|------|
| Factory Function | `libs/deepagents/deepagents/graph.py` |
| FilesystemMiddleware | `libs/deepagents/deepagents/middleware/filesystem.py` |
| SubAgentMiddleware | `libs/deepagents/deepagents/middleware/subagents.py` |
| MemoryMiddleware | `libs/deepagents/deepagents/middleware/memory.py` |
| SkillsMiddleware | `libs/deepagents/deepagents/middleware/skills.py` |
| StateBackend | `libs/deepagents/deepagents/backends/state.py` |
| StoreBackend | `libs/deepagents/deepagents/backends/store.py` |
| CompositeBackend | `libs/deepagents/deepagents/backends/composite.py` |
| BackendProtocol | `libs/deepagents/deepagents/backends/protocol.py` |
