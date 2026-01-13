"""
===============================================================================
ANNOTATED: MemoryMiddleware - Persistent Agent Memory via AGENTS.md
===============================================================================

SOURCE: libs/deepagents/deepagents/middleware/memory.py

This file explains how agents maintain persistent memory across sessions
using the AGENTS.md specification (https://agents.md/).

===============================================================================
WHAT: Loads context from AGENTS.md files and injects into system prompt

WHERE: Injected early in middleware stack (before FilesystemMiddleware)

WHEN: Loads at agent startup, persists through conversation

WHY: Agents need project-specific context and learned preferences

HOW: Reads from backend, formats content, injects into system prompt
===============================================================================
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, NotRequired, TypedDict

from langchain.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

if TYPE_CHECKING:
    from deepagents.backends.protocol import BACKEND_TYPES, BackendProtocol

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
    PrivateStateAttr,
)
from langchain.tools import ToolRuntime
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


# =============================================================================
# MEMORY STATE SCHEMA
# =============================================================================
# WHAT: Adds memory_contents to agent state
# KEY: Marked as PrivateStateAttr so not serialized to checkpoints

class MemoryState(AgentState):
    """State schema for MemoryMiddleware.

    Attributes:
        memory_contents: Dict mapping source paths to their loaded content.
            Marked as private so it's not included in the final agent state.
    """

    memory_contents: NotRequired[Annotated[dict[str, str], PrivateStateAttr]]
    # PrivateStateAttr means this is NOT checkpointed
    # WHY: Memory is reloaded from files on each session anyway


class MemoryStateUpdate(TypedDict):
    """State update for MemoryMiddleware."""

    memory_contents: dict[str, str]


# =============================================================================
# MEMORY SYSTEM PROMPT
# =============================================================================
# WHAT: Instructions for how the agent should use and update memory
# KEY: This is the "learning" capability that makes agents improve over time

MEMORY_SYSTEM_PROMPT = """<agent_memory>
{agent_memory}
</agent_memory>

<memory_guidelines>
    The above <agent_memory> was loaded in from files in your filesystem. As you learn from your interactions with the user, you can save new knowledge by calling the `edit_file` tool.

    **Learning from feedback:**
    - One of your MAIN PRIORITIES is to learn from your interactions with the user. These learnings can be implicit or explicit. This means that in the future, you will remember this important information.
    - When you need to remember something, updating memory must be your FIRST, IMMEDIATE action - before responding to the user, before calling other tools, before doing anything else. Just update memory immediately.
    - When user says something is better/worse, capture WHY and encode it as a pattern.
    - Each correction is a chance to improve permanently - don't just fix the immediate issue, update your instructions.
    - A great opportunity to update your memories is when the user interrupts a tool call and provides feedback. You should update your memories immediately before revising the tool call.
    - Look for the underlying principle behind corrections, not just the specific mistake.
    - The user might not explicitly ask you to remember something, but if they provide information that is useful for future use, you should update your memories immediately.

    **Asking for information:**
    - If you lack context to perform an action (e.g. send a Slack DM, requires a user ID/email) you should explicitly ask the user for this information.
    - It is preferred for you to ask for information, don't assume anything that you do not know!
    - When the user provides information that is useful for future use, you should update your memories immediately.

    **When to update memories:**
    - When the user explicitly asks you to remember something (e.g., "remember my email", "save this preference")
    - When the user describes your role or how you should behave (e.g., "you are a web researcher", "always do X")
    - When the user gives feedback on your work - capture what was wrong and how to improve
    - When the user provides information required for tool use (e.g., slack channel ID, email addresses)
    - When the user provides context useful for future tasks, such as how to use tools, or which actions to take in a particular situation
    - When you discover new patterns or preferences (coding styles, conventions, workflows)

    **When to NOT update memories:**
    - When the information is temporary or transient (e.g., "I'm running late", "I'm on my phone right now")
    - When the information is a one-time task request (e.g., "Find me a recipe", "What's 25 * 4?")
    - When the information is a simple question that doesn't reveal lasting preferences (e.g., "What day is it?", "Can you explain X?")
    - When the information is an acknowledgment or small talk (e.g., "Sounds good!", "Hello", "Thanks for that")
    - When the information is stale or irrelevant in future conversations
    - Never store API keys, access tokens, passwords, or any other credentials in any file, memory, or system prompt.
    - If the user asks where to put API keys or provides an API key, do NOT echo or save it.

    **Examples:**
    Example 1 (remembering user information):
    User: Can you connect to my google account?
    Agent: Sure, I'll connect to your google account, what's your google account email?
    User: john@example.com
    Agent: Let me save this to my memory.
    Tool Call: edit_file(...) -> remembers that the user's google account email is john@example.com

    Example 2 (remembering implicit user preferences):
    User: Can you write me an example for creating a deep agent in LangChain?
    Agent: Sure, I'll write you an example for creating a deep agent in LangChain <example code in Python>
    User: Can you do this in JavaScript
    Agent: Let me save this to my memory.
    Tool Call: edit_file(...) -> remembers that the user prefers to get LangChain code examples in JavaScript
    Agent: Sure, here is the JavaScript example <example code in JavaScript>

    Example 3 (do not remember transient information):
    User: I'm going to play basketball tonight so I will be offline for a few hours.
    Agent: Okay I'll add a block to your calendar.
    Tool Call: create_calendar_event(...) -> just calls a tool, does not commit anything to memory, as it is transient information
