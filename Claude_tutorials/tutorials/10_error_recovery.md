# Error Recovery Patterns

> Handling failures gracefully in long-running agent tasks

## Overview

Long-running tasks will encounter errors. Robust agents need strategies for:
- Tool call failures
- API errors
- Invalid inputs
- Partial completions
- Context issues

## Common Error Types

### 1. Tool Execution Errors

```
Tool: write_file("/readonly/file.txt", content)
Error: "Permission denied"
```

### 2. Validation Errors

```
Tool: edit_file("/file.txt", "nonexistent string", "replacement")
Error: "String not found in file"
```

### 3. API Errors

```
Tool: web_search("query")
Error: "API rate limit exceeded"
```

### 4. Context Errors

```
Error: "Message exceeds context window"
```

## Built-in Recovery: PatchToolCallsMiddleware

Handles dangling tool calls (tool called but no response):

```python
# Scenario: Tool call made but response missing
# (Can happen during interrupts or errors)

# PatchToolCallsMiddleware adds synthetic response:
ToolMessage(
    content="Tool call cancelled",
    tool_call_id=dangling_tool_call_id
)
```

This prevents the model from getting confused by incomplete tool call sequences.

## Recovery Strategies

### Strategy 1: Explicit Retry Logic

```python
agent = create_deep_agent(
    system_prompt="""## Error Handling

    When a tool call fails:
    1. Read the error message carefully
    2. Identify the root cause
    3. Adjust your approach
    4. Retry with corrected parameters

    Example:
    - If edit_file fails with "string not found":
      1. Read the file again to see current content
      2. Adjust old_string to match actual content
      3. Retry the edit

    - If write_file fails with "file exists":
      1. Use edit_file instead
      2. Or write to a different path

    Never retry the exact same failing call more than once.
    """
)
```

### Strategy 2: Fallback Approaches

```python
system_prompt = """## Fallback Strategies

When primary approach fails, try alternatives:

1. Web Search Fails:
   - Try different search terms
   - Try searching specific sites
   - Fall back to cached/known information

2. File Operation Fails:
   - Check path exists with ls
   - Check permissions
   - Try alternative location

3. Subagent Fails:
   - Simplify the task
   - Break into smaller pieces
   - Handle manually

Always have a plan B.
"""
```

### Strategy 3: Graceful Degradation

```python
system_prompt = """## Graceful Degradation

When you cannot complete a task fully:

1. Complete what you can
2. Document what failed and why
3. Provide partial results
4. Suggest next steps for user

Example:
"I was able to research topics A and B, but couldn't access
information about C due to API limits. Here's what I found..."
"""
```

## Handling Specific Errors

### File Not Found

```python
# Agent behavior pattern
"""
Tool: read_file("/nonexistent.md")
Error: "File not found"

Recovery:
1. ls("/") to see available files
2. glob("**/*.md") to find similar files
3. Inform user or create the file
"""
```

### Edit String Not Found

```python
# Agent behavior pattern
"""
Tool: edit_file("/file.md", "old text", "new text")
Error: "String not found"

Recovery:
1. read_file("/file.md") to see current content
2. Identify correct string (maybe whitespace difference)
3. Retry with exact match including whitespace
"""
```

### Multiple Occurrences

```python
# Agent behavior pattern
"""
Tool: edit_file("/file.md", "common text", "new text")
Error: "String appears 5 times. Use replace_all=True"

Recovery:
1. Decide: replace all or be more specific?
2. If all: retry with replace_all=True
3. If specific: add more context to old_string
"""
```

### Rate Limits

```python
# Agent behavior pattern
"""
Tool: web_search("query")
Error: "Rate limit exceeded"

Recovery:
1. Wait a moment (or inform user)
2. Reduce search frequency
3. Use cached results if available
4. Try alternative sources
"""
```

## Error Recovery in Subagents

### Subagent Failure Handling

```python
system_prompt = """## Subagent Error Handling

If a subagent returns an error or incomplete result:

1. Analyze the Error
   - What specifically failed?
   - Is it recoverable?

2. Retry with Adjustments
   - Simplify the task
   - Provide more context
   - Use different approach

3. Fall Back
   - Try different subagent
   - Handle manually
   - Report limitation to user

Example:
task("Complex research task") → Error
Retry: task("Simpler, focused research task")
"""
```

### Subagent Result Validation

```python
system_prompt = """## Validate Subagent Results

After receiving subagent result:

1. Check Completeness
   - Does result answer the original question?
   - Are all requested items present?

2. Check Quality
   - Is information accurate?
   - Are sources cited?

3. Handle Issues
   - If incomplete: follow up or supplement
   - If incorrect: retry with clarification
   - If partial: acknowledge limitations
"""
```

## Building Resilient Agents

### Defensive Tool Usage

```python
system_prompt = """## Defensive Tool Usage

Before operations, verify state:

1. Before edit_file:
   - ALWAYS read_file first
   - Verify the string exists

2. Before write_file:
   - Check if file exists (ls or read)
   - Use edit_file if it exists

3. Before delete operations:
   - Confirm what will be deleted
   - Consider backup first

Prevention is better than recovery.
"""
```

### Progress Checkpoints

```python
system_prompt = """## Progress Checkpoints

For long tasks, create checkpoints:

1. After completing each major step:
   - Write progress to /progress/checkpoint.md
   - Include: what's done, what's next

2. If error occurs:
   - Write error details to /progress/errors.md
   - Include: what failed, what was tried

3. On resume:
   - Read /progress/ to understand state
   - Continue from last checkpoint

This enables recovery from failures.
"""
```

### Error Documentation

```python
system_prompt = """## Error Documentation

When errors occur, document them:

1. Log Format:
   ```
   ## Error at [timestamp]
   - Operation: [what was attempted]
   - Error: [error message]
   - Context: [relevant details]
   - Resolution: [what was done]
   ```

2. Write to /logs/errors.md

3. Use for:
   - Debugging patterns
   - Improving strategies
   - User transparency
"""
```

## Code Example: Resilient Research Agent

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt="""You are a resilient research assistant.

    ## Error Handling Protocol

    1. Tool Errors:
       - Log error to /logs/errors.md
       - Attempt recovery (max 2 retries)
       - Fall back to alternative approach
       - Report if unrecoverable

    2. Progress Tracking:
       - Write checkpoints to /progress/
       - Include completed steps and next steps
       - Enable resume from failure

    3. Graceful Degradation:
       - Complete what's possible
       - Document limitations
       - Provide partial results with context

    4. User Communication:
       - Be transparent about issues
       - Explain what was tried
       - Suggest alternatives
    """
)
```

## Related Tutorials

- [The Planning Loop Pattern](01_planning_loop_pattern.md)
- [Human-in-the-Loop](04_human_in_the_loop.md)
- [State Management](12_state_management.md)
