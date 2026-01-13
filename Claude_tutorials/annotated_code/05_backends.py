"""
===============================================================================
ANNOTATED: Storage Backends - Ephemeral, Persistent, and Hybrid Storage
===============================================================================

SOURCE: libs/deepagents/deepagents/backends/

This file explains the backend abstraction layer that enables flexible
storage strategies for the virtual filesystem.

===============================================================================
WHAT: Pluggable storage backends for file operations

WHERE: Used by FilesystemMiddleware, MemoryMiddleware, SkillsMiddleware

WHEN: All file operations route through backends

WHY: Different use cases need different persistence strategies

HOW: Common protocol (BackendProtocol) with multiple implementations
===============================================================================
"""

import abc
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypeAlias

from langchain.tools import ToolRuntime
from typing_extensions import TypedDict


# =============================================================================
# BACKEND PROTOCOL - The Common Interface
# =============================================================================
# WHAT: Abstract base class that all backends must implement
# WHY: Allows middleware to work with any storage backend

class BackendProtocol(abc.ABC):
    """Protocol for pluggable memory backends.

    =========================================================================
    ALL BACKENDS MUST IMPLEMENT
    =========================================================================

    File Operations:
    - ls_info(path) -> list[FileInfo]      # List directory
    - read(path, offset, limit) -> str     # Read file content
    - write(path, content) -> WriteResult  # Create new file
    - edit(path, old, new) -> EditResult   # Replace string in file
    - glob_info(pattern, path) -> list[FileInfo]  # Find files by pattern
    - grep_raw(pattern, path, glob) -> list[GrepMatch] | str  # Search content

    Batch Operations:
    - upload_files(files) -> list[FileUploadResponse]
    - download_files(paths) -> list[FileDownloadResponse]

    All methods have async versions (prefix with 'a'):
    - als_info, aread, awrite, aedit, aglob_info, agrep_raw
    - aupload_files, adownload_files

    =========================================================================
    """

    def ls_info(self, path: str) -> list["FileInfo"]:
        """List all files in a directory with metadata.

        Args:
            path: Absolute path to directory. Must start with '/'.

        Returns:
            List of FileInfo dicts:
            - path (required): Absolute file path
            - is_dir (optional): True if directory
            - size (optional): File size in bytes
            - modified_at (optional): ISO 8601 timestamp
        """

    async def als_info(self, path: str) -> list["FileInfo"]:
        """Async version - default runs sync in thread."""
        return await asyncio.to_thread(self.ls_info, path)

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content with line numbers.

        Args:
            file_path: Absolute path. Must start with '/'.
            offset: Line number to start from (0-indexed).
            limit: Maximum lines to read.

        Returns:
            Content with line numbers (cat -n format), or error string.

        PAGINATION:
        - First scan: read(path, limit=100)
        - Next section: read(path, offset=100, limit=200)
        - ALWAYS read before editing
        """

    def write(self, file_path: str, content: str) -> "WriteResult":
        """Write content to a NEW file (errors if exists).

        Returns:
            WriteResult with:
            - error: Error message or None
            - path: Absolute path of written file
            - files_update: State update dict (StateBackend) or None (others)
        """

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> "EditResult":
        """Perform exact string replacements.

        Returns:
            EditResult with:
            - error: Error message or None
            - path: Absolute path of edited file
            - files_update: State update dict or None
            - occurrences: Number of replacements made
        """


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class WriteResult:
    """Result from backend write operations.

    files_update MEANING:
    - StateBackend: Returns {path: FileData} for LangGraph state update
    - Other backends: Returns None (already persisted to external storage)
    """
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None


@dataclass
class EditResult:
    """Result from backend edit operations."""
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrences: int | None = None


class FileInfo(TypedDict):
    """Structured file listing info."""
    path: str
    is_dir: NotRequired[bool]
    size: NotRequired[int]
    modified_at: NotRequired[str]


class GrepMatch(TypedDict):
    """Structured grep match entry."""
    path: str
    line: int  # 1-indexed
    text: str


# =============================================================================
# STATE BACKEND - Ephemeral Storage in LangGraph State
# =============================================================================
# SOURCE: libs/deepagents/deepagents/backends/state.py

class StateBackend(BackendProtocol):
    """Backend that stores files in LangGraph agent state.

    =========================================================================
    CHARACTERISTICS
    =========================================================================

    EPHEMERAL:
    - Files persist ONLY within the current conversation thread
    - New thread = fresh filesystem
    - Perfect for temporary working files

    CHECKPOINTED:
    - If checkpointer configured, files survive interrupts
    - Resume from checkpoint = files restored
    - No external storage needed

    STATE UPDATES:
    - Write/edit return files_update dict
    - Middleware wraps in Command for LangGraph state update
    - Required because state is immutable

    =========================================================================
    WHEN TO USE
    =========================================================================

    - Default choice (no configuration needed)
    - Temporary working files during task
    - No persistence requirements
    - Testing and development

    =========================================================================
    """

    def __init__(self, runtime: "ToolRuntime"):
        """Initialize with runtime to access state."""
        self.runtime = runtime

    def ls_info(self, path: str) -> list[FileInfo]:
        """List files from state['files']."""
        files = self.runtime.state.get("files", {})
        infos: list[FileInfo] = []
        subdirs: set[str] = set()

        # Normalize path for prefix matching
        normalized_path = path if path.endswith("/") else path + "/"

        for k, fd in files.items():
            if not k.startswith(normalized_path):
                continue

            relative = k[len(normalized_path):]

            # Check if in subdirectory
            if "/" in relative:
                subdir_name = relative.split("/")[0]
                subdirs.add(normalized_path + subdir_name + "/")
                continue

            # Direct file
            size = len("\n".join(fd.get("content", [])))
            infos.append({
                "path": k,
                "is_dir": False,
                "size": int(size),
                "modified_at": fd.get("modified_at", ""),
            })

        # Add directories
        for subdir in sorted(subdirs):
            infos.append({"path": subdir, "is_dir": True, "size": 0, "modified_at": ""})

        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read from state['files'][file_path]."""
        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)

        if file_data is None:
            return f"Error: File '{file_path}' not found"

        # Format with line numbers
        return format_read_response(file_data, offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Write to state - returns state update for Command."""
        files = self.runtime.state.get("files", {})

        if file_path in files:
            return WriteResult(
                error=f"Cannot write to {file_path} - already exists. Use edit_file."
            )

        new_file_data = create_file_data(content)

        # Return update for LangGraph Command
        return WriteResult(
            path=file_path,
            files_update={file_path: new_file_data}
        )

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit in state - returns state update for Command."""
        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)

        if file_data is None:
            return EditResult(error=f"Error: File '{file_path}' not found")

        content = file_data_to_string(file_data)
        result = perform_string_replacement(content, old_string, new_string, replace_all)

        if isinstance(result, str):
            return EditResult(error=result)

        new_content, occurrences = result
        new_file_data = update_file_data(file_data, new_content)

        return EditResult(
            path=file_path,
            files_update={file_path: new_file_data},
            occurrences=int(occurrences)
        )


