"""LangChain agent wiring for the Telegram PoC.

This module configures a modern LangChain v1 agent with MCP tools and Redis-backed
message history via LangGraph checkpointing.

When LangSmith environment variables are set (LANGSMITH_TRACING, LANGSMITH_API_KEY, etc.),
all agent invocations are automatically traced to LangSmith for observability.

Migration Note: This uses LangChain v1's create_agent API which replaces the legacy
AgentExecutor + create_tool_calling_agent pattern with a simpler, unified approach
built on LangGraph.
"""

from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, TYPE_CHECKING

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt, ModelRequest, after_model
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from mcp_tools import MCPTool

if TYPE_CHECKING:
    from langgraph.pregel import CompiledGraph

LOGGER = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Runtime context passed to the agent for user-specific information."""
    current_date: str
    current_datetime: str
    telegram_id: int
    role: Optional[str]
    player_ids: Optional[list]
    player_names: Optional[Dict[str, int]]  # Map of player name to player ID
    odoo_partner_id: Optional[int]
    odoo_user_id: Optional[int]


class LangChainTelegramAgent:
    """Modern LangChain v1 agent using create_agent with Redis persistence.
    
    This replaces the legacy AgentExecutor + create_tool_calling_agent pattern
    with a unified create_agent approach built on LangGraph.
    """

    def __init__(
        self,
        *,
        tools: Iterable[MCPTool],
        redis_url: str,
        session_ttl: int,
        model: str,
        api_key: Optional[str],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_iterations: int = 25,
    ) -> None:
        """Initialize the agent with tools and configuration.
        
        Args:
            tools: MCP tools for the agent to use
            redis_url: Redis connection URL for checkpointing
            session_ttl: TTL for Redis keys (in seconds)
            model: Model identifier (e.g., "gpt-4o-mini")
            api_key: OpenAI API key
            system_prompt: Custom system prompt (optional)
            temperature: Model temperature (0.0 = deterministic)
            max_iterations: Max tool calling iterations
        """
        self.tools = list(tools)
        self.redis_url = redis_url
        self.session_ttl = session_ttl
        self.model_name = model
        self.max_iterations = max_iterations
        # Default system prompt if none provided at initialization
        default_system_prompt = """You are a helpful assistant for parents at a tennis academy.

Your capabilities:
1. search_sessions - Find upcoming training sessions
2. report_absence - Record player absences
3. get_invoices - Check invoices
4. get_contact_info - Get contact information

For requests outside these capabilities, say: "Това не мога да направя през чата. Моля използвайте порталa на академията."

Absence workflow:
1. Extract reason from parent's message (болна→illness, семейни причини→family reasons, etc.)
2. CRITICAL: When reporting absence by DATE, ALWAYS use ONLY the 'date' parameter (NEVER use 'session_id')
   - This lets the tool detect multiple sessions and ask for confirmation
   - Tool will handle single vs multiple session logic automatically
3. If tool asks for confirmation about multiple sessions, wait for user response
4. After confirmation, call report_absence again with confirm_all=True or specific session_id
5. After tool succeeds: Confirm briefly

