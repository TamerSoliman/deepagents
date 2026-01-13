# Code Refactoring Pattern

> Systematic code improvement using deep agents

## Overview

Code refactoring benefits from systematic analysis and careful changes. This pattern shows how to coordinate agents for safe, comprehensive refactoring.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CODE REFACTORING ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                    ┌─────────────────────────────┐                          │
│                    │    REFACTORING COORDINATOR  │                          │
│                    │                             │                          │
│                    │  - Understands codebase     │                          │
│                    │  - Plans refactoring        │                          │
│                    │  - Coordinates changes      │                          │
│                    │  - Validates results        │                          │
│                    └──────────────┬──────────────┘                          │
│                                   │                                          │
│            ┌──────────────────────┼──────────────────────┐                  │
│            │                      │                      │                  │
│            ▼                      ▼                      ▼                  │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐          │
│   │    ANALYZER     │   │    REFACTORER   │   │    VALIDATOR    │          │
│   │                 │   │                 │   │                 │          │
│   │ - Code analysis │   │ - Code changes  │   │ - Run tests     │          │
│   │ - Find patterns │   │ - Apply fixes   │   │ - Check types   │          │
│   │ - Identify debt │   │ - Update refs   │   │ - Verify build  │          │
│   └─────────────────┘   └─────────────────┘   └─────────────────┘          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Implementation

### Specialized Agents

```python
subagents = [
    {
        "name": "analyzer",
        "description": "Analyzes code to find refactoring opportunities",
        "system_prompt": """You are a code analyzer.

        Your job:
        1. Read source files from /workspace/
        2. Identify code smells and patterns
        3. Find refactoring opportunities
        4. Document findings

        Output: Write analysis to /analysis/findings.md

        Look for:
        - Duplicated code
        - Long functions (>50 lines)
        - Deep nesting (>3 levels)
        - Unclear naming
        - Missing type hints
        - Unused imports/variables
        - Inconsistent patterns

        Format findings as:
        ## [File Path]
        ### Issue: [Name]
        Lines: [start-end]
        Severity: HIGH/MEDIUM/LOW
        Description: [what's wrong]
        Suggestion: [how to fix]
        """,
        "tools": [],
    },
    {
        "name": "refactorer",
        "description": "Applies refactoring changes to code",
        "system_prompt": """You are a code refactorer.

        Your job:
        1. Read refactoring plan from /plan/
        2. Read source file
        3. Apply changes carefully
        4. Preserve functionality
        5. Update references if needed

        Rules:
        - ALWAYS read file before editing
        - Make ONE logical change per edit
        - Preserve existing behavior
        - Update imports if needed
        - Follow existing code style

        Output: Edit files in /workspace/
        Log changes to /changes/log.md
        """,
        "tools": [],
    },
    {
        "name": "validator",
        "description": "Validates code changes by running tests and checks",
        "system_prompt": """You are a code validator.

        Your job:
        1. Run test suite
        2. Run type checker
        3. Run linter
        4. Check build succeeds
        5. Report any failures

        Output: Write results to /validation/results.md

        Commands to run:
        - pytest tests/
        - mypy src/
        - ruff check src/
        - python -m py_compile src/**/*.py

        Report format:
        ## Tests
        Status: PASS/FAIL
        Details: [output]

        ## Type Check
        Status: PASS/FAIL
        Details: [errors if any]
        """,
        "tools": [execute_tool],
    },
]
```

### Refactoring Coordinator

```python
agent = create_deep_agent(
    subagents=subagents,
    backend=lambda rt: FilesystemBackend(root_dir="/project"),
    system_prompt="""You are a refactoring coordinator.

    ## Refactoring Protocol

    ### Phase 1: Analysis
    task("Analyze /workspace/src/ for refactoring opportunities", "analyzer")

    ### Phase 2: Planning
    Read /analysis/findings.md
    Create prioritized plan in /plan/refactoring.md:
    - HIGH severity first
    - Group related changes
    - Identify dependencies

    ### Phase 3: Execution (SEQUENTIAL - not parallel!)
    For each planned change:
    1. task("Apply [specific change] to [file]", "refactorer")
    2. task("Validate changes", "validator")
    3. If validation fails: revert and adjust

    ### Phase 4: Final Validation
    task("Run full test suite and checks", "validator")

    ## Safety Rules
    - Never refactor without tests
    - One change at a time
    - Validate after each change
    - Revert if tests fail
    - Document all changes
    """,
)
```

