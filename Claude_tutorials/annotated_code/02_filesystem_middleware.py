"""
===============================================================================
ANNOTATED: FilesystemMiddleware - Virtual Filesystem for Context Management
===============================================================================

SOURCE: libs/deepagents/deepagents/middleware/filesystem.py

This file explains how the virtual filesystem works, including:
- Tool implementations (ls, read_file, write_file, edit_file, glob, grep, execute)
- Large output eviction to prevent context overflow
- Backend abstraction (StateBackend, FilesystemBackend, StoreBackend)

===============================================================================
WHAT: Provides 7 file/execution tools with automatic context management

WHERE: Injected into the middleware stack in create_deep_agent()

WHEN: Active during every model call and tool execution

WHY: Agents need persistent working memory and large output handling
     to prevent context window overflow in long-running tasks

HOW: Tools delegate to backend for storage, middleware intercepts
     large results and offloads them to the filesystem
===============================================================================
"""

import os
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Literal, NotRequired

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain.tools import ToolRuntime
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command
from typing_extensions import TypedDict

from deepagents.backends import StateBackend
from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    SandboxBackendProtocol,
    WriteResult,
)
from deepagents.backends.utils import (
    format_content_with_line_numbers,
    format_grep_matches,
    sanitize_tool_call_id,
    truncate_if_too_long,
)


# =============================================================================
# FILE DATA STRUCTURE
# =============================================================================
# WHAT: How files are represented in state
# WHY: Track content AND metadata for proper file operations

class FileData(TypedDict):
    """Data structure for storing file contents with metadata."""

    content: list[str]
    """Lines of the file (split by newline)."""

    created_at: str
    """ISO 8601 timestamp of file creation."""

    modified_at: str
    """ISO 8601 timestamp of last modification."""


# =============================================================================
# FILE DATA REDUCER - LangGraph State Management
# =============================================================================
# WHAT: Controls how file updates merge into state
# WHY: LangGraph uses reducers to handle concurrent state updates
# KEY: None values DELETE files (enables file deletion)

def _file_data_reducer(
    left: dict[str, FileData] | None,
    right: dict[str, FileData | None]
) -> dict[str, FileData]:
    """Merge file updates with support for deletions.

    Args:
        left: Existing files dictionary. May be None during initialization.
        right: New files dictionary. None values = deletion markers.

    Returns:
        Merged dictionary. None values in right trigger deletions.

    Example:
        existing = {"/file1.txt": FileData(...), "/file2.txt": FileData(...)}
        updates = {"/file2.txt": None, "/file3.txt": FileData(...)}
        result = {"/file1.txt": FileData(...), "/file3.txt": FileData(...)}
        # /file2.txt was deleted by None value
    """
    if left is None:
        return {k: v for k, v in right.items() if v is not None}

    result = {**left}
    for key, value in right.items():
        if value is None:
            result.pop(key, None)  # DELETE
        else:
            result[key] = value    # ADD/UPDATE
    return result


# =============================================================================
# FILESYSTEM STATE SCHEMA
# =============================================================================
# WHAT: Adds 'files' field to agent state
# HOW: Composed with other middleware state schemas

class FilesystemState(AgentState):
    """State for the filesystem middleware."""

    files: Annotated[NotRequired[dict[str, FileData]], _file_data_reducer]
    """Files in the filesystem. Uses custom reducer for merge/delete."""


# =============================================================================
# PATH VALIDATION - Security
# =============================================================================
# WHAT: Prevents path traversal attacks
# WHY: Agent-generated paths could be malicious

def _validate_path(path: str, *, allowed_prefixes: Sequence[str] | None = None) -> str:
    """Validate and normalize file path for security.

    Security checks:
    - No ".." traversal
    - No "~" expansion
    - No Windows absolute paths (C:\...)
    - Optional prefix whitelist

    Args:
        path: The path to validate
        allowed_prefixes: Optional whitelist of allowed path prefixes

    Returns:
        Normalized path starting with /

    Raises:
        ValueError: On security violation

    Examples:
        _validate_path("foo/bar")           # → "/foo/bar"
        _validate_path("../etc/passwd")     # → ValueError
        _validate_path("C:\\Users\\...")    # → ValueError
    """
    if ".." in path or path.startswith("~"):
        msg = f"Path traversal not allowed: {path}"
        raise ValueError(msg)

    # Reject Windows paths - maintain virtual path consistency
    if re.match(r"^[a-zA-Z]:", path):
        msg = f"Windows absolute paths not supported: {path}"
        raise ValueError(msg)

    # Normalize to Unix-style
    normalized = os.path.normpath(path)
    normalized = normalized.replace("\\", "/")

    # Ensure leading slash
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    # Check against prefix whitelist
    if allowed_prefixes is not None:
        if not any(normalized.startswith(prefix) for prefix in allowed_prefixes):
            msg = f"Path must start with one of {allowed_prefixes}: {path}"
            raise ValueError(msg)

    return normalized


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

