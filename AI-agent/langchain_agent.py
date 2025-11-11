"""LangChain agent wiring for the Telegram PoC.

This module configures a LangChain agent with MCP tools and Redis-backed message history.
When LangSmith environment variables are set (LANGSMITH_TRACING, LANGSMITH_API_KEY, etc.),
all agent invocations are automatically traced to LangSmith for observability.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from langchain_community.chat_message_histories import RedisChatMessageHistory

from mcp_tools import MCPTool

LOGGER = logging.getLogger(__name__)


class LangChainTelegramAgent:
    """Wraps LangChain components needed by the FastAPI app."""

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
    ) -> None:
        self.tools = list(tools)
        self.redis_url = redis_url
        self.session_ttl = session_ttl
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt
                    or "You are an assistant helping tennis academy members. Use tools when needed."
                    " Always respect the provided context.",
                ),
                MessagesPlaceholder(variable_name="chat_history"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
                (
                    "human",
                    "Context: {context}\nMessage: {input}",
                ),
            ]
        )
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
        )
        self.agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=False,
            handle_parsing_errors=True,
        )
        self._history_runnable = RunnableWithMessageHistory(
            self.executor,
            self._message_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="output",
        )

    def _message_history(self, session_id: str) -> RedisChatMessageHistory:
        return RedisChatMessageHistory(
            session_id=session_id,
            url=self.redis_url,
            ttl=self.session_ttl,
        )

    async def arun(
        self,
        *,
        session_id: str,
        user_context: Dict[str, Any],
        message: str,
    ) -> Dict[str, Any]:
        for tool in self.tools:
            tool.set_user_context(user_context)
        context_dump = self._format_context(user_context)
        try:
            result = await self._history_runnable.ainvoke(
                {"input": message, "context": context_dump},
                config={"configurable": {"session_id": session_id}},
            )
        finally:
            for tool in self.tools:
                tool.clear_user_context()
        return result

    async def aclear_history(self, session_id: str) -> None:
        history = self._message_history(session_id)
        await history.clear()

    def _format_context(self, context: Dict[str, Any]) -> str:
        safe_items = {k: v for k, v in context.items() if v is not None}
        pieces = [f"{key}: {value}" for key, value in safe_items.items()]
        return "\n".join(pieces)
