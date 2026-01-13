"""
===============================================================================
ANNOTATED: create_deep_agent() - The Deep Agent Factory Function
===============================================================================

SOURCE: libs/deepagents/deepagents/graph.py

This file provides a heavily annotated explanation of how the create_deep_agent()
factory compiles a LangGraph StateGraph with all the capabilities needed for
long-horizon agentic orchestration.

===============================================================================
WHAT: Creates a fully-configured deep agent with planning, memory, delegation,
      and context management capabilities.

WHERE: This is the main entry point for the deepagents library. Called once
       at agent initialization time.

WHEN: Called when you need to create a new deep agent instance. The returned
      graph is then invoked for each conversation turn.

WHY: Composing all the middleware, tools, and backends manually is complex.
     This factory handles the composition, ensuring proper middleware order
     and configuration.

HOW: Through middleware stacking - each capability is a middleware layer that
     wraps the core agent with additional tools, prompts, and behaviors.

CONTEXT: LangGraph agents are compiled StateGraphs. This factory configures
         the graph with proper state schema, tools, and middleware interception.
===============================================================================
"""

# =============================================================================
# IMPORTS - Understanding the dependency tree
# =============================================================================

from collections.abc import Callable, Sequence
from typing import Any

# Core LangChain agent creation - the foundation
from langchain.agents import create_agent  # <-- Creates the base LangGraph agent

# Middleware for agent capabilities
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,    # Pauses for human approval
    InterruptOnConfig,           # Configuration for HITL
    TodoListMiddleware,          # Planning via write_todos
)
from langchain.agents.middleware.summarization import SummarizationMiddleware  # Context compression
from langchain.agents.middleware.types import AgentMiddleware  # Base middleware type
from langchain.agents.structured_output import ResponseFormat  # Structured output schema
from langchain.chat_models import init_chat_model  # Model initialization
from langchain_anthropic import ChatAnthropic  # Default model provider
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware  # Performance optimization
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.cache.base import BaseCache
from langgraph.graph.state import CompiledStateGraph  # Return type
from langgraph.store.base import BaseStore  # Persistent storage
from langgraph.types import Checkpointer  # State persistence

# DeepAgents-specific middleware and backends
from deepagents.backends import StateBackend
from deepagents.backends.protocol import BackendFactory, BackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware  # Virtual FS
from deepagents.middleware.memory import MemoryMiddleware  # AGENTS.md loading
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware  # Error recovery
from deepagents.middleware.skills import SkillsMiddleware  # Progressive skill disclosure
from deepagents.middleware.subagents import (
    CompiledSubAgent,
    SubAgent,
    SubAgentMiddleware,  # task tool for delegation
)


# =============================================================================
# BASE SYSTEM PROMPT
# =============================================================================
# WHY: This minimal prompt is appended to the user's system_prompt to establish
#      that the agent has access to tools. Each middleware adds its own
#      specialized instructions on top of this.

BASE_AGENT_PROMPT = "In order to complete the objective that the user asks of you, you have access to a number of standard tools."


# =============================================================================
# DEFAULT MODEL CONFIGURATION
# =============================================================================
# WHY Claude Sonnet 4.5: Balances capability with cost for agentic tasks.
#     20k max_tokens allows for long, detailed responses in complex tasks.

def get_default_model() -> ChatAnthropic:
    """Get the default model for deep agents.

    Returns:
        `ChatAnthropic` instance configured with Claude Sonnet 4.5.
    """
    return ChatAnthropic(
        model_name="claude-sonnet-4-5-20250929",
        max_tokens=20000,
    )


# =============================================================================
# THE MAIN FACTORY FUNCTION
# =============================================================================