# Constants for pagination and formatting
EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"
MAX_LINE_LENGTH = 2000
LINE_NUMBER_WIDTH = 6
DEFAULT_READ_OFFSET = 0
DEFAULT_READ_LIMIT = 500  # Default to 500 lines to prevent context overflow


def _read_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """Generate the read_file tool.

    =========================================================================
    read_file TOOL
    =========================================================================
    WHAT: Read file contents with line numbers and pagination

    PARAMETERS:
        file_path: Absolute path (must start with /)
        offset: Starting line (0-indexed, default 0)
        limit: Max lines to read (default 500)

    PAGINATION PATTERN (for large files):
        1. read_file(path, limit=100)  # Scan structure
        2. read_file(path, offset=100, limit=200)  # Read next section
        3. read_file(path)  # Full read only when editing

    WHY PAGINATION:
        - Prevents context overflow in exploration
        - Allows targeted reading of large files
        - Essential for codebase exploration

    OUTPUT FORMAT: cat -n style
        1    first line
        2    second line
        ...
    """

    def sync_read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = DEFAULT_READ_OFFSET,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        return resolved_backend.read(file_path, offset=offset, limit=limit)

    return StructuredTool.from_function(
        name="read_file",
        description=READ_FILE_TOOL_DESCRIPTION,
        func=sync_read_file,
        # coroutine=async_read_file,  # Also has async version
    )


