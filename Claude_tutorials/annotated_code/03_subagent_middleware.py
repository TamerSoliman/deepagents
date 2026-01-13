"""
===============================================================================
ANNOTATED: SubAgentMiddleware - Context Quarantine & Hierarchical Delegation
===============================================================================

SOURCE: libs/deepagents/deepagents/middleware/subagents.py

This file explains the most critical pattern for long-horizon agents:
CONTEXT QUARANTINE through subagent delegation.

===============================================================================
WHAT: Provides the `task` tool for spawning isolated subagents

WHERE: Injected into main agent middleware stack (not in subagents themselves)

WHEN: Used when tasks require isolated context or parallel execution

WHY: Prevents context overflow in the main orchestrator thread

HOW: Spawns ephemeral agents with fresh message history but shared file state
===============================================================================
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NotRequired, TypedDict, cast

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools import BaseTool, ToolRuntime
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
from langgraph.types import Command


# =============================================================================
# SUBAGENT SPECIFICATION
# =============================================================================
# WHAT: TypedDict defining how to configure a specialized subagent
# WHY: Type-safe configuration for custom subagents

class SubAgent(TypedDict):
    """Specification for a custom subagent.

    =========================================================================
    CREATING SPECIALIZED SUBAGENTS
    =========================================================================

    Subagents are specialized workers that handle specific domains:
    - Researcher: Tools for web search, document analysis
    - Writer: Tools for file editing, formatting
    - Coder: Tools for code execution, testing
    - Analyst: Tools for data processing, visualization

    Each subagent gets:
    1. Its own system prompt (role and behavior)
    2. Its own tools (domain-specific capabilities)
    3. Isolated message history (fresh context each invocation)
    4. Shared file state (can read/write to common filesystem)

    =========================================================================
    """

    name: str
    """Unique identifier for the subagent (e.g., "researcher", "writer")."""

    description: str
    """What this subagent does. Main agent uses this to decide when to delegate."""

    system_prompt: str
    """Instructions for the subagent's role and behavior."""

    tools: Sequence[BaseTool | Callable | dict[str, Any]]
    """Tools the subagent can use. Keep minimal and domain-specific."""

    model: NotRequired[str | BaseChatModel]
    """Optional model override. Use "provider:model-name" format."""

    middleware: NotRequired[list[AgentMiddleware]]
    """Additional middleware for custom behavior."""

    interrupt_on: NotRequired[dict[str, bool | InterruptOnConfig]]
    """HITL configuration for specific tools."""


class CompiledSubAgent(TypedDict):
    """A pre-compiled agent for complex workflows.

    Use when you need a pre-built LangGraph graph as a subagent.
    Must call .compile() on the graph before passing.
    """

    name: str
    description: str
    runnable: Runnable  # Pre-compiled LangGraph graph


# =============================================================================
# CONTEXT QUARANTINE: The Critical Pattern
# =============================================================================
# WHAT: Keys EXCLUDED when passing state to subagents
# WHY: Subagents get isolated context, only final result returns

_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response"}

"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CONTEXT QUARANTINE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  MAIN AGENT STATE:                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ messages: [User, AI, Tool, AI, Tool, AI, Tool, ...]  100+ messages  │   │
│  │ todos: [{task: "Research X", status: "in_progress"}, ...]           │   │
│  │ files: {"/notes.md": FileData, "/data.json": FileData}              │   │
│  │ memory_contents: {"path": "content"}                                │   │
│  │ skills_metadata: [SkillMetadata, ...]                               │   │
│  │ structured_response: None                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│                           task("Research topic X", "researcher")            │
│                                          │                                  │
│                                          ▼                                  │
│                              CONTEXT QUARANTINE                             │
│                              ─────────────────                              │
│                                                                              │
│  SUBAGENT STATE (what subagent receives):                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ messages: [HumanMessage("Research topic X")]  ← FRESH, only task    │   │
│  │ files: {"/notes.md": FileData, "/data.json": FileData}  ← SHARED    │   │
│  │ memory_contents: {"path": "content"}  ← INHERITED                   │   │
│  │ skills_metadata: [SkillMetadata, ...]  ← INHERITED                  │   │
│  │                                                                      │   │
│  │ ❌ NO: Main agent's conversation history                            │   │
│  │ ❌ NO: Main agent's todos                                           │   │
│  │ ❌ NO: Main agent's structured_response                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│                                          │                                  │
│                          [Subagent works autonomously]                      │
│                          [May take 50+ tool calls]                          │
│                          [Writes files, reads files]                        │
│                                          │                                  │
│                                          ▼                                  │
│                                                                              │
│  SUBAGENT FINAL STATE:                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ messages: [Human, AI, Tool, AI, Tool, ..., AI("Research complete")] │   │
│  │ files: {"/notes.md": ..., "/research/findings.md": CREATED}         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│                                          │                                  │
│                              RESULT PURIFICATION                            │
│                              ───────────────────                            │
│                                          │                                  │
│                                          ▼                                  │
│                                                                              │
│  RETURNED TO MAIN AGENT:                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ToolMessage("Research complete. Key findings: ...")                 │   │
│  │ files: {"/notes.md": ..., "/research/findings.md": ...}  ← UPDATED  │   │
│  │                                                                      │   │
│  │ ❌ NO: Subagent's internal conversation                             │   │
│  │ ❌ NO: Subagent's intermediate tool results                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

