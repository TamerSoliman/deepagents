# File Pagination Patterns

> Efficiently reading large files without context overflow

## The Problem

```
Large file: 10,000 lines
read_file("/large.md")  # Reads ALL lines
Context usage: ~40,000 tokens  # Overflow risk!
```

## The Solution: Pagination

```
read_file("/large.md", offset=0, limit=100)    # Lines 1-100
read_file("/large.md", offset=100, limit=100)  # Lines 101-200
read_file("/large.md", offset=500, limit=50)   # Lines 501-550

Context usage: ~400 tokens per read  # Manageable!
```

## Pagination Parameters

```python
read_file(
    file_path: str,       # Absolute path
    offset: int = 0,      # Starting line (0-indexed)
    limit: int = 500,     # Max lines to read
) -> str                  # Content with line numbers
```

## Reading Strategies

### Strategy 1: Structure First

```python
system_prompt = """
## Large File Reading

1. SCAN: read_file(path, limit=100)
   - See file structure
   - Identify sections
   - Note line numbers

2. TARGET: read_file(path, offset=X, limit=Y)
   - Read specific sections
   - Skip irrelevant parts

3. DEEP DIVE: Only if needed
   - Read more of interesting sections
"""
```

### Strategy 2: Binary Search

For finding specific content in large files:

```python
system_prompt = """
## Finding Content in Large Files

1. Read middle: read_file(path, offset=500, limit=50)
2. Based on content, go up or down
3. Narrow down to target section
4. Read target with appropriate context

Like binary search: O(log n) reads instead of O(n)
"""
```

### Strategy 3: Section Sampling

```python
system_prompt = """
## Sampling Large Files

For 5000-line file:
1. Beginning: read_file(path, offset=0, limit=100)
2. Early-mid: read_file(path, offset=1000, limit=100)
3. Middle: read_file(path, offset=2500, limit=100)
4. Late-mid: read_file(path, offset=4000, limit=100)
5. End: read_file(path, offset=4900, limit=100)

Get representative view without reading everything.
"""
```

## Pattern: Reading for Edit

When you need to edit, you must have exact content:

```python
system_prompt = """
## Reading Before Edit

1. First, find the section:
   read_file("/code.py", limit=100)  # Find function location

2. Then, read exact lines for edit:
   read_file("/code.py", offset=45, limit=20)  # Get function

3. Now edit with exact content:
   edit_file("/code.py", old_string="exact match", new_string="replacement")

CRITICAL: edit_file requires EXACT string match
- Include whitespace as shown in read output
- Get enough context for unique match
"""
```

## Output Format

`read_file` returns cat -n style output:

```
     1	# First line of file
     2	def function():
     3	    """Docstring"""
     4	    pass
     5
     6	class MyClass:
     7	    def method(self):
     8	        return True
```

Line numbers help you:
1. Reference specific locations
2. Calculate offsets for next read
3. Understand file structure

## Examples

### Example 1: Exploring Code

```
Task: Understand a Python module

Step 1: See structure
> read_file("/src/module.py", limit=50)
Returns: imports, first class definition

Step 2: Find specific class
> Looking for "class UserManager"
> grep("class UserManager", "/src/")
> Found at line 234

Step 3: Read the class
> read_file("/src/module.py", offset=233, limit=100)
> Returns: UserManager class definition
```

### Example 2: Finding Configuration

```
Task: Find database config in large config file

Step 1: Scan file
> read_file("/config/settings.yaml", limit=100)
> See: general settings, no database yet

Step 2: Search for section
> grep("database", "/config/settings.yaml")
> Found at line 450

Step 3: Read database section
> read_file("/config/settings.yaml", offset=449, limit=50)
> Returns: database configuration
```

### Example 3: Reading Log Files

```
Task: Analyze recent logs (file has 50,000 lines)

Approach: Read recent entries (end of file)
> read_file("/var/log/app.log", offset=49900, limit=100)
> Returns: Last 100 log entries

For specific time range:
> grep("2024-01-15", "/var/log/app.log")
> Find line numbers
> read_file with appropriate offset
```

## Combining with grep

Use grep to find, then read for context:

```python
system_prompt = """
## Find Then Read Pattern

1. grep("pattern", "/path/") to find occurrences
2. Note file and line numbers from grep output
3. read_file with offset = line_number - context_lines
4. Get surrounding context for understanding
"""
```

## Best Practices

### 1. Always Paginate Unfamiliar Files

```python
# ❌ Never do this for unknown files
read_file("/unknown.txt")

# ✓ Always start with limit
read_file("/unknown.txt", limit=100)
```

### 2. Adjust Based on Content Density

```python
# Dense code: smaller chunks
read_file("/complex_code.py", limit=50)

# Sparse logs: larger chunks
read_file("/app.log", limit=200)
```

### 3. Track Your Position

```python
system_prompt = """
When paginating:
- Note where you stopped
- Continue from that offset
- Avoid re-reading same content

Example:
read_file(path, offset=0, limit=100)    # Lines 1-100
read_file(path, offset=100, limit=100)  # Lines 101-200 (not 1-200!)
"""
```

### 4. Use Line Numbers from Output

```python
# Output shows:
#    45	def target_function():
#    46	    return value

# To read more context:
read_file(path, offset=40, limit=20)  # 5 lines before, 15 after
```

## Related Tutorials

- [Managing Massive Contexts](03_managing_massive_contexts.md)
- [Tool Result Eviction](16_tool_result_eviction.md)
- [Error Recovery Patterns](10_error_recovery.md)