Always use current date from context. Be concise."""

        self.system_prompt = system_prompt or default_system_prompt
        
        # Configure the model
        self.model = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            stream_usage=True,
        )
        
        # Initialize Redis checkpointer for conversation persistence
        self._checkpointer: Optional[AsyncRedisSaver] = None
        self._checkpointer_cm = None  # Store context manager reference
        self._checkpointer_url = redis_url
        
        # Agent will be initialized lazily with checkpointer
        if TYPE_CHECKING:
            from langgraph.pregel import CompiledGraph
            self.agent: Optional[CompiledGraph] = None
        else:
            self.agent = None
        
        LOGGER.info(
            "LangChain agent configuration ready: model=%s, tools=%d, max_iterations=%d",
            model, len(self.tools), max_iterations
        )

    async def _initialize_agent(self):
        """Initialize the agent with checkpointer (must be called before first use)."""
        if self.agent is not None:
            return
            
        # Initialize Redis checkpointer
        if self._checkpointer is None:
            try:
                # from_conn_string returns a context manager, enter it to get the checkpointer
                self._checkpointer_cm = AsyncRedisSaver.from_conn_string(self._checkpointer_url)
                self._checkpointer = await self._checkpointer_cm.__aenter__()
                
                # Setup Redis indices/structures on first use (idempotent)
                # This creates the necessary RediSearch indices and data structures
                await self._checkpointer.asetup()
                LOGGER.info("Initialized AsyncRedisSaver checkpointer with Redis indices")
            except Exception as e:
                LOGGER.error("Failed to initialize Redis checkpointer: %s", e, exc_info=True)
                raise
        
        # Middleware to replace AI response with template after successful tool execution
        @after_model
        def replace_tool_response_with_template(state, runtime):
            """Replace AI response with a template after successful report_absence tool execution.
            
            This ensures the agent cannot offer additional services or ask follow-up questions.
            We simply confirm the action and ask if the user needs anything else.
            """
            
            # Get messages from state
            messages = state.get("messages", [])
            if not messages:
                return None
            
            last_message = messages[-1]
            
            # Only process AIMessage responses (not tool calls)
            if not isinstance(last_message, AIMessage):
                return None
            
            # CRITICAL: If the last AI message has tool_calls, the tools haven't executed yet
            # Don't replace the response - let the tools execute first
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                return None
            
            # Look for ALL ToolMessages in the current turn
            # We iterate backwards from the message before the current one.
            # If we encounter a HumanMessage before finding a ToolMessage, it means
            # the tool execution belongs to a previous turn and is stale.
            tool_messages = []
            for msg in reversed(messages[:-1]):
                if isinstance(msg, HumanMessage):
                    # Found user input before tool - tool is stale
                    break
                if isinstance(msg, ToolMessage):
                    tool_messages.append(msg)
            
            if not tool_messages:
                return None
            
            # Check if ANY of the tools was report_absence
            report_absence_msgs = [m for m in tool_messages if getattr(m, 'name', None) == 'report_absence']
            
            if not report_absence_msgs:
                return None
            
            # Check for errors or clarification requests in ANY of the messages
            for msg in report_absence_msgs:
                content = str(getattr(msg, 'content', ''))
                if '[CLARIFICATION_NEEDED]' in content:
                    LOGGER.info("Tool is asking for confirmation - preserving agent's question")
                    return None
                if '❌' in content or 'Error' in content or 'ГРЕШКА' in content:
                    LOGGER.info("Tool reported an error - preserving agent's response")
                    return None
                if 'Няма тренировки' in content:
                    LOGGER.info("Tool reported no sessions - preserving agent's response")
                    return None
            
            # Collect details from all successful report_absence calls
            details = []
            import re
            
            for tool_msg in report_absence_msgs:
                tool_call_id = getattr(tool_msg, 'tool_call_id', None)
                tool_content = str(getattr(tool_msg, 'content', ''))
                
                if tool_call_id:
                    # Find the AIMessage that triggered this tool call
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls'):
                            for tool_call in msg.tool_calls:
                                if tool_call.get('id') == tool_call_id:
                                    args = tool_call.get('args', {})
                                    player_name = args.get('player_name')
                                    
                                    # Fallback: Extract player name from tool output if missing in args
                                    if not player_name:
                                        # Pattern 1: Multiple sessions - "... за всички ... за {Name}."
                                        match = re.search(r"за всички .+? за (.+?)\.", tool_content)
                                        if match:
                                            player_name = match.group(1)
                                        else:
                                            # Pattern 2: Single session - "... отсъствието на {Name} на/за ..."
                                            match = re.search(r"Отбелязах отсъствието на (.+?) (?:на|за)", tool_content)
                                            if match:
                                                player_name = match.group(1)

                                    details.append({
                                        'player_name': player_name,
                                        'date': args.get('date'),
                                        'confirm_all': bool(args.get('confirm_all')),
                                        'session_id': args.get('session_id')
                                    })
                                    break
                            # Optimization: if we found the call for this tool_msg, we could break inner loop
                            # but we need to be careful if multiple calls are in same AIMessage
            
            # Build the template response
            if not details:
                 template_response = "Разбрано. Отсъствието е регистрирано. Треньорите са уведомени. Мога ли да помогна с още нещо?"
            else:
                # Summarize details
                players = sorted(list(set(d['player_name'] for d in details if d['player_name'])))
                dates = sorted(list(set(d['date'] for d in details if d['date'])))
                
                if len(players) > 1:
                    players_str = " и ".join([", ".join(players[:-1]), players[-1]] if len(players) > 2 else players)
                    if len(dates) == 1:
                        template_response = f"Разбрано. Регистрирах отсъствие за {players_str} на {dates[0]}. Треньорите са уведомени. Мога ли да помогна с още нещо?"
                    else:
                        template_response = f"Разбрано. Регистрирах отсъствие за {players_str}. Треньорите са уведомени. Мога ли да помогна с още нещо?"
                elif len(players) == 1:
                    player = players[0]
                    # Find the detail for this player (first one)
                    d = next(d for d in details if d['player_name'] == player)
                    if d['confirm_all']:
                         template_response = f"Разбрано. Регистрирах отсъствие за всички сесии на {d['date']} за {player}. Треньорите са уведомени. Мога ли да помогна с още нещо?"
                    elif d['session_id']:
                         template_response = f"Разбрано. Регистрирах отсъствие за {player} за тренировка {d['session_id']}. Треньорите са уведомени. Мога ли да помогна с още нещо?"
                    else:
                         template_response = f"Разбрано. Регистрирах отсъствие за {player} на {d['date']}. Треньорите са уведомени. Мога ли да помогна с още нещо?"
                else:
                    template_response = "Разбрано. Отсъствието е регистрирано. Треньорите са уведомени. Мога ли да помогна с още нещо?"
            
            LOGGER.info(
                f"Replaced AI response with template after report_absence. "
                f"Details: {details}, Template: {template_response}"
            )
            
            # Create a new AIMessage with template content
            new_message = AIMessage(
                content=template_response,
                additional_kwargs=last_message.additional_kwargs if hasattr(last_message, 'additional_kwargs') else {},
                response_metadata=last_message.response_metadata if hasattr(last_message, 'response_metadata') else {},
            )
            
            # Return state update with replaced message
            return {"messages": [new_message]}
        
        # Dynamic prompt middleware to inject user context
        @dynamic_prompt
        def context_aware_prompt(request: ModelRequest) -> str:
            """Inject user context into system prompt."""
            base = self.system_prompt or ""
            
            # Add context from runtime if available
            if hasattr(request.runtime, 'context') and request.runtime.context:
                ctx = request.runtime.context
                context_parts = []
                
                if hasattr(ctx, 'current_date'):
                    context_parts.append(f"Current date: {ctx.current_date}")
                if hasattr(ctx, 'telegram_id'):
                    context_parts.append(f"User Telegram ID: {ctx.telegram_id}")
                if hasattr(ctx, 'role'):
                    context_parts.append(f"User role: {ctx.role}")
                
                # Include player names mapped to IDs to avoid confusion
                if hasattr(ctx, 'player_names') and ctx.player_names:
                    # player_names should be a dict like {"Стела Величкова": 6, "Далия Величкова": 7}
                    player_list = [f"{name} (ID: {pid})" for name, pid in ctx.player_names.items()]
                    context_parts.append(f"Players: {', '.join(player_list)}")
                elif hasattr(ctx, 'player_ids') and ctx.player_ids:
                    # Fallback if player_names not available
                    context_parts.append(f"Player IDs: {ctx.player_ids}")
                
                if context_parts:
                    base += "\n\nUser Context:\n" + "\n".join(context_parts)
            
            # Trim conversation if too long
            message_count = len(request.messages)
            if message_count > 10:
                base += "\n\nNote: This is a long conversation - keep responses concise."

            # Truncate restored messages to the most recent ones to limit prompt size.
            # This prevents very long persisted histories from being sent as full context
            # to the model on every invocation (which can cause huge prompt token usage).
            MAX_MESSAGES = 12
            if hasattr(request, "messages") and isinstance(request.messages, list):
                if len(request.messages) > MAX_MESSAGES:
                    # Attempt to obtain a thread id for logging; fall back to None
                    thread_id = None
                    try:
                        cfg = getattr(request, "runtime", None)
                        if cfg is not None:
                            # runtime may expose configurable dict or attributes
                            thread_id = getattr(cfg, "configurable", None)
                            if isinstance(thread_id, dict):
                                thread_id = thread_id.get("thread_id")
                    except Exception:
                        thread_id = None

                    LOGGER.debug(
                        "Truncating restored messages for thread=%s: %d -> %d",
                        thread_id,
                        len(request.messages),
                        MAX_MESSAGES,
                    )
                    # Keep only the last MAX_MESSAGES entries
                    request.messages = request.messages[-MAX_MESSAGES:]
                    
                    # Ensure we don't start with a ToolMessage (orphaned from its AIMessage)
                    while request.messages and isinstance(request.messages[0], ToolMessage):
                        request.messages.pop(0)

                # If the conversation is much longer, kick off a background summarization
                # task that will persist a single-line summary into Redis for audit/compact
                # storage. We do this asynchronously so we don't block the request path.
                SUMMARY_TRIGGER = 40
                if len(request.messages) > SUMMARY_TRIGGER:
                    # Build a short heuristic summary from recent user messages
                    try:
                        snippets = []
                        # collect last few user/assistant message snippets
                        for m in request.messages[-12:]:
                            try:
                                if isinstance(m, dict):
                                    role = m.get("role") or m.get("type")
                                    content = m.get("content", "")
                                else:
                                    role = getattr(m, "role", None) or getattr(m, "type", None)
                                    content = getattr(m, "content", "")
                            except Exception:
                                role = None
                                content = ""

                            if role and role == "user":
                                # take a short prefix
                                snippets.append(content.strip().replace("\n", " ")[:120])

                        if not snippets:
                            # fallback: take assistant snippets
                            for m in request.messages[-12:]:
                                try:
                                    if isinstance(m, dict):
                                        role = m.get("role") or m.get("type")
                                        content = m.get("content", "")
                                    else:
                                        role = getattr(m, "role", None) or getattr(m, "type", None)
                                        content = getattr(m, "content", "")
                                except Exception:
                                    role = None
                                    content = ""
                                if role and role == "assistant":
                                    snippets.append(content.strip().replace("\n", " ")[:120])

                        summary_line = " | ".join(snippets[:6])
                        if not summary_line:
                            summary_line = "(no significant recent user messages)"

                        # Best-effort: extract thread id for namespacing
                        thread_id = None
                        try:
                            cfg = getattr(request, "runtime", None)
                            if cfg is not None:
                                thread_cfg = getattr(cfg, "configurable", None)
                                if isinstance(thread_cfg, dict):
                                    thread_id = thread_cfg.get("thread_id")
                        except Exception:
                            thread_id = None

                        # Persist summary in Redis in background
                        try:
                            asyncio.create_task(self._persist_summary(thread_id or "unknown", summary_line))
                        except Exception:
                            LOGGER.debug("Could not schedule summary persistence task for thread=%s", thread_id)
                    except Exception:
                        LOGGER.exception("Error while preparing summary snippet")
            
            return base
        
        # Create the agent with modern v1 API (already compiled with checkpointer)
        # Note: Middleware execution order:
        # 1. context_aware_prompt (before model) - Inject user context
        # 2. replace_tool_response_with_template (after model) - Replace with template
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            middleware=[
                context_aware_prompt,  # Inject context before model call
                replace_tool_response_with_template,  # Replace response with template after tool execution
            ],
            context_schema=AgentContext,
            checkpointer=self._checkpointer,  # Pass checkpointer to create_agent
        )
        
        LOGGER.info("LangChain v1 agent initialized with checkpointer")

    async def arun(
        self,
        *,
        session_id: str,
        user_context: Dict[str, Any],
        message: str,
        is_confirmation: bool = False,
    ) -> Dict[str, Any]:
        """Run the agent with a user message.
        
        Args:
            session_id: Unique conversation identifier (thread_id)
            user_context: User-specific context (date, role, player IDs, etc.)
            message: User message text
            is_confirmation: Whether the message is a confirmation for a pending tool
            
        Returns:
            Agent response with 'messages' key containing conversation, and an
            optional 'requires_confirmation' key if a tool needs user approval.
        """
        # Convert user_context dict to AgentContext dataclass
        context = AgentContext(
            current_date=user_context.get("current_date", ""),
            current_datetime=user_context.get("current_datetime", ""),
            telegram_id=user_context.get("telegram_id", 0),
            role=user_context.get("role"),
            player_ids=user_context.get("player_ids"),
            player_names=user_context.get("player_names"),  # New field for player name to ID mapping
            odoo_partner_id=user_context.get("odoo_partner_id"),
            odoo_user_id=user_context.get("odoo_user_id"),
        )
        
        # Set user context on tools (for RBAC and context-aware operations)
        for tool in self.tools:
            tool.set_user_context(user_context)
        
        try:
            # Ensure agent is initialized
            await self._initialize_agent()
            assert self.agent is not None, "Agent initialization failed"
            
            # Prepare agent invocation
            config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": self.max_iterations,
            }
            
            # If this is a confirmation, we don't need to add the user's message again
            payload = {"messages": []} if is_confirmation else {"messages": [{"role": "user", "content": message}]}

            # Stream agent steps to intercept tool calls
            async for chunk in self.agent.astream(payload, config=config, context=context):
                # Look for the 'agent' step which contains tool calls
                if "agent" in chunk:
                    agent_step = chunk["agent"]
                    if agent_step and agent_step.tool_calls:
                        for tool_call in agent_step.tool_calls:
                            tool_name = tool_call.get("name")
                            tool = next((t for t in self.tools if t.name == tool_name), None)
                            
                            # Check if the tool requires confirmation
                            if tool and getattr(tool, "requires_confirmation", False):
                                LOGGER.info(
                                    "Tool '%s' requires confirmation. Pausing execution for session %s.",
                                    tool_name, session_id
                                )
                                # Return a special response to the caller indicating confirmation is needed
                                return {
                                    "messages": chunk["agent"].messages,
                                    "requires_confirmation": True,
                                    "confirmation_prompt": f"Потвърждавате ли извършването на това действие: '{tool.description}'?",
                                }
            
            # If no tool required confirmation, get the final state
            final_state = await self.agent.aget_state(config)
            
            LOGGER.debug(
                "Agent invocation complete for session=%s, message_count=%d",
                session_id, len(final_state.values.get("messages", []))
            )
            
            return final_state.values
            
        except Exception as e:
            # Check if this is the corrupted checkpoint error
            error_msg = str(e)
            if "tool_calls" in error_msg and "tool_call_id" in error_msg:
                LOGGER.warning(
                    "Detected corrupted checkpoint for session=%s (incomplete tool_calls). Clearing history and retrying.",
                    session_id
                )
                # Clear the corrupted checkpoint
                await self.aclear_history(session_id)
                
                # Retry the invocation with fresh history
                # This is a simplified retry; a more robust implementation might use a different strategy
                return await self.arun(
                    session_id=session_id,
                    user_context=user_context,
                    message=message,
                    is_confirmation=is_confirmation,
                )
            
            # Re-raise other errors
            raise
            
        finally:
            # Clear tool context
            for tool in self.tools:
                tool.clear_user_context()

    async def aclear_history(self, session_id: str) -> None:
        """Clear conversation history for a session.
        
        Args:
            session_id: Thread ID to clear
        """
        # Ensure agent is initialized (which initializes checkpointer)
        await self._initialize_agent()
        
        # Get all checkpoints for this thread
        config = {"configurable": {"thread_id": session_id}}
        
        # Delete checkpoints by iterating and removing
        # Note: AsyncRedisSaver doesn't have a direct clear method,
        # so we need to manually delete the Redis keys
        import redis.asyncio as aioredis
        
        redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
        try:
            # Redis key pattern for LangGraph checkpoints
            pattern = f"checkpoint:{session_id}:*"
            keys = await redis_client.keys(pattern)
            if keys:
                await redis_client.delete(*keys)
                LOGGER.info("Cleared %d checkpoint keys for session=%s", len(keys), session_id)
        finally:
            await redis_client.close()

    async def _persist_summary(self, session_id: str, summary: str) -> None:
        """Persist a one-line summary for a session into Redis.

        This is a best-effort audit/compact storage to avoid keeping large
        conversational context in the live model prompt. We store the summary
        under `checkpoint_summary:{session_id}` with the configured TTL.
        """
        try:
            import redis.asyncio as aioredis

            redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
            key = f"checkpoint_summary:{session_id}"
            await redis_client.set(key, summary)
            if getattr(self, "session_ttl", None):
                try:
                    await redis_client.expire(key, int(self.session_ttl))
                except Exception:
                    # ignore expire errors
                    pass
            await redis_client.close()
            LOGGER.info("Persisted summary for session=%s (key=%s)", session_id, key)
        except Exception as e:
            LOGGER.warning("Failed to persist summary for session=%s: %s", session_id, e)

    async def cleanup(self) -> None:
        """Cleanup resources (close Redis connections)."""
        if self._checkpointer is not None:
            # Exit the context manager properly
            try:
                await self._checkpointer.__aexit__(None, None, None)
                LOGGER.info("Cleaned up AsyncRedisSaver resources")
            except Exception as e:
                LOGGER.warning("Error cleaning up checkpointer: %s", e)
            finally:
                self._checkpointer = None