WHY THIS MATTERS:
─────────────────
1. CONTEXT PRESERVATION: Main agent's context not polluted by subagent's work
2. COST EFFICIENCY: Only final result counts against main agent's context
3. SCALABILITY: Can spawn multiple subagents in parallel
4. CLEAN ABSTRACTIONS: Main agent sees results, not implementation details
"""


# =============================================================================
# DEFAULT SUBAGENT PROMPT
# =============================================================================

DEFAULT_SUBAGENT_PROMPT = "In order to complete the objective that the user asks of you, you have access to a number of standard tools."


# =============================================================================
# TASK TOOL DESCRIPTION (Injected into main agent's context)
# =============================================================================

TASK_TOOL_DESCRIPTION = """Launch an ephemeral subagent to handle complex, multi-step independent tasks with isolated context windows.

Available agent types and the tools they have access to:
{available_agents}

When using the Task tool, you must specify a subagent_type parameter to select which agent type to use.

## Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
3. Each agent invocation is stateless. You will not be able to send additional messages to the agent, nor will the agent be able to communicate with you outside of its final report. Therefore, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted
5. Clearly tell the agent whether you expect it to create content, perform analysis, or just do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
6. If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first. Use your judgement.
7. When only the general-purpose agent is provided, you should use it for all tasks. It is great for isolating context and token usage, and completing specific, complex tasks, as it has all the same capabilities as the main agent.
"""


# =============================================================================
# TASK SYSTEM PROMPT (Additional instructions for main agent)
# =============================================================================

TASK_SYSTEM_PROMPT = """## `task` (subagent spawner)

You have access to a `task` tool to launch short-lived subagents that handle isolated tasks. These agents are ephemeral — they live only for the duration of the task and return a single result.

When to use the task tool:
- When a task is complex and multi-step, and can be fully delegated in isolation
- When a task is independent of other tasks and can run in parallel
- When a task requires focused reasoning or heavy token/context usage that would bloat the orchestrator thread
- When sandboxing improves reliability (e.g. code execution, structured searches, data formatting)
- When you only care about the output of the subagent, and not the intermediate steps (ex. performing a lot of research and then returned a synthesized report, performing a series of computations or lookups to achieve a concise, relevant answer.)

Subagent lifecycle:
1. **Spawn** → Provide clear role, instructions, and expected output
2. **Run** → The subagent completes the task autonomously
3. **Return** → The subagent provides a single structured result
4. **Reconcile** → Incorporate or synthesize the result into the main thread

When NOT to use the task tool:
- If you need to see the intermediate reasoning or steps after the subagent has completed (the task tool hides them)
- If the task is trivial (a few tool calls or simple lookup)
- If delegating does not reduce token usage, complexity, or context switching
- If splitting would add latency without benefit

