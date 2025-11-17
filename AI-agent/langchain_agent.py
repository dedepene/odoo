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
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, TYPE_CHECKING

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

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
        
        default_system_prompt = """You help parents of the tennis academy.

- When a parent reports an absence, call report_absence with the player name from that message plus the date or session_id.
- If the tool replies with a list of sessions, forward it to the parent and wait for a yes/no answer.
- On a positive reply, call report_absence again with confirm_all=True; on a negative reply, answer "Нищо не записах. Има ли нещо друго?".
- Speak in the parent's language, keep answers short, and stop once the tool confirms success."""

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
        
        # Dynamic prompt middleware to inject user context
        @dynamic_prompt
        def context_aware_prompt(request: ModelRequest) -> str:
            """Inject user context into system prompt."""
            base = self.system_prompt
            
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
                if hasattr(ctx, 'player_ids') and ctx.player_ids:
                    context_parts.append(f"Player IDs: {ctx.player_ids}")
                
                if context_parts:
                    base += "\n\nUser Context:\n" + "\n".join(context_parts)
            
            # Trim conversation if too long
            message_count = len(request.messages)
            if message_count > 10:
                base += "\n\nNote: This is a long conversation - keep responses concise."
            
            return base
        
        # Create the agent with modern v1 API (already compiled with checkpointer)
        # Note: dynamic_prompt middleware goes in middleware=[], not system_prompt=
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            middleware=[context_aware_prompt],  # Dynamic prompt as middleware
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
    ) -> Dict[str, Any]:
        """Run the agent with a user message.
        
        Args:
            session_id: Unique conversation identifier (thread_id)
            user_context: User-specific context (date, role, player IDs, etc.)
            message: User message text
            
        Returns:
            Agent response with 'messages' key containing conversation
        """
        # Convert user_context dict to AgentContext dataclass
        context = AgentContext(
            current_date=user_context.get("current_date", ""),
            current_datetime=user_context.get("current_datetime", ""),
            telegram_id=user_context.get("telegram_id", 0),
            role=user_context.get("role"),
            player_ids=user_context.get("player_ids"),
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
            
            # Invoke agent with message and context (agent is already compiled with checkpointer)
            result = await self.agent.ainvoke(
                {
                    "messages": [
                        {"role": "user", "content": message}
                    ]
                },
                config={
                    "configurable": {
                        "thread_id": session_id,
                    },
                    "recursion_limit": self.max_iterations,
                },
                context=context,
            )
            
            LOGGER.debug(
                "Agent invocation complete for session=%s, message_count=%d",
                session_id, len(result.get("messages", []))
            )
            
            return result
            
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
                result = await self.agent.ainvoke(
                    {
                        "messages": [
                            {"role": "user", "content": message}
                        ]
                    },
                    config={
                        "configurable": {
                            "thread_id": session_id,
                        },
                        "recursion_limit": self.max_iterations,
                    },
                    context=context,
                )
                
                LOGGER.info("Successfully recovered from corrupted checkpoint for session=%s", session_id)
                return result
            
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