</memory_guidelines>
"""


# =============================================================================
# MEMORY MIDDLEWARE
# =============================================================================

class MemoryMiddleware(AgentMiddleware):
    """Middleware for loading agent memory from AGENTS.md files.

    =========================================================================
    MEMORY SYSTEM OVERVIEW
    =========================================================================

    The memory system provides:

    1. LOADING: Read AGENTS.md files from backend at startup
    2. INJECTION: Format and inject into system prompt
    3. LEARNING: Guidelines for when/how to update memory via edit_file
    4. PERSISTENCE: Memory files persist across sessions

    =========================================================================
    AGENTS.MD FILE FORMAT
    =========================================================================

    AGENTS.md files are standard Markdown with no required structure.
    Common sections include:

    ```markdown
    # Project Overview
    This is a web application using React and FastAPI.

    # Build Commands
    - Frontend: `npm run dev`
    - Backend: `uvicorn main:app`

    # Code Style
    - Use TypeScript for all frontend code
    - Prefer functional components with hooks
    - Use Pydantic models for API schemas

    # User Preferences
    - Prefers concise responses
    - Likes examples with explanations
    ```

    =========================================================================
    MULTIPLE SOURCES
    =========================================================================

    Memory can be loaded from multiple sources:

    ```python
    memory=[
        "~/.deepagents/AGENTS.md",      # Global user preferences
        "./.deepagents/AGENTS.md",      # Project-specific context
    ]
    ```

    Sources are loaded in order and concatenated.
    Later sources appear after earlier ones.

    =========================================================================
    """

    state_schema = MemoryState

    def __init__(
        self,
        *,
        backend: BACKEND_TYPES,
        sources: list[str],
    ) -> None:
        """Initialize the memory middleware.

        Args:
            backend: Backend instance or factory for file operations.
            sources: List of memory file paths to load.
                     Display names derived from paths automatically.
        """
        self._backend = backend
        self.sources = sources

    def _get_backend(
        self,
        state: MemoryState,
        runtime: Runtime,
        config: RunnableConfig
    ) -> BackendProtocol:
        """Resolve backend from instance or factory.

        Args:
            state: Current agent state.
            runtime: Runtime context for factory functions.
            config: Runnable config.

        Returns:
            Resolved backend instance.
        """
        if callable(self._backend):
            # Factory pattern - create backend with runtime
            tool_runtime = ToolRuntime(
                state=state,
                context=runtime.context,
                stream_writer=runtime.stream_writer,
                store=runtime.store,
                config=config,
                tool_call_id=None,
            )
            return self._backend(tool_runtime)
        return self._backend

    def _format_agent_memory(self, contents: dict[str, str]) -> str:
        """Format memory with locations and contents paired together.

        FORMAT:
        <agent_memory>
        /path/to/first/AGENTS.md
        [content of first file]

        /path/to/second/AGENTS.md
        [content of second file]
        </agent_memory>

        <memory_guidelines>
        [instructions for updating memory]
        </memory_guidelines>
        """
        if not contents:
            return MEMORY_SYSTEM_PROMPT.format(agent_memory="(No memory loaded)")

        sections = []
        for path in self.sources:
            if contents.get(path):
                sections.append(f"{path}\n{contents[path]}")

        if not sections:
            return MEMORY_SYSTEM_PROMPT.format(agent_memory="(No memory loaded)")

        memory_body = "\n\n".join(sections)
        return MEMORY_SYSTEM_PROMPT.format(agent_memory=memory_body)

    async def _load_memory_from_backend(
        self,
        backend: BackendProtocol,
        path: str,
    ) -> str | None:
        """Load memory content from a backend path (async).

        GRACEFUL DEGRADATION:
        - Returns None if file doesn't exist (file_not_found)
        - Memory files are optional - agent works without them
        - Other errors are raised
        """
        results = await backend.adownload_files([path])

        if len(results) != 1:
            raise AssertionError(f"Expected 1 response for {path}, got {len(results)}")

        response = results[0]

        if response.error is not None:
            # file_not_found is expected - memory files are optional
            if response.error == "file_not_found":
                return None
            raise ValueError(f"Failed to download {path}: {response.error}")

        if response.content is not None:
            return response.content.decode("utf-8")

        return None

    def _load_memory_from_backend_sync(
        self,
        backend: BackendProtocol,
        path: str,
    ) -> str | None:
        """Synchronous version of memory loading."""
        results = backend.download_files([path])

        if len(results) != 1:
            raise AssertionError(f"Expected 1 response for {path}, got {len(results)}")

        response = results[0]

        if response.error is not None:
            if response.error == "file_not_found":
                return None
            raise ValueError(f"Failed to download {path}: {response.error}")

        if response.content is not None:
            return response.content.decode("utf-8")

        return None

    # =========================================================================
    # before_agent: Load memory at startup
    # =========================================================================

    def before_agent(
        self,
        state: MemoryState,
        runtime: Runtime,
        config: RunnableConfig
    ) -> MemoryStateUpdate | None:
        """Load memory content before agent execution (synchronous).

        LIFECYCLE:
        1. Called ONCE at agent startup
        2. Skipped if memory already in state (resuming)
        3. Loads from all configured sources
        4. Returns state update with memory_contents

        RESUMING:
        - If checkpointed, memory_contents persists in state
        - This method returns None (skip loading)
        - Memory is already available
        """
        # Skip if already loaded (resuming from checkpoint)
        if "memory_contents" in state:
            return None

        backend = self._get_backend(state, runtime, config)
        contents: dict[str, str] = {}

        # Load from each source
        for path in self.sources:
            content = self._load_memory_from_backend_sync(backend, path)
            if content:
                contents[path] = content
                logger.debug(f"Loaded memory from: {path}")

        return MemoryStateUpdate(memory_contents=contents)

    async def abefore_agent(
        self,
        state: MemoryState,
        runtime: Runtime,
        config: RunnableConfig
    ) -> MemoryStateUpdate | None:
        """Async version of before_agent."""
        if "memory_contents" in state:
            return None

        backend = self._get_backend(state, runtime, config)
        contents: dict[str, str] = {}

        for path in self.sources:
            content = await self._load_memory_from_backend(backend, path)
            if content:
                contents[path] = content
                logger.debug(f"Loaded memory from: {path}")

        return MemoryStateUpdate(memory_contents=contents)

    # =========================================================================
    # modify_request: Inject memory into system prompt
    # =========================================================================

    def modify_request(self, request: ModelRequest) -> ModelRequest:
        """Inject memory content into the system prompt.

        PROMPT STRUCTURE:
        <agent_memory>
        [loaded content from AGENTS.md files]
        </agent_memory>

        <memory_guidelines>
        [instructions for updating memory]
        </memory_guidelines>

        [rest of system prompt]
        """
        contents = request.state.get("memory_contents", {})
        agent_memory = self._format_agent_memory(contents)

        if request.system_prompt:
            system_prompt = agent_memory + "\n\n" + request.system_prompt
        else:
            system_prompt = agent_memory

        return request.override(system_message=SystemMessage(system_prompt))

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Wrap model call to inject memory into system prompt."""
        modified_request = self.modify_request(request)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Async version of wrap_model_call."""
        modified_request = self.modify_request(request)
        return await handler(modified_request)


# =============================================================================
# MEMORY USAGE PATTERNS
# =============================================================================
"""
PATTERN 1: User Preferences Memory
═══════════════════════════════════