def create_deep_agent(
    # -------------------------------------------------------------------------
    # Model Configuration
    # -------------------------------------------------------------------------
    model: str | BaseChatModel | None = None,
    # WHAT: The LLM to use for reasoning
    # HOW: Can be a string like "openai:gpt-4o" or a pre-configured model instance
    # DEFAULT: claude-sonnet-4-5-20250929

    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    # WHAT: Custom tools beyond the built-in ones
    # NOTE: Deep agents already include: write_todos, ls, read_file, write_file,
    #       edit_file, glob, grep, execute, task

    # -------------------------------------------------------------------------
    # Prompt Configuration
    # -------------------------------------------------------------------------
    *,  # Force keyword arguments from here
    system_prompt: str | None = None,
    # WHAT: Your custom instructions for the agent's role and behavior
    # HOW: Gets prepended to BASE_AGENT_PROMPT, then each middleware adds more

    # -------------------------------------------------------------------------
    # Middleware Configuration
    # -------------------------------------------------------------------------
    middleware: Sequence[AgentMiddleware] = (),
    # WHAT: Additional custom middleware to add after standard middleware
    # WHEN: For custom logging, rate limiting, or specialized behaviors

    # -------------------------------------------------------------------------
    # Delegation Configuration
    # -------------------------------------------------------------------------
    subagents: list[SubAgent | CompiledSubAgent] | None = None,
    # WHAT: Specialized agents that can be invoked via task()
    # WHY: Context quarantine - subagents handle complex tasks in isolation

    # -------------------------------------------------------------------------
    # Progressive Disclosure Features
    # -------------------------------------------------------------------------
    skills: list[str] | None = None,
    # WHAT: Paths to skill directories (e.g., ["/skills/user/"])
    # HOW: Skills are loaded and described, agent reads full content on-demand

    memory: list[str] | None = None,
    # WHAT: Paths to AGENTS.md files for session context
    # HOW: Content injected into system prompt at startup

    # -------------------------------------------------------------------------
    # Output Configuration
    # -------------------------------------------------------------------------
    response_format: ResponseFormat | None = None,
    # WHAT: Schema for structured output (e.g., JSON)

    context_schema: type[Any] | None = None,
    # WHAT: Additional state schema fields

    # -------------------------------------------------------------------------
    # State Persistence Configuration
    # -------------------------------------------------------------------------
    checkpointer: Checkpointer | None = None,
    # WHAT: Enables state persistence and HITL interrupts
    # REQUIRED FOR: interrupt_on to work (HITL)

    store: BaseStore | None = None,
    # WHAT: Persistent storage for StoreBackend
    # WHEN: Using StoreBackend for cross-thread file persistence

    backend: BackendProtocol | BackendFactory | None = None,
    # WHAT: Storage backend for virtual filesystem
    # DEFAULT: StateBackend (ephemeral, in LangGraph state)
    # OPTIONS: FilesystemBackend, StoreBackend, CompositeBackend

    # -------------------------------------------------------------------------
    # Human-in-the-Loop Configuration
    # -------------------------------------------------------------------------
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    # WHAT: Which tools require human approval before execution
    # EXAMPLE: {"write_file": True, "execute": True}
    # REQUIRES: checkpointer to be set

    # -------------------------------------------------------------------------
    # Debug and Metadata
    # -------------------------------------------------------------------------
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,

) -> CompiledStateGraph:
    """Create a deep agent.

    ==========================================================================
    RETURN VALUE: A compiled LangGraph StateGraph ready for invoke/ainvoke
    ==========================================================================
    """

    # =========================================================================
    # STEP 1: Model Resolution
    # =========================================================================
    # WHAT: Ensure we have a configured model instance
    # WHY: Supports multiple input formats for convenience

    if model is None:
        model = get_default_model()
    elif isinstance(model, str):
        # Support "provider:model" format like "openai:gpt-4o"
        model = init_chat_model(model)

    # =========================================================================
    # STEP 2: Summarization Trigger Configuration
    # =========================================================================
    # WHAT: Configure when to trigger context summarization
    # WHY: Prevent context overflow in long conversations
    # HOW: Different strategies based on model capabilities

    if (
        model.profile is not None
        and isinstance(model.profile, dict)
        and "max_input_tokens" in model.profile
        and isinstance(model.profile["max_input_tokens"], int)
    ):
        # Model reports its context limit - use fraction-based triggers
        trigger = ("fraction", 0.85)  # Summarize at 85% capacity
        keep = ("fraction", 0.10)     # Keep 10% after summarization
    else:
        # Unknown context limit - use safe token-based defaults
        trigger = ("tokens", 170000)  # Summarize at 170k tokens
        keep = ("messages", 6)        # Keep last 6 messages

    # =========================================================================
    # STEP 3: Build Subagent Middleware Stack
    # =========================================================================
    # WHAT: Configure middleware for subagents (spawned via task tool)
    # WHY: Subagents need their own capabilities but simpler than main agent
    # KEY DIFFERENCE: Subagents don't have SubAgentMiddleware (no nesting)

    subagent_middleware: list[AgentMiddleware] = [
        TodoListMiddleware(),  # Planning capability for subagents too
    ]

    # Default to StateBackend factory if no backend specified
    backend = backend if backend is not None else (lambda rt: StateBackend(rt))

    # Add skills to subagents if configured
    if skills is not None:
        subagent_middleware.append(SkillsMiddleware(backend=backend, sources=skills))

    subagent_middleware.extend([
        FilesystemMiddleware(backend=backend),  # File operations
        SummarizationMiddleware(                # Context management
            model=model,
            trigger=trigger,
            keep=keep,
            trim_tokens_to_summarize=None,
        ),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),  # Performance
        PatchToolCallsMiddleware(),  # Error recovery for dangling tool calls
    ])

    # =========================================================================
    # STEP 4: Build Main Agent Middleware Stack
    # =========================================================================
    # WHAT: Configure the full middleware stack for the main orchestrator
    # ORDER MATTERS: Middleware wraps in order, executes in reverse
    #
    # EXECUTION FLOW (request path):
    # User Request
    #   → TodoListMiddleware.wrap_model_call
    #     → MemoryMiddleware.wrap_model_call
    #       → SkillsMiddleware.wrap_model_call
    #         → FilesystemMiddleware.wrap_model_call
    #           → SubAgentMiddleware.wrap_model_call
    #             → SummarizationMiddleware.wrap_model_call
    #               → AnthropicCachingMiddleware.wrap_model_call
    #                 → PatchToolCallsMiddleware.wrap_model_call
    #                   → HumanInTheLoopMiddleware.wrap_model_call
    #                     → ACTUAL MODEL CALL
    #
    # Response flows back through the same stack in reverse

    deepagent_middleware: list[AgentMiddleware] = [
        # -----------------------------------------------------------------
        # Layer 1: Planning (write_todos tool)
        # -----------------------------------------------------------------
        TodoListMiddleware(),
        # ADDS: write_todos tool
        # ENABLES: Plan-Act-Update loop for multi-step tasks
    ]

    # -----------------------------------------------------------------
    # Layer 2: Memory (optional, AGENTS.md loading)
    # -----------------------------------------------------------------
    if memory is not None:
        deepagent_middleware.append(MemoryMiddleware(backend=backend, sources=memory))
        # ADDS: Memory content to system prompt
        # ADDS: Guidelines for when to update memory via edit_file

    # -----------------------------------------------------------------
    # Layer 3: Skills (optional, progressive disclosure)
    # -----------------------------------------------------------------
    if skills is not None:
        deepagent_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
        # ADDS: Skill descriptions to system prompt
        # ENABLES: Read skill content on-demand via read_file

    deepagent_middleware.extend([
        # -----------------------------------------------------------------
        # Layer 4: Virtual Filesystem (7 tools)
        # -----------------------------------------------------------------
        FilesystemMiddleware(backend=backend),
        # ADDS: ls, read_file, write_file, edit_file, glob, grep, execute
        # ADDS: Filesystem usage instructions to system prompt
        # INTERCEPTS: Large tool results, evicts to filesystem

        # -----------------------------------------------------------------
        # Layer 5: Subagent Delegation (task tool)
        # -----------------------------------------------------------------
        SubAgentMiddleware(
            default_model=model,
            default_tools=tools,
            subagents=subagents if subagents is not None else [],
            default_middleware=subagent_middleware,  # Stack from Step 3
            default_interrupt_on=interrupt_on,       # HITL for subagents too
            general_purpose_agent=True,              # Always include general-purpose
        ),
        # ADDS: task tool for spawning subagents
        # ENABLES: Context quarantine - subagents get isolated state
        # KEY: Only final message returns to main agent

        # -----------------------------------------------------------------
        # Layer 6: Context Management (automatic summarization)
        # -----------------------------------------------------------------
        SummarizationMiddleware(
            model=model,
            trigger=trigger,  # When to summarize (from Step 2)
            keep=keep,        # What to keep after summarization
            trim_tokens_to_summarize=None,
        ),
        # INTERCEPTS: Long conversations
        # ACTION: Summarizes old messages to free context

        # -----------------------------------------------------------------
        # Layer 7: Performance Optimization (Anthropic-specific)
        # -----------------------------------------------------------------
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        # OPTIMIZES: Reduces API costs via prompt caching
        # SAFE: Ignores non-Anthropic models gracefully

        # -----------------------------------------------------------------
        # Layer 8: Error Recovery
        # -----------------------------------------------------------------
        PatchToolCallsMiddleware(),
        # HANDLES: Dangling tool calls without responses
        # ADDS: Synthetic "cancelled" ToolMessages for recovery
    ])

    # -----------------------------------------------------------------
    # Layer 9: Custom Middleware (user-provided)
    # -----------------------------------------------------------------
    if middleware:
        deepagent_middleware.extend(middleware)

    # -----------------------------------------------------------------
    # Layer 10: Human-in-the-Loop (final layer, closest to model)
    # -----------------------------------------------------------------
    if interrupt_on is not None:
        deepagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
        # INTERCEPTS: Tool calls matching interrupt_on config
        # ACTION: Pauses execution for human approval
        # REQUIRES: checkpointer to be configured

    # =========================================================================
    # STEP 5: Create and Return the Compiled Agent
    # =========================================================================
    # WHAT: Compile the LangGraph StateGraph with all configuration
    # OUTPUT: Ready-to-invoke CompiledStateGraph

    return create_agent(
        model,
        system_prompt=system_prompt + "\n\n" + BASE_AGENT_PROMPT if system_prompt else BASE_AGENT_PROMPT,
        tools=tools,
        middleware=deepagent_middleware,
        response_format=response_format,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit": 1000})
    # NOTE: High recursion limit (1000) allows for long agent loops
    # WHY: Deep agents may take 100+ tool calls for complex tasks


# =============================================================================
# GRAPH WIRING: How LangGraph Handles the Agent Loop
# =============================================================================
"""
The create_agent() function internally creates a StateGraph with this structure:

┌─────────────────────────────────────────────────────────────────────────────┐
│                           LANGGRAPH STATE MACHINE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   START                                                                      │
│     │                                                                        │
│     ▼                                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         "agent" NODE                                 │   │
│   │  • Middleware.wrap_model_call() chains execute                      │   │
│   │  • Model receives messages + tools + system prompt                  │   │
│   │  • Model returns: text response OR tool_calls                       │   │
│   └───────────────────────────┬─────────────────────────────────────────┘   │
│                               │                                              │
│                               ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       CONDITIONAL EDGE                               │   │
│   │  if tool_calls: → go to "tools" node                                │   │
│   │  else: → go to END                                                  │   │
│   └───────────────────────────┬─────────────────────────────────────────┘   │
│                               │                                              │
│                    ┌──────────┴──────────┐                                   │
│                    │                     │                                   │
│              [has tools]          [no tools]                                 │
│                    │                     │                                   │
│                    ▼                     ▼                                   │
│   ┌─────────────────────────┐       ┌─────────┐                             │
│   │      "tools" NODE       │       │   END   │                             │
│   │  • Middleware.wrap_tool_call()  │         │                             │
│   │  • Execute each tool call       │         │                             │
│   │  • Add ToolMessages to state    │         │                             │
│   │  • Return to "agent" node       │         │                             │
│   └───────────────┬─────────┘       └─────────┘                             │
│                   │                                                          │
│                   └─────────────────────────────┐                            │
│                                                 │                            │
│                                                 ▼                            │
│                                           [back to agent]                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

INTERRUPTS (for HITL):
- HumanInTheLoopMiddleware sets interrupt_before=["tools"] for specified tools
- Graph pauses BEFORE tool execution
- Human can approve, modify, or reject
- Graph resumes from checkpoint
"""


# =============================================================================
# STATE SCHEMA: What Lives in the Agent State
# =============================================================================
"""
The agent state is composed from multiple middleware state schemas:

class ComposedAgentState(TypedDict):
    # Base agent state
    messages: Annotated[list[AnyMessage], add_messages]  # Conversation history

    # TodoListMiddleware
    todos: list[Todo]  # Current task list

    # FilesystemMiddleware
    files: Annotated[dict[str, FileData], file_data_reducer]  # Virtual filesystem

    # MemoryMiddleware
    memory_contents: dict[str, str]  # Loaded AGENTS.md content (private)

    # SkillsMiddleware
    skills_metadata: list[SkillMetadata]  # Loaded skill info (private)

    # Structured output (if configured)
    structured_response: Any

The state flows through the graph and is modified by:
1. Agent node: Adds AIMessages (model responses)
2. Tools node: Adds ToolMessages (tool results)
3. Middleware: Can add state updates via Command objects
"""


# =============================================================================
# TWO-WAY COMMUNICATION: Main Agent ↔ Subagent
# =============================================================================
"""
VERTICAL COMMUNICATION (Orchestrator → Subagent → Orchestrator):

1. TASK CREATION (Main → Sub):
   - Main agent calls task(description="...", subagent_type="researcher")
   - SubAgentMiddleware creates subagent with:
     - Fresh messages: [HumanMessage(content=description)]
     - Inherited state: files, memory_contents, skills_metadata
     - EXCLUDED: messages, todos, structured_response

2. TASK EXECUTION (Sub runs independently):
   - Subagent has its own middleware stack (simpler)
   - Subagent can read/write files visible to main agent
   - Subagent maintains own conversation history (isolated)

3. RESULT RETURN (Sub → Main):
   - Only FINAL message from subagent returns
   - Returned as ToolMessage to main agent
   - Subagent's internal conversation DISCARDED
   - Files written by subagent PERSIST (shared backend)

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   MAIN AGENT                                                                │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │ messages: [User, AI, Tool, AI, Tool, ...]                         │    │
│   │ files: {"/notes.md": ..., "/data.json": ...}                      │    │
│   └───────────────────────────────┬───────────────────────────────────┘    │
│                                   │                                         │
│                task("Research X", "researcher")                             │
│                                   │                                         │
│                                   ▼                                         │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │                         SUBAGENT                                   │    │
│   │   messages: [HumanMessage("Research X")]  ← Fresh context         │    │
│   │   files: {"/notes.md": ..., "/data.json": ...}  ← Shared          │    │
│   │                                                                    │    │
│   │   [Subagent works autonomously, may write to /research/output.md] │    │
│   │                                                                    │    │
│   │   Final: AIMessage("Research complete. Key findings: ...")        │    │
│   └───────────────────────────────┬───────────────────────────────────┘    │
│                                   │                                         │
│                    Return: ToolMessage("Research complete...")              │
│                                   │                                         │
│                                   ▼                                         │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │ MAIN AGENT (continued)                                             │    │
│   │ messages: [..., ToolMessage("Research complete...")]              │    │
│   │ files: {"/notes.md": ..., "/research/output.md": ...}  ← Updated  │    │
│   └───────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

LATERAL COMMUNICATION (Subagent ↔ Subagent via Shared State):
- Subagents DO NOT communicate directly
- They communicate via SHARED FILES in the backend
- Subagent A writes /data/intermediate.json
- Subagent B reads /data/intermediate.json
- Main agent coordinates the handoff
"""