# =============================================================================
# STORE BACKEND - Persistent Cross-Thread Storage
# =============================================================================
# SOURCE: libs/deepagents/deepagents/backends/store.py

class StoreBackend(BackendProtocol):
    """Backend that stores files in LangGraph's BaseStore.

    =========================================================================
    CHARACTERISTICS
    =========================================================================

    PERSISTENT:
    - Files survive across conversations
    - Shared between all threads
    - Uses LangGraph's persistent store

    CROSS-THREAD:
    - Agent A writes /memory/notes.md
    - Agent B can read /memory/notes.md
    - Perfect for shared knowledge bases

    NAMESPACED:
    - Files organized by namespace
    - Optional assistant_id isolation
    - Prevents conflicts between agents

    =========================================================================
    WHEN TO USE
    =========================================================================

    - Long-term memory across sessions
    - Shared knowledge bases
    - User preferences that persist
    - Cross-conversation file sharing

    =========================================================================
    REQUIREMENTS
    =========================================================================

    Must provide `store` parameter to create_deep_agent():

    ```python
    from langgraph.store.memory import InMemoryStore

    store = InMemoryStore()  # Or PostgresStore, etc.

    agent = create_deep_agent(
        backend=lambda rt: StoreBackend(rt),
        store=store,
    )
    ```

    =========================================================================
    """

    def __init__(self, runtime: "ToolRuntime"):
        """Initialize with runtime to access store."""
        self.runtime = runtime

    def _get_store(self):
        """Get store from runtime, raise if missing."""
        store = self.runtime.store
        if store is None:
            raise ValueError("Store required but not available in runtime")
        return store

    def _get_namespace(self) -> tuple[str, ...]:
        """Get namespace for store operations.

        Preference order:
        1. assistant_id from config metadata (per-agent isolation)
        2. Default "filesystem" namespace
        """
        namespace = "filesystem"

        # Check for assistant_id in config
        runtime_cfg = getattr(self.runtime, "config", None)
        if isinstance(runtime_cfg, dict):
            assistant_id = runtime_cfg.get("metadata", {}).get("assistant_id")
            if assistant_id:
                return (assistant_id, namespace)

        return (namespace,)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Write to store - persists immediately."""
        store = self._get_store()
        namespace = self._get_namespace()

        # Check if exists
        existing = store.get(namespace, file_path)
        if existing is not None:
            return WriteResult(
                error=f"Cannot write to {file_path} - already exists."
            )

        file_data = create_file_data(content)
        store.put(namespace, file_path, file_data)

        # No files_update - already persisted
        return WriteResult(path=file_path, files_update=None)


# =============================================================================
# FILESYSTEM BACKEND - Real Disk Access
# =============================================================================
# SOURCE: libs/deepagents/deepagents/backends/filesystem.py

class FilesystemBackend(BackendProtocol):
    """Backend that reads/writes directly from filesystem.

    =========================================================================
    CHARACTERISTICS
    =========================================================================

    REAL DISK:
    - Actual files on disk
    - Changes persist immediately
    - Full filesystem access (or sandboxed)

    OPTIONAL SANDBOXING:
    - root_dir: Base directory for all operations
    - virtual_mode: Treat paths as virtual (prevent traversal)
    - Security: O_NOFOLLOW for symlink protection

    SEARCH OPTIMIZED:
    - Uses ripgrep for fast grep operations
    - Python fallback if ripgrep unavailable

    =========================================================================
    WHEN TO USE
    =========================================================================

    - Code editing tasks
    - File system automation
    - When real files needed
    - With sandbox for security

    =========================================================================
    SECURITY CONSIDERATIONS
    =========================================================================

    UNSANDBOXED (root_dir=None):
    - Agent has full filesystem access
    - ONLY use in trusted environments
    - Consider HITL for write operations

    SANDBOXED (root_dir="/some/path"):
    - Operations restricted to root_dir
    - Paths rewritten: /foo.txt -> /some/path/foo.txt
    - virtual_mode=True: stricter path handling

    =========================================================================
    """

    def __init__(
        self,
        root_dir: str | None = None,
        virtual_mode: bool = False,
        max_file_size_mb: int = 10,
    ):
        """Initialize filesystem backend.

        Args:
            root_dir: Base directory for all operations. None = full access.
            virtual_mode: Treat paths as virtual under root.
            max_file_size_mb: Maximum file size to read (DoS protection).
        """
        self.root_dir = root_dir
        self.virtual_mode = virtual_mode
        self.max_file_size_mb = max_file_size_mb


# =============================================================================
# COMPOSITE BACKEND - Route by Path Prefix
# =============================================================================
# SOURCE: libs/deepagents/deepagents/backends/composite.py

class CompositeBackend(BackendProtocol):
    """Routes file operations to different backends by path prefix.

    =========================================================================
    THE HYBRID PATTERN
    =========================================================================

    Different paths need different storage:
    - /tmp/* - Ephemeral working files (StateBackend)
    - /memories/* - Persistent notes (StoreBackend)
    - /workspace/* - Real code files (FilesystemBackend)

    CompositeBackend routes operations based on path prefix.

    =========================================================================
    CONFIGURATION
    =========================================================================

    ```python
    backend = lambda rt: CompositeBackend(
        # Default for unmatched paths
        default=StateBackend(rt),

        # Route specific prefixes
        routes={
            "/memories/": StoreBackend(rt),
            "/workspace/": FilesystemBackend(root_dir="/home/user/project"),
        }
    )

    agent = create_deep_agent(backend=backend)
    ```

    =========================================================================
    ROUTING BEHAVIOR
    =========================================================================

    Path: /tmp/working.txt
    → Matches nothing → StateBackend (default)

    Path: /memories/notes.md
    → Matches /memories/ → StoreBackend

    Path: /workspace/src/main.py
    → Matches /workspace/ → FilesystemBackend

    LONGEST PREFIX WINS:
    Routes sorted by length (longest first)
    /memories/archive/ before /memories/

    =========================================================================
    """

    def __init__(
        self,
        default: BackendProtocol,
        routes: dict[str, BackendProtocol],
    ) -> None:
        """Initialize composite backend.

        Args:
            default: Backend for unmatched paths.
            routes: Map of path prefixes to backends.
                    Prefixes should start and end with "/".
        """
        self.default = default
        self.routes = routes
        # Sort by length for correct prefix matching
        self.sorted_routes = sorted(
            routes.items(),
            key=lambda x: len(x[0]),
            reverse=True  # Longest first
        )

    def _get_backend_and_key(self, key: str) -> tuple[BackendProtocol, str]:
        """Get backend for path and strip route prefix.

        Example:
            key="/memories/notes.txt", route="/memories/"
            → (StoreBackend, "/notes.txt")
        """
        for prefix, backend in self.sorted_routes:
            if key.startswith(prefix):
                suffix = key[len(prefix):]
                stripped_key = f"/{suffix}" if suffix else "/"
                return backend, stripped_key

        return self.default, key

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Route read to appropriate backend."""
        backend, stripped_key = self._get_backend_and_key(file_path)
        return backend.read(stripped_key, offset=offset, limit=limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Route write to appropriate backend."""
        backend, stripped_key = self._get_backend_and_key(file_path)
        return backend.write(stripped_key, content)

    def ls_info(self, path: str) -> list[FileInfo]:
        """List from appropriate backend(s).

        SPECIAL CASES:
        - "/" lists default + all route directories
        - Route path lists only that backend
        - Other paths list default only
        """
        # Check if path matches a route
        for route_prefix, backend in self.sorted_routes:
            if path.startswith(route_prefix.rstrip("/")):
                suffix = path[len(route_prefix):]
                search_path = f"/{suffix}" if suffix else "/"
                infos = backend.ls_info(search_path)
                # Restore route prefix in paths
                return [{**fi, "path": f"{route_prefix[:-1]}{fi['path']}"} for fi in infos]

        # At root, show all
        if path == "/":
            results: list[FileInfo] = []
            results.extend(self.default.ls_info(path))
            # Add route directories
            for route_prefix, _ in self.sorted_routes:
                results.append({
                    "path": route_prefix,
                    "is_dir": True,
                    "size": 0,
                    "modified_at": "",
                })
            results.sort(key=lambda x: x.get("path", ""))
            return results

        # Other paths - default only
        return self.default.ls_info(path)


# =============================================================================
# SANDBOX BACKEND PROTOCOL - For Execution Support
# =============================================================================

class SandboxBackendProtocol(BackendProtocol):
    """Extended protocol for backends that support command execution.

    =========================================================================
    EXECUTION CAPABILITY
    =========================================================================

    Some backends can run shell commands:
    - Docker containers
    - Virtual machines
    - Sandboxed processes

    The execute() method provides this capability.
    FilesystemMiddleware checks for this protocol to enable the execute tool.

    =========================================================================
    """

    def execute(self, command: str) -> "ExecuteResponse":
        """Execute a shell command.

        Args:
            command: Full shell command string.

        Returns:
            ExecuteResponse with output, exit_code, truncated flag.
        """

    async def aexecute(self, command: str) -> "ExecuteResponse":
        """Async version."""
        return await asyncio.to_thread(self.execute, command)


@dataclass
class ExecuteResponse:
    """Result of command execution."""
    output: str          # Combined stdout/stderr
    exit_code: int | None = None  # 0 = success
    truncated: bool = False       # Output was cut off


# =============================================================================
# BACKEND SELECTION GUIDE
# =============================================================================
"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BACKEND SELECTION GUIDE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  USE CASE                          │ BACKEND                                │
│  ──────────────────────────────────│────────────────────────────────────── │
│  Simple tasks, no persistence      │ StateBackend (default)                 │
│  Testing and development           │ StateBackend                           │
│  Long-term memory across sessions  │ StoreBackend                           │
│  Shared knowledge between threads  │ StoreBackend                           │
│  Code editing tasks                │ FilesystemBackend                      │
│  Sandboxed file access             │ FilesystemBackend(root_dir=...)       │
│  Mixed storage needs               │ CompositeBackend                       │
│  Command execution                 │ SandboxBackendProtocol impl           │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  COMPOSITE BACKEND PATTERNS                                                  │
│  ──────────────────────────────────────────────────────────────────────────│
│                                                                              │
│  Pattern: Working + Persistent                                               │
│  ```python                                                                   │
│  backend = lambda rt: CompositeBackend(                                      │
│      default=StateBackend(rt),           # /tmp/* ephemeral                 │
│      routes={"/memories/": StoreBackend(rt)}  # /memories/* persistent      │
│  )                                                                           │
│  ```                                                                         │
│                                                                              │
│  Pattern: Virtual + Real Filesystem                                          │
│  ```python                                                                   │
│  backend = lambda rt: CompositeBackend(                                      │
│      default=StateBackend(rt),           # /notes/* virtual                 │
│      routes={"/code/": FilesystemBackend(root_dir="/project")}             │
│  )                                                                           │
│  ```                                                                         │
│                                                                              │
│  Pattern: Full Hybrid                                                        │
│  ```python                                                                   │
│  backend = lambda rt: CompositeBackend(                                      │
│      default=StateBackend(rt),           # Ephemeral working files          │
│      routes={                                                                │
│          "/memories/": StoreBackend(rt),  # Persistent memory               │
│          "/workspace/": FilesystemBackend(root_dir="/project"),            │
│          "/sandbox/": DockerSandboxBackend(container_id="..."),            │
│      }                                                                       │
│  )                                                                           │
│  ```                                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
"""


# =============================================================================
# UTILITY FUNCTIONS (from backends/utils.py)
# =============================================================================

def create_file_data(content: str) -> dict[str, Any]:
    """Create FileData with timestamps."""
    from datetime import UTC, datetime
    lines = content.split("\n")
    now = datetime.now(UTC).isoformat()
    return {"content": lines, "created_at": now, "modified_at": now}


def update_file_data(file_data: dict[str, Any], content: str) -> dict[str, Any]:
    """Update FileData preserving created_at."""
    from datetime import UTC, datetime
    lines = content.split("\n")
    now = datetime.now(UTC).isoformat()
    return {"content": lines, "created_at": file_data["created_at"], "modified_at": now}


def file_data_to_string(file_data: dict[str, Any]) -> str:
    """Convert FileData to string."""
    return "\n".join(file_data["content"])


def format_read_response(file_data: dict[str, Any], offset: int, limit: int) -> str:
    """Format file content with line numbers."""
    content = file_data_to_string(file_data)
    if not content.strip():
        return "System reminder: File exists but has empty contents"
    lines = content.splitlines()
    selected = lines[offset:offset + limit]
    # Format with line numbers (cat -n style)
    return "\n".join(f"{i + offset + 1:6d}\t{line}" for i, line in enumerate(selected))


def perform_string_replacement(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> tuple[str, int] | str:
    """Perform string replacement with validation."""
    occurrences = content.count(old_string)
    if occurrences == 0:
        return f"Error: String not found: '{old_string}'"
    if occurrences > 1 and not replace_all:
        return f"Error: String appears {occurrences} times. Use replace_all=True."
    return content.replace(old_string, new_string), occurrences