# ~/.deepagents/AGENTS.md

## User Info
- Name: John
- Email: john@example.com
- Timezone: PST

## Communication Preferences
- Prefers concise responses
- Likes bullet points over paragraphs
- Requests code examples with explanations

## Code Style
- Uses TypeScript for all projects
- Prefers functional programming patterns
- Uses 2-space indentation


PATTERN 2: Project-Specific Memory
═══════════════════════════════════

# ./project/.deepagents/AGENTS.md

## Project Overview
React dashboard application for analytics.

## Build Commands
- Development: `npm run dev`
- Test: `npm run test`
- Build: `npm run build`

## Architecture
- /src/components - React components
- /src/hooks - Custom hooks
- /src/api - API client functions
- /src/types - TypeScript types

## Conventions
- All components use functional style with hooks
- State management via React Query
- Styling via Tailwind CSS


PATTERN 3: Learning from Feedback
═══════════════════════════════════

INITIAL MEMORY:
## User Preferences
(empty)

AFTER USER SAYS "I prefer shorter responses":

## User Preferences
- Prefers shorter, more concise responses
- Avoid lengthy explanations unless requested

AFTER USER CORRECTS CODE STYLE:

## Code Style
- Use arrow functions for React components
- Import React types explicitly
- Use `const` instead of `let` when possible


PATTERN 4: Multi-Source Layering
═══════════════════════════════════

sources=[
    "~/.deepagents/global/AGENTS.md",   # User-wide defaults
    "./project/AGENTS.md",               # Project context
    "./project/.local/AGENTS.md",        # Local overrides (gitignored)
]

RESULTING SYSTEM PROMPT ORDER:
1. Global preferences
2. Project-specific context
3. Local overrides (most specific)

WHY ORDER MATTERS:
- Later content appears last in prompt
- Model tends to weight recent content more
- Allows layered override patterns
"""