def _write_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """Generate the write_file tool.

    =========================================================================
    write_file TOOL
    =========================================================================
    WHAT: Create a NEW file (errors if file exists)

    PARAMETERS:
        file_path: Absolute path for new file
        content: String content to write

    BEHAVIOR:
        - FAILS if file already exists (use edit_file instead)
        - Creates parent directories implicitly (backend-dependent)

    STATE UPDATE:
        For StateBackend, returns Command with files_update
        For external backends, writes directly
    """

    def sync_write_file(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        res: WriteResult = resolved_backend.write(file_path, content)

        if res.error:
            return res.error

        # STATE BACKEND: Return Command to update LangGraph state
        # WHY: StateBackend stores files IN state, needs state update
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Updated file {res.path}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        # EXTERNAL BACKEND: Already persisted, just return message
        return f"Updated file {res.path}"

    return StructuredTool.from_function(
        name="write_file",
        description=WRITE_FILE_TOOL_DESCRIPTION,
        func=sync_write_file,
    )


def _edit_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """Generate the edit_file tool.

    =========================================================================
    edit_file TOOL
    =========================================================================
    WHAT: Exact string replacement in existing files

    PARAMETERS:
        file_path: Absolute path to existing file
        old_string: Exact string to find (including whitespace)
        new_string: Replacement string
        replace_all: If True, replace ALL occurrences (default False)

    BEHAVIOR:
        - FAILS if old_string not found
        - FAILS if old_string not unique (unless replace_all=True)
        - Preserves file timestamps (updates modified_at)

    BEST PRACTICES:
        1. ALWAYS read_file before edit_file
        2. Use enough context to make old_string unique
        3. Preserve exact indentation from read output
    """

    def sync_edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        *,
        replace_all: bool = False,
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        res: EditResult = resolved_backend.edit(
            file_path, old_string, new_string, replace_all=replace_all
        )

        if res.error:
            return res.error

        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Successfully replaced {res.occurrences} instance(s)",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'"

    return StructuredTool.from_function(
        name="edit_file",
        description=EDIT_FILE_TOOL_DESCRIPTION,
        func=sync_edit_file,
    )


# =============================================================================
# TOOL RESULT EVICTION - Preventing Context Overflow
# =============================================================================
# WHAT: Automatically offloads large tool results to filesystem
# WHY: Tool results >20k tokens would consume too much context
# HOW: Intercept tool results, write to /large_tool_results/, return pointer

TOO_LARGE_TOOL_MSG = """Tool result too large, the result of this tool call {tool_call_id} was saved in the filesystem at this path: {file_path}
You can read the result from the filesystem by using the read_file tool, but make sure to only read part of the result at a time.
You can do this by specifying an offset and limit in the read_file tool call.
For example, to read the first 100 lines, you can use the read_file tool with offset=0 and limit=100.

Here are the first 10 lines of the result:
{content_sample}
"""


class FilesystemMiddleware(AgentMiddleware):
    """Middleware for providing filesystem and optional execution tools.

    =========================================================================
    MIDDLEWARE CAPABILITIES
    =========================================================================

    1. ADDS TOOLS:
       - ls: List directory contents
       - read_file: Read with pagination
       - write_file: Create new files
       - edit_file: Replace strings in files
       - glob: Find files by pattern
       - grep: Search file contents
       - execute: Run shell commands (if SandboxBackendProtocol)

    2. ADDS SYSTEM PROMPT:
       - Filesystem usage instructions
       - Path conventions (absolute paths starting with /)
       - Execution guidelines (if available)

    3. INTERCEPTS TOOL RESULTS:
       - Checks result size (>20k tokens estimate)
       - Writes large results to /large_tool_results/
       - Returns truncated preview with file pointer

    =========================================================================
    """

    state_schema = FilesystemState

    def __init__(
        self,
        *,
        backend: BACKEND_TYPES | None = None,
        # WHAT: Storage backend for file operations
        # DEFAULT: StateBackend (ephemeral, in LangGraph state)

        system_prompt: str | None = None,
        # WHAT: Override default filesystem instructions

        custom_tool_descriptions: dict[str, str] | None = None,
        # WHAT: Override individual tool descriptions

        tool_token_limit_before_evict: int | None = 20000,
        # WHAT: Token threshold for large output eviction
        # HOW: Estimate 4 chars per token
        # SET TO None: Disable eviction
    ) -> None:
        self.tool_token_limit_before_evict = tool_token_limit_before_evict
        self.backend = backend if backend is not None else (lambda rt: StateBackend(rt))
        self._custom_system_prompt = system_prompt
        self.tools = _get_filesystem_tools(self.backend, custom_tool_descriptions)

    # =========================================================================
    # wrap_model_call: System Prompt Injection
    # =========================================================================

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Update system prompt and filter tools based on backend capabilities.

        FLOW:
        1. Check if backend supports execute (SandboxBackendProtocol)
        2. Filter out execute tool if not supported
        3. Build dynamic system prompt with available tools
        4. Call handler with modified request
        """
        # Check if execute tool is available and backend supports it
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )

        backend_supports_execution = False
        if has_execute_tool:
            backend = self._get_backend(request.runtime)
            backend_supports_execution = _supports_execution(backend)

            # Filter out execute if backend doesn't support it
            if not backend_supports_execution:
                filtered_tools = [
                    tool for tool in request.tools
                    if (tool.name if hasattr(tool, "name") else tool.get("name")) != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        # Build system prompt
        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]
            if has_execute_tool and backend_supports_execution:
                prompt_parts.append(EXECUTION_SYSTEM_PROMPT)
            system_prompt = "\n\n".join(prompt_parts)

        if system_prompt:
            new_prompt = (
                request.system_prompt + "\n\n" + system_prompt
                if request.system_prompt
                else system_prompt
            )
            request = request.override(system_prompt=new_prompt)

        return handler(request)

    # =========================================================================
    # wrap_tool_call: Large Result Eviction
    # =========================================================================

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """Check tool result size and evict to filesystem if too large.

        FLOW:
        1. Execute tool normally via handler
        2. Check result size (skip for filesystem tools - they handle their own)
        3. If >20k tokens estimate, evict to /large_tool_results/
        4. Return truncated preview with file pointer

        WHY SKIP FILESYSTEM TOOLS:
        - They already handle their own output
        - Prevents infinite recursion
        """
        # Skip eviction for filesystem tools (they handle their own output)
        if (
            self.tool_token_limit_before_evict is None
            or request.tool_call["name"] in TOOL_GENERATORS
        ):
            return handler(request)

        # Execute tool
        tool_result = handler(request)

        # Check and potentially evict
        return self._intercept_large_tool_result(tool_result, request.runtime)

    def _process_large_message(
        self,
        message: ToolMessage,
        resolved_backend: BackendProtocol,
    ) -> tuple[ToolMessage, dict[str, FileData] | None]:
        """Process a large ToolMessage by evicting to filesystem.

        ALGORITHM:
        1. Convert content to string
        2. Check if exceeds threshold (4 chars per token estimate)
        3. Write to /large_tool_results/{sanitized_tool_call_id}
        4. Create truncated preview (first 10 lines, 1000 chars max per line)
        5. Return new message with file pointer

        Returns:
            (processed_message, files_update or None)
        """
        if not self.tool_token_limit_before_evict:
            return message, None

        # Extract content as string
        if (
            isinstance(message.content, list)
            and len(message.content) == 1
            and isinstance(message.content[0], dict)
            and message.content[0].get("type") == "text"
        ):
            content_str = str(message.content[0]["text"])
        elif isinstance(message.content, str):
            content_str = message.content
        else:
            content_str = str(message.content)

        # Check size (4 chars per token heuristic)
        if len(content_str) <= 4 * self.tool_token_limit_before_evict:
            return message, None

        # Write to filesystem
        sanitized_id = sanitize_tool_call_id(message.tool_call_id)
        file_path = f"/large_tool_results/{sanitized_id}"
        result = resolved_backend.write(file_path, content_str)

        if result.error:
            return message, None

        # Create truncated preview
        content_sample = format_content_with_line_numbers(
            [line[:1000] for line in content_str.splitlines()[:10]],
            start_line=1
        )

        replacement_text = TOO_LARGE_TOOL_MSG.format(
            tool_call_id=message.tool_call_id,
            file_path=file_path,
            content_sample=content_sample,
        )

        processed_message = ToolMessage(
            content=replacement_text,
            tool_call_id=message.tool_call_id,
        )

        return processed_message, result.files_update


# =============================================================================
# TOOL DESCRIPTIONS (Injected into model)
# =============================================================================

READ_FILE_TOOL_DESCRIPTION = """Reads a file from the filesystem.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 500 lines starting from the beginning
- **IMPORTANT for large files**: Use pagination with offset and limit
  - First scan: read_file(path, limit=100) to see structure
  - Read more: read_file(path, offset=100, limit=200) for next section
- Lines longer than 2000 characters will be truncated
- Results use cat -n format with line numbers starting at 1
- ALWAYS read a file before editing it."""

WRITE_FILE_TOOL_DESCRIPTION = """Writes to a NEW file in the filesystem.

Usage:
- The file_path parameter must be an absolute path
- The content parameter must be a string
- This will create a NEW file - errors if file already exists
- Prefer editing existing files over creating new ones."""

EDIT_FILE_TOOL_DESCRIPTION = """Performs exact string replacements in files.

Usage:
- You must read_file BEFORE editing (will error otherwise)
- Preserve exact indentation from the read output
- old_string must be UNIQUE in file (or use replace_all=True)
- Use replace_all for renaming variables across the file."""

FILESYSTEM_SYSTEM_PROMPT = """## Filesystem Tools `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`

You have access to a filesystem. All file paths must start with a /.

- ls: list files in a directory (requires absolute path)
- read_file: read a file from the filesystem
- write_file: write to a file in the filesystem
- edit_file: edit a file in the filesystem
- glob: find files matching a pattern (e.g., "**/*.py")
- grep: search for text within files"""

EXECUTION_SYSTEM_PROMPT = """## Execute Tool `execute`

You have access to an `execute` tool for running shell commands in a sandboxed environment.
Use this for commands, scripts, tests, builds, and other shell operations."""


# =============================================================================
# HELPER: Backend Resolution
# =============================================================================

def _get_backend(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    runtime: ToolRuntime
) -> BackendProtocol:
    """Resolve backend from instance or factory.

    WHY FACTORY PATTERN:
    - StateBackend needs runtime to access state
    - Factory defers instantiation until tool execution
    - Allows same middleware config for different runtimes
    """
    if callable(backend):
        return backend(runtime)
    return backend


def _supports_execution(backend: BackendProtocol) -> bool:
    """Check if backend supports command execution.

    WHAT: Checks for SandboxBackendProtocol implementation
    WHY: Only some backends can run shell commands
    """
    # Import here to avoid circular dependency
    from deepagents.backends.composite import CompositeBackend

    if isinstance(backend, CompositeBackend):
        return isinstance(backend.default, SandboxBackendProtocol)

    return isinstance(backend, SandboxBackendProtocol)


# =============================================================================
# TOOL GENERATORS REGISTRY
# =============================================================================

TOOL_GENERATORS = {
    "ls": _ls_tool_generator,
    "read_file": _read_file_tool_generator,
    "write_file": _write_file_tool_generator,
    "edit_file": _edit_file_tool_generator,
    "glob": _glob_tool_generator,
    "grep": _grep_tool_generator,
    "execute": _execute_tool_generator,
}


def _get_filesystem_tools(
    backend: BackendProtocol,
    custom_tool_descriptions: dict[str, str] | None = None,
) -> list[BaseTool]:
    """Get all filesystem and execution tools.

    Returns: ls, read_file, write_file, edit_file, glob, grep, execute
    """
    if custom_tool_descriptions is None:
        custom_tool_descriptions = {}

    tools = []
    for tool_name, tool_generator in TOOL_GENERATORS.items():
        tool = tool_generator(backend, custom_tool_descriptions.get(tool_name))
        tools.append(tool)

    return tools