## Important Task Tool Usage Notes to Remember
- Whenever possible, parallelize the work that you do. This is true for both tool_calls, and for tasks. Whenever you have independent steps to complete - make tool_calls, or kick off tasks (subagents) in parallel to accomplish them faster. This saves time for the user, which is incredibly important.
- Remember to use the `task` tool to silo independent tasks within a multi-part objective.
- You should use the `task` tool whenever you have a complex task that will take multiple steps, and is independent from other tasks that the agent needs to complete. These agents are highly competent and efficient."""


DEFAULT_GENERAL_PURPOSE_DESCRIPTION = "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent."


# =============================================================================
# SUBAGENT CREATION
# =============================================================================

def _get_subagents(
    *,
    default_model: str | BaseChatModel,
    default_tools: Sequence[BaseTool | Callable | dict[str, Any]],
    default_middleware: list[AgentMiddleware] | None,
    default_interrupt_on: dict[str, bool | InterruptOnConfig] | None,
    subagents: list[SubAgent | CompiledSubAgent],
    general_purpose_agent: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Create subagent instances from specifications.

    =========================================================================
    SUBAGENT COMPILATION
    =========================================================================

    This function:
    1. Creates a general-purpose agent (if enabled)
    2. Compiles each custom SubAgent spec into a runnable graph
    3. Handles CompiledSubAgent (pre-built graphs)
    4. Returns dict mapping name → runnable and list of descriptions

    GENERAL PURPOSE AGENT:
    - Always available (unless disabled)
    - Has all the same tools as main agent
    - Use for: search, file operations, multi-step tasks
    - Perfect for context isolation even without specialization

    =========================================================================
    """

    default_subagent_middleware = default_middleware or []
    agents: dict[str, Any] = {}
    subagent_descriptions = []

    # Create general-purpose agent if enabled
    if general_purpose_agent:
        general_purpose_middleware = [*default_subagent_middleware]
        if default_interrupt_on:
            general_purpose_middleware.append(
                HumanInTheLoopMiddleware(interrupt_on=default_interrupt_on)
            )

        general_purpose_subagent = create_agent(
            default_model,
            system_prompt=DEFAULT_SUBAGENT_PROMPT,
            tools=default_tools,
            middleware=general_purpose_middleware,
        )

        agents["general-purpose"] = general_purpose_subagent
        subagent_descriptions.append(
            f"- general-purpose: {DEFAULT_GENERAL_PURPOSE_DESCRIPTION}"
        )

    # Process custom subagents
    for agent_ in subagents:
        subagent_descriptions.append(f"- {agent_['name']}: {agent_['description']}")

        # Handle pre-compiled subagents
        if "runnable" in agent_:
            custom_agent = cast("CompiledSubAgent", agent_)
            agents[custom_agent["name"]] = custom_agent["runnable"]
            continue

        # Compile SubAgent spec
        _tools = agent_.get("tools", list(default_tools))
        subagent_model = agent_.get("model", default_model)

        _middleware = (
            [*default_subagent_middleware, *agent_["middleware"]]
            if "middleware" in agent_
            else [*default_subagent_middleware]
        )

        interrupt_on = agent_.get("interrupt_on", default_interrupt_on)
        if interrupt_on:
            _middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

        agents[agent_["name"]] = create_agent(
            subagent_model,
            system_prompt=agent_["system_prompt"],
            tools=_tools,
            middleware=_middleware,
        )

    return agents, subagent_descriptions


# =============================================================================
# TASK TOOL CREATION
# =============================================================================