## Refactoring Workflow

### Example: Extract Function

```
COORDINATOR:

1. Analysis identifies: "Long function in /workspace/src/processor.py"

2. Create plan:
   write_file("/plan/refactoring.md", """
   # Refactoring Plan

   ## Change 1: Extract function from processor.py
   - File: /workspace/src/processor.py
   - Lines: 45-78
   - Action: Extract to helper function
   - New function: _process_item()
   """)

3. Execute refactoring:
   task("""
   Refactor /workspace/src/processor.py:
   1. Read the file
   2. Extract lines 45-78 into function _process_item(item)
   3. Replace original code with function call
   4. Add appropriate docstring
   """, "refactorer")

4. Validate:
   task("Run tests and type checks", "validator")

5. Check result:
   read_file("/validation/results.md")
   If FAIL: revert changes, analyze issue
   If PASS: continue to next change
```

## Safe Refactoring Patterns

### Pattern 1: Rename Symbol

```python
refactorer_prompt = """
## Rename Symbol Safely

1. Find all occurrences:
   grep("old_name", "/workspace/", glob="*.py")

2. For each file with occurrences:
   - Read the file
   - Identify if it's the definition or usage
   - Apply rename with replace_all=True

3. Update imports if needed

4. Document in /changes/log.md
"""
```

### Pattern 2: Extract Function

```python
refactorer_prompt = """
## Extract Function Safely

1. Read target file completely
2. Identify code block to extract
3. Determine:
   - Input parameters (variables used but not defined in block)
   - Return values (variables defined and used after block)
4. Create new function with proper signature
5. Replace original code with function call
6. Add docstring to new function
"""
```

### Pattern 3: Move to Module

```python
refactorer_prompt = """
## Move Code to Module Safely

1. Read source file
2. Identify code to move (function/class)
3. Check for internal dependencies
4. Create/update target file
5. Add import to source file
6. Update all files that import the symbol
"""
```

## Validation Strategy

### Incremental Validation

```python
system_prompt = """
## Validation After Every Change

After each refactoring:
1. Run affected tests first (fast feedback)
2. Run type checker on changed files
3. If pass: continue
4. If fail: STOP and revert

Only run full suite after all changes complete.
"""
```

### Revert Strategy

```python
system_prompt = """
## Revert Protocol

If validation fails:
1. Read /changes/log.md for last change
2. Read original content from backup
3. Restore file to previous state
4. Analyze what went wrong
5. Adjust approach and retry
"""
```

## Complete Example

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

refactoring_agent = create_deep_agent(
    subagents=subagents,
    backend=FilesystemBackend(root_dir="/project"),
    checkpointer=checkpointer,
    interrupt_on={"edit_file": True},  # Human approval for edits
    system_prompt=COORDINATOR_PROMPT,
)

# Start refactoring
result = refactoring_agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Refactor the user authentication module to improve code quality"
    }]
}, config={"configurable": {"thread_id": "auth-refactor"}})
```

## Best Practices

### 1. Test Coverage First

```python
system_prompt = """
Before any refactoring:
1. Check test coverage for target code
2. If coverage < 80%: write tests first
3. Never refactor untested code
"""
```

### 2. Small Commits

```python
system_prompt = """
After each successful refactoring:
1. Document the change
2. Suggest commit message
3. Keep changes atomic (one logical change)
"""
```

### 3. Preserve Behavior

```python
system_prompt = """
Refactoring rules:
- NO functional changes
- Same inputs → same outputs
- Preserve public API
- Internal changes only
"""
```

## Related Tutorials

- [Human-in-the-Loop](04_human_in_the_loop.md)
- [Error Recovery Patterns](10_error_recovery.md)
- [Managing Massive Contexts](03_managing_massive_contexts.md)