def _create_task_tool(
    *,
    default_model: str | BaseChatModel,
    default_tools: Sequence[BaseTool | Callable | dict[str, Any]],
    default_middleware: list[AgentMiddleware] | None,
    default_interrupt_on: dict[str, bool | InterruptOnConfig] | None,
    subagents: list[SubAgent | CompiledSubAgent],
    general_purpose_agent: bool,
    task_description: str | None = None,
) -> BaseTool:
    """Create the task tool for invoking subagents.

    =========================================================================
    THE TASK TOOL
    =========================================================================

    PARAMETERS:
        description: str - Detailed task for the subagent
        subagent_type: str - Which subagent to use (e.g., "general-purpose")

    EXECUTION FLOW:
        1. Validate subagent_type exists
        2. Prepare isolated state (exclude messages, todos, structured_response)
        3. Create fresh messages with task description
        4. Invoke subagent graph
        5. Extract final message
        6. Return as ToolMessage to main agent

    =========================================================================
    """

    # Compile subagents
    subagent_graphs, subagent_descriptions = _get_subagents(
        default_model=default_model,
        default_tools=default_tools,
        default_middleware=default_middleware,
        default_interrupt_on=default_interrupt_on,
        subagents=subagents,
        general_purpose_agent=general_purpose_agent,
    )

    subagent_description_str = "\n".join(subagent_descriptions)

    def _return_command_with_state_update(result: dict, tool_call_id: str) -> Command:
        """Extract final result and prepare state update.

        RESULT PURIFICATION:
        - Only take LAST message from subagent
        - Include any file updates from subagent
        - EXCLUDE: subagent's messages, todos, structured_response
        """
        # Filter out excluded keys
        state_update = {
            k: v for k, v in result.items()
            if k not in _EXCLUDED_STATE_KEYS
        }

        # Extract final message text
        message_text = (
            result["messages"][-1].text.rstrip()
            if result["messages"][-1].text
            else ""
        )

        return Command(
            update={
                **state_update,  # Includes file updates
                "messages": [ToolMessage(message_text, tool_call_id=tool_call_id)],
            }
        )

    def _validate_and_prepare_state(
        subagent_type: str,
        description: str,
        runtime: ToolRuntime
    ) -> tuple[Runnable, dict]:
        """Prepare isolated state for subagent invocation.

        STATE PREPARATION:
        1. Get subagent runnable by type
        2. Copy state, excluding messages/todos/structured_response
        3. Create fresh messages with task description
        """
        subagent = subagent_graphs[subagent_type]

        # CONTEXT QUARANTINE: Exclude main agent's conversation
        subagent_state = {
            k: v for k, v in runtime.state.items()
            if k not in _EXCLUDED_STATE_KEYS
        }

        # Fresh message history with just the task
        subagent_state["messages"] = [HumanMessage(content=description)]

        return subagent, subagent_state

    # Build tool description
    if task_description is None:
        task_description = TASK_TOOL_DESCRIPTION.format(
            available_agents=subagent_description_str
        )
    elif "{available_agents}" in task_description:
        task_description = task_description.format(
            available_agents=subagent_description_str
        )

    def task(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        """Invoke a subagent to handle a task.

        Args:
            description: Detailed task description for the subagent
            subagent_type: Which subagent to use

        Returns:
            Command with final message and state updates
        """
        # Validate subagent exists
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"Cannot invoke {subagent_type}, allowed types: {allowed_types}"

        # Prepare isolated state
        subagent, subagent_state = _validate_and_prepare_state(
            subagent_type, description, runtime
        )

        # INVOKE SUBAGENT (may take many tool calls)
        result = subagent.invoke(subagent_state, runtime.config)

        # Return purified result
        if not runtime.tool_call_id:
            raise ValueError("Tool call ID required for subagent invocation")

        return _return_command_with_state_update(result, runtime.tool_call_id)

    async def atask(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        """Async version of task tool."""
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"Cannot invoke {subagent_type}, allowed types: {allowed_types}"

        subagent, subagent_state = _validate_and_prepare_state(
            subagent_type, description, runtime
        )

        result = await subagent.ainvoke(subagent_state, runtime.config)

        if not runtime.tool_call_id:
            raise ValueError("Tool call ID required for subagent invocation")

        return _return_command_with_state_update(result, runtime.tool_call_id)

    return StructuredTool.from_function(
        name="task",
        func=task,
        coroutine=atask,
        description=task_description,
    )


# =============================================================================
# SUBAGENT MIDDLEWARE
# =============================================================================

class SubAgentMiddleware(AgentMiddleware):
    """Middleware for providing subagent delegation via `task` tool.

    =========================================================================
    MIDDLEWARE CAPABILITIES
    =========================================================================

    1. ADDS TOOLS:
       - task: Spawn ephemeral subagents

    2. ADDS SYSTEM PROMPT:
       - When to use subagents
       - How to parallelize independent tasks
       - What information to provide subagents

    3. MANAGES SUBAGENTS:
       - Compiles SubAgent specs into runnable graphs
       - Provides general-purpose agent by default
       - Handles HITL for subagent tool calls

    =========================================================================
    USAGE
    =========================================================================

    # With default general-purpose agent only
    middleware = SubAgentMiddleware(
        default_model=model,
        default_tools=tools,
    )

    # With custom specialized subagents
    middleware = SubAgentMiddleware(
        default_model=model,
        default_tools=tools,
        subagents=[
            {
                "name": "researcher",
                "description": "Conducts web research",
                "system_prompt": "You are a research specialist...",
                "tools": [web_search],
            }
        ],
    )

    =========================================================================
    """

    def __init__(
        self,
        *,
        default_model: str | BaseChatModel,
        default_tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
        default_middleware: list[AgentMiddleware] | None = None,
        default_interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
        subagents: list[SubAgent | CompiledSubAgent] | None = None,
        system_prompt: str | None = TASK_SYSTEM_PROMPT,
        general_purpose_agent: bool = True,
        task_description: str | None = None,
    ) -> None:
        """Initialize SubAgentMiddleware.

        Args:
            default_model: Model for subagents
            default_tools: Tools for general-purpose subagent
            default_middleware: Middleware for all subagents
            default_interrupt_on: HITL config for subagents
            subagents: Custom subagent specifications
            system_prompt: Override system prompt
            general_purpose_agent: Include general-purpose agent (default True)
            task_description: Override task tool description
        """
        super().__init__()
        self.system_prompt = system_prompt

        task_tool = _create_task_tool(
            default_model=default_model,
            default_tools=default_tools or [],
            default_middleware=default_middleware,
            default_interrupt_on=default_interrupt_on,
            subagents=subagents or [],
            general_purpose_agent=general_purpose_agent,
            task_description=task_description,
        )

        self.tools = [task_tool]

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject subagent instructions into system prompt."""
        if self.system_prompt is not None:
            system_prompt = (
                request.system_prompt + "\n\n" + self.system_prompt
                if request.system_prompt
                else self.system_prompt
            )
            return handler(request.override(system_prompt=system_prompt))
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Async version of wrap_model_call."""
        if self.system_prompt is not None:
            system_prompt = (
                request.system_prompt + "\n\n" + self.system_prompt
                if request.system_prompt
                else self.system_prompt
            )
            return await handler(request.override(system_prompt=system_prompt))
        return await handler(request)


# =============================================================================
# HIERARCHICAL COMMUNICATION PATTERNS
# =============================================================================
"""
PATTERN 1: VERTICAL COMMUNICATION (Orchestrator ↔ Worker)
═══════════════════════════════════════════════════════════

                    ┌─────────────────┐
                    │  ORCHESTRATOR   │
                    │  (Main Agent)   │
                    └────────┬────────┘
                             │
                    task("Do X", "worker")
                             │
                             ▼
                    ┌─────────────────┐
                    │     WORKER      │
                    │  (Subagent)     │
                    └────────┬────────┘
                             │
                      ToolMessage
                   ("Result of X")
                             │
                             ▼
                    ┌─────────────────┐
                    │  ORCHESTRATOR   │
                    │  (continues)    │
                    └─────────────────┘

Communication:
- DOWN: Task description in HumanMessage
- UP: Final result in ToolMessage
- SHARED: Files in backend (can read/write)


PATTERN 2: LATERAL COMMUNICATION (Worker ↔ Worker via Files)
═════════════════════════════════════════════════════════════

                    ┌─────────────────┐
                    │  ORCHESTRATOR   │
                    └───┬─────────┬───┘
                        │         │
           task("Research")  task("Write report")
                        │         │
                        ▼         ▼
            ┌───────────────┐ ┌───────────────┐
            │  RESEARCHER   │ │    WRITER     │
            └───────┬───────┘ └───────┬───────┘
                    │                 │
         writes /research/data.json   │
                    │                 │
                    └────────────────►│
                                      │
                          reads /research/data.json
                                      │
                          writes /report/final.md
                                      │
                    ┌─────────────────┘
                    ▼
            ┌───────────────┐
            │  ORCHESTRATOR │
            │  (synthesizes)│
            └───────────────┘

Communication:
- Workers don't talk directly
- Workers communicate via SHARED FILES
- Orchestrator coordinates the handoff


PATTERN 3: PARALLEL EXECUTION
════════════════════════════════

                    ┌─────────────────┐
                    │  ORCHESTRATOR   │
                    └───┬───┬───┬─────┘
                        │   │   │
         ┌──────────────┤   │   ├──────────────┐
         │              │   │   │              │
         ▼              ▼   ▼   ▼              ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │ WORKER1 │    │ WORKER2 │    │ WORKER3 │
    └────┬────┘    └────┬────┘    └────┬────┘
         │              │              │
    [independent]  [independent]  [independent]
         │              │              │
         └──────────────┼──────────────┘
                        │
                        ▼
                ┌───────────────┐
                │  ORCHESTRATOR │
                │  (synthesizes │
                │   all results)│
                └───────────────┘

Key for Parallelization:
- Multiple task() calls in SAME message
- Workers run concurrently
- Results collected when all complete
- Orchestrator synthesizes combined output
"""
