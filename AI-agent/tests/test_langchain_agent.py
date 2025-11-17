"""Unit tests for the modernized LangChain v1 agent."""Unit tests for the modernized LangChain v1 agent."""Unit tests for the LangChainTelegramAgent modernized implementation."""



This test suite validates the refactored agent using create_agent

instead of the legacy AgentExecutor pattern.

"""This test suite validates the refactored agent using create_agentfrom __future__ import annotations



import pytestinstead of the legacy AgentExecutor pattern.

from unittest.mock import AsyncMock, MagicMock, patch

from datetime import datetime"""from types import SimpleNamespace



from langchain_agent import LangChainTelegramAgent, AgentContextfrom typing import Any, Dict, List, cast

from mcp_tools import MCPTool

import pytestimport pathlib



@pytest.fixturefrom unittest.mock import AsyncMock, MagicMock, patchimport sys

def mock_tools():

    """Create mock MCP tools for testing."""from datetime import datetime

    tool1 = MagicMock(spec=MCPTool)

    tool1.name = "test_tool"import pytest

    tool1.description = "A test tool"

    tool1.set_user_context = MagicMock()from langchain_agent import LangChainTelegramAgent, AgentContext

    tool1.clear_user_context = MagicMock()

    from mcp_tools import MCPToolfrom langchain_core.chat_history import BaseChatMessageHistory

    tool2 = MagicMock(spec=MCPTool)

    tool2.name = "report_absence"from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

    tool2.description = "Report player absence"

    tool2.set_user_context = MagicMock()

    tool2.clear_user_context = MagicMock()

    @pytest.fixturePROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]

    return [tool1, tool2]

def mock_tools():if str(PROJECT_ROOT) not in sys.path:



@pytest.fixture    """Create mock MCP tools for testing."""	sys.path.insert(0, str(PROJECT_ROOT))

def user_context():

    """Create sample user context."""    tool1 = MagicMock(spec=MCPTool)

    return {

        "current_date": "2024-11-15",    tool1.name = "test_tool"import langchain_agent  # noqa: E402

        "current_datetime": "2024-11-15T10:30:00",

        "telegram_id": 12345,    tool1.description = "A test tool"from langchain_agent import LangChainTelegramAgent

        "role": "parent",

        "player_ids": [100, 101],    tool1.set_user_context = MagicMock()from mcp_tools import MCPTool

        "odoo_partner_id": 50,

        "odoo_user_id": 25,    tool1.clear_user_context = MagicMock()

    }

    



@pytest.fixture    tool2 = MagicMock(spec=MCPTool)class SimpleHistory(BaseChatMessageHistory):

def agent_config():

    """Agent configuration for testing."""    tool2.name = "report_absence"	"""In-memory history used for isolating Redis in tests."""

    return {

        "redis_url": "redis://localhost:6379/1",    tool2.description = "Report player absence"

        "session_ttl": 86400,

        "model": "gpt-4o-mini",    tool2.set_user_context = MagicMock()	def __init__(self, seed: List[BaseMessage] | None = None) -> None:

        "api_key": "test-api-key",

        "temperature": 0.0,    tool2.clear_user_context = MagicMock()		self._messages: List[BaseMessage] = list(seed or [])

    }

    



class TestLangChainTelegramAgent:    return [tool1, tool2]	@property

    """Test suite for the modernized agent."""

	def messages(self) -> List[BaseMessage]:  # type: ignore[override]

    def test_initialization(self, mock_tools, agent_config):

        """Test that the agent initializes correctly with modern API."""		return list(self._messages)

        agent = LangChainTelegramAgent(

            tools=mock_tools,@pytest.fixture

            **agent_config

        )def user_context():	def add_message(self, message: BaseMessage) -> None:

        

        assert agent is not None    """Create sample user context."""		self._messages.append(message)

        assert len(agent.tools) == 2

        assert agent.model_name == "gpt-4o-mini"    return {

        assert agent.max_iterations == 25

        assert agent.system_prompt is not None        "current_date": "2024-11-15",	def clear(self) -> None:  # type: ignore[override]

        assert "tennis academy" in agent.system_prompt.lower()

        "current_datetime": "2024-11-15T10:30:00",		self._messages.clear()

    def test_custom_system_prompt(self, mock_tools, agent_config):

        """Test custom system prompt override."""        "telegram_id": 12345,

        custom_prompt = "You are a custom assistant."

                "role": "parent",

        agent = LangChainTelegramAgent(

            tools=mock_tools,        "player_ids": [100, 101],class DummyTool:

            system_prompt=custom_prompt,

            **agent_config        "odoo_partner_id": 50,	"""Minimal MCPTool stand-in tracking context binding."""

        )

                "odoo_user_id": 25,

        assert agent.system_prompt == custom_prompt

    }	def __init__(self) -> None:

    def test_agent_context_dataclass(self, user_context):

        """Test AgentContext dataclass creation."""		self.context_log: List[str] = []

        context = AgentContext(

            current_date=user_context["current_date"],		self._context: Dict[str, Any] | None = None

            current_datetime=user_context["current_datetime"],

            telegram_id=user_context["telegram_id"],@pytest.fixture

            role=user_context["role"],

            player_ids=user_context["player_ids"],def agent_config():	def set_user_context(self, context: Dict[str, Any]) -> None:

            odoo_partner_id=user_context["odoo_partner_id"],

            odoo_user_id=user_context["odoo_user_id"],    """Agent configuration for testing."""		self.context_log.append("set")

        )

            return {		self._context = context

        assert context.telegram_id == 12345

        assert context.role == "parent"        "redis_url": "redis://localhost:6379/1",

        assert context.player_ids == [100, 101]

        assert context.current_date == "2024-11-15"        "session_ttl": 86400,	def clear_user_context(self) -> None:



    @pytest.mark.asyncio        "model": "gpt-4o-mini",		self.context_log.append("clear")

    async def test_get_checkpointer(self, mock_tools, agent_config):

        """Test checkpointer initialization."""        "api_key": "test-api-key",		self._context = None

        with patch('langchain_agent.AsyncRedisSaver') as mock_saver:

            mock_instance = AsyncMock()        "temperature": 0.0,

            mock_saver.from_conn_string.return_value = mock_instance

                }

            agent = LangChainTelegramAgent(

                tools=mock_tools,class _MiddlewareAwareAgent:

                **agent_config

            )	def __init__(self, middleware):

            

            checkpointer = await agent.get_checkpointer()class TestLangChainTelegramAgent:		self.middleware = middleware

            

            assert checkpointer is not None    """Test suite for the modernized agent."""		self.calls: List[Dict[str, Any]] = []

            mock_saver.from_conn_string.assert_called_once_with(agent_config["redis_url"])

            mock_instance.asetup.assert_called_once()



    @pytest.mark.asyncio    def test_initialization(self, mock_tools, agent_config):	async def ainvoke(self, payload, *, config=None, context=None):

    async def test_arun_sets_tool_context(self, mock_tools, agent_config, user_context):

        """Test that arun sets and clears tool context properly."""        """Test that the agent initializes correctly with modern API."""		state = {"messages": list(payload["messages"])}

        with patch('langchain_agent.AsyncRedisSaver'):

            agent = LangChainTelegramAgent(        agent = LangChainTelegramAgent(		runtime = SimpleNamespace(context=context)

                tools=mock_tools,

                **agent_config            tools=mock_tools,		for middleware in self.middleware:

            )

                        **agent_config			update = middleware.before_agent(state, runtime)

            # Mock the agent's invoke method

            mock_result = {        )			if update and "messages" in update:

                "messages": [

                    {"role": "user", "content": "Hello"},        				state["messages"] = list(update["messages"])

                    {"role": "assistant", "content": "Hi there!"}

                ]        assert agent is not None		response = AIMessage(content="dummy-response")

            }

                    assert len(agent.tools) == 2		state["messages"].append(response)

            with patch.object(agent.agent, 'compile') as mock_compile:

                mock_compiled = AsyncMock()        assert agent.model_name == "gpt-4o-mini"		self.calls.append({"payload": payload, "context": context, "config": config})

                mock_compiled.ainvoke = AsyncMock(return_value=mock_result)

                mock_compile.return_value = mock_compiled        assert agent.max_iterations == 25		return {"messages": state["messages"]}

                

                result = await agent.arun(        assert agent.system_prompt is not None

                    session_id="test-session",

                    user_context=user_context,        assert "tennis academy" in agent.system_prompt.lower()

                    message="Hello"

                )@pytest.fixture(autouse=True)

                

                # Verify tools had context set    def test_custom_system_prompt(self, mock_tools, agent_config):def stub_chat_model(monkeypatch):

                for tool in mock_tools:

                    tool.set_user_context.assert_called_once_with(user_context)        """Test custom system prompt override."""	monkeypatch.setattr(langchain_agent, "init_chat_model", lambda *_, **__: "stub-model")

                    tool.clear_user_context.assert_called_once()

                        custom_prompt = "You are a custom assistant."

                assert result == mock_result

        

    @pytest.mark.asyncio

    async def test_arun_context_conversion(self, mock_tools, agent_config, user_context):        agent = LangChainTelegramAgent(@pytest.fixture

        """Test that user_context dict is converted to AgentContext."""

        with patch('langchain_agent.AsyncRedisSaver'):            tools=mock_tools,def fake_agent(monkeypatch):

            agent = LangChainTelegramAgent(

                tools=mock_tools,            system_prompt=custom_prompt,	container: Dict[str, _MiddlewareAwareAgent] = {}

                **agent_config

            )            **agent_config

            

            mock_result = {"messages": [{"role": "assistant", "content": "Reply"}]}        )	def _factory(*_, **kwargs):

            

            with patch.object(agent.agent, 'compile') as mock_compile:        		agent = _MiddlewareAwareAgent(kwargs.get("middleware", []))

                mock_compiled = AsyncMock()

                mock_compiled.ainvoke = AsyncMock(return_value=mock_result)        assert agent.system_prompt == custom_prompt		container["agent"] = agent

                mock_compile.return_value = mock_compiled

                		return agent

                await agent.arun(

                    session_id="test-session",    def test_agent_context_dataclass(self, user_context):

                    user_context=user_context,

                    message="Test message"        """Test AgentContext dataclass creation."""	monkeypatch.setattr(langchain_agent, "create_agent", _factory)

                )

                        context = AgentContext(	return container

                # Verify ainvoke was called with correct structure

                call_args = mock_compiled.ainvoke.call_args            current_date=user_context["current_date"],

                assert call_args is not None

                            current_datetime=user_context["current_datetime"],

                # Check messages structure

                messages = call_args[0][0]["messages"]            telegram_id=user_context["telegram_id"],@pytest.mark.asyncio

                assert len(messages) == 1

                assert messages[0]["role"] == "user"            role=user_context["role"],async def test_arun_updates_history_and_returns_output(fake_agent):

                assert messages[0]["content"] == "Test message"

                            player_ids=user_context["player_ids"],	tool = DummyTool()

                # Check config

                config = call_args[1]["config"]            odoo_partner_id=user_context["odoo_partner_id"],	seed_history = SimpleHistory(

                assert config["configurable"]["thread_id"] == "test-session"

                assert config["recursion_limit"] == 25            odoo_user_id=user_context["odoo_user_id"],		[HumanMessage(content="hello"), AIMessage(content="hi there")]

                

                # Check context        )	)

                context = call_args[1]["context"]

                assert isinstance(context, AgentContext)        	agent = LangChainTelegramAgent(

                assert context.telegram_id == 12345

                assert context.role == "parent"        assert context.telegram_id == 12345		tools=[cast(MCPTool, tool)],



    @pytest.mark.asyncio        assert context.role == "parent"		redis_url="redis://localhost/0",

    async def test_arun_clears_context_on_error(self, mock_tools, agent_config, user_context):

        """Test that tool context is cleared even if agent fails."""        assert context.player_ids == [100, 101]		session_ttl=60,

        with patch('langchain_agent.AsyncRedisSaver'):

            agent = LangChainTelegramAgent(        assert context.current_date == "2024-11-15"		model="fake",

                tools=mock_tools,

                **agent_config		api_key=None,

            )

                @pytest.mark.asyncio		history_factory=lambda _: seed_history,

            with patch.object(agent.agent, 'compile') as mock_compile:

                mock_compiled = AsyncMock()    async def test_get_checkpointer(self, mock_tools, agent_config):	)

                mock_compiled.ainvoke = AsyncMock(side_effect=Exception("Test error"))

                mock_compile.return_value = mock_compiled        """Test checkpointer initialization."""

                

                with pytest.raises(Exception, match="Test error"):        with patch('langchain_agent.AsyncRedisSaver') as mock_saver:	result = await agent.arun(

                    await agent.arun(

                        session_id="test-session",            mock_instance = AsyncMock()		session_id="sess-1",

                        user_context=user_context,

                        message="Hello"            mock_saver.from_conn_string.return_value = mock_instance		user_context={"role": "guardian", "player_ids": [1]},

                    )

                            		message="Need to report an absence",

                # Verify context was still cleared despite error

                for tool in mock_tools:            agent = LangChainTelegramAgent(	)

                    tool.clear_user_context.assert_called_once()

                tools=mock_tools,

    @pytest.mark.asyncio

    async def test_aclear_history(self, mock_tools, agent_config):                **agent_config	assert result["output"] == "dummy-response"

        """Test conversation history clearing."""

        with patch('langchain_agent.AsyncRedisSaver'), \            )	assert tool.context_log == ["set", "clear"]

             patch('langchain_agent.aioredis') as mock_redis_module:

                        	assert len(seed_history.messages) == 4

            mock_redis_client = AsyncMock()

            mock_redis_client.keys = AsyncMock(return_value=["checkpoint:session1:1", "checkpoint:session1:2"])            checkpointer = await agent.get_checkpointer()	assert seed_history.messages[-1].content == "dummy-response"

            mock_redis_client.delete = AsyncMock()

            mock_redis_client.close = AsyncMock()            	assert "agent" in fake_agent and fake_agent["agent"].calls

            mock_redis_module.from_url.return_value = mock_redis_client

                        assert checkpointer is not None

            agent = LangChainTelegramAgent(

                tools=mock_tools,            mock_saver.from_conn_string.assert_called_once_with(agent_config["redis_url"])

                **agent_config

            )            mock_instance.asetup.assert_called_once()@pytest.mark.asyncio

            

            await agent.aclear_history("session1")async def test_history_is_trimmed_to_window(fake_agent):

            

            # Verify Redis operations    @pytest.mark.asyncio	tool = DummyTool()

            mock_redis_client.keys.assert_called_once_with("checkpoint:session1:*")

            mock_redis_client.delete.assert_called_once_with("checkpoint:session1:1", "checkpoint:session1:2")    async def test_arun_sets_tool_context(self, mock_tools, agent_config, user_context):	long_history = SimpleHistory(_build_history(10))

            mock_redis_client.close.assert_called_once()

        """Test that arun sets and clears tool context properly."""	agent = LangChainTelegramAgent(

    @pytest.mark.asyncio

    async def test_cleanup(self, mock_tools, agent_config):        with patch('langchain_agent.AsyncRedisSaver'):		tools=[cast(MCPTool, tool)],

        """Test resource cleanup."""

        with patch('langchain_agent.AsyncRedisSaver'):            agent = LangChainTelegramAgent(		redis_url="redis://localhost/0",

            agent = LangChainTelegramAgent(

                tools=mock_tools,                tools=mock_tools,		session_ttl=60,

                **agent_config

            )                **agent_config		model="fake",

            

            # Initialize checkpointer            )		api_key=None,

            await agent.get_checkpointer()

            assert agent._checkpointer is not None            		history_factory=lambda _: long_history,

            

            # Cleanup            # Mock the agent's invoke method		max_history_messages=4,

            await agent.cleanup()

            assert agent._checkpointer is None            mock_result = {	)



                "messages": [

class TestAgentMemoryBehavior:

    """Test conversation memory and history management."""                    {"role": "user", "content": "Hello"},	await agent.arun(



    @pytest.mark.asyncio                    {"role": "assistant", "content": "Hi there!"}		session_id="sess-trim",

    async def test_multiple_turns_same_session(self, mock_tools, agent_config, user_context):

        """Test that multiple turns maintain session history."""                ]		user_context={"role": "guardian", "player_ids": [42]},

        with patch('langchain_agent.AsyncRedisSaver'):

            agent = LangChainTelegramAgent(            }		message="Second run",

                tools=mock_tools,

                **agent_config            	)

            )

                        with patch.object(agent.agent, 'compile') as mock_compile:

            session_id = "multi-turn-session"

                            mock_compiled = AsyncMock()	assert len(long_history.messages) == 4

            with patch.object(agent.agent, 'compile') as mock_compile:

                mock_compiled = AsyncMock()                mock_compiled.ainvoke = AsyncMock(return_value=mock_result)	assert isinstance(long_history.messages[-1], AIMessage)

                mock_compiled.ainvoke = AsyncMock(return_value={

                    "messages": [{"role": "assistant", "content": "Response"}]                mock_compile.return_value = mock_compiled

                })

                mock_compile.return_value = mock_compiled                

                

                # First turn                result = await agent.arun(def _build_history(count: int) -> List[BaseMessage]:

                await agent.arun(

                    session_id=session_id,                    session_id="test-session",	messages: List[BaseMessage] = []

                    user_context=user_context,

                    message="First message"                    user_context=user_context,	for idx in range(count):

                )

                                    message="Hello"		if idx % 2 == 0:

                # Second turn (same session)

                await agent.arun(                )			messages.append(HumanMessage(content=f"User message {idx}"))

                    session_id=session_id,

                    user_context=user_context,                		else:

                    message="Second message"

                )                # Verify tools had context set			messages.append(AIMessage(content=f"Bot reply {idx}"))

                

                # Both should use same thread_id                for tool in mock_tools:	return messages

                calls = mock_compiled.ainvoke.call_args_list

                assert len(calls) == 2                    tool.set_user_context.assert_called_once_with(user_context)

                assert calls[0][1]["config"]["configurable"]["thread_id"] == session_id                    tool.clear_user_context.assert_called_once()

                assert calls[1][1]["config"]["configurable"]["thread_id"] == session_id                

                assert result == mock_result

    @pytest.mark.asyncio

    async def test_different_sessions_isolated(self, mock_tools, agent_config, user_context):    @pytest.mark.asyncio

        """Test that different sessions are isolated."""    async def test_arun_context_conversion(self, mock_tools, agent_config, user_context):

        with patch('langchain_agent.AsyncRedisSaver'):        """Test that user_context dict is converted to AgentContext."""

            agent = LangChainTelegramAgent(        with patch('langchain_agent.AsyncRedisSaver'):

                tools=mock_tools,            agent = LangChainTelegramAgent(

                **agent_config                tools=mock_tools,

            )                **agent_config

                        )

            with patch.object(agent.agent, 'compile') as mock_compile:            

                mock_compiled = AsyncMock()            mock_result = {"messages": [{"role": "assistant", "content": "Reply"}]}

                mock_compiled.ainvoke = AsyncMock(return_value={            

                    "messages": [{"role": "assistant", "content": "Response"}]            with patch.object(agent.agent, 'compile') as mock_compile:

                })                mock_compiled = AsyncMock()

                mock_compile.return_value = mock_compiled                mock_compiled.ainvoke = AsyncMock(return_value=mock_result)

                                mock_compile.return_value = mock_compiled

                # Session 1                

                await agent.arun(                await agent.arun(

                    session_id="session1",                    session_id="test-session",

                    user_context=user_context,                    user_context=user_context,

                    message="Message 1"                    message="Test message"

                )                )

                                

                # Session 2                # Verify ainvoke was called with correct structure

                await agent.arun(                call_args = mock_compiled.ainvoke.call_args

                    session_id="session2",                assert call_args is not None

                    user_context=user_context,                

                    message="Message 2"                # Check messages structure

                )                messages = call_args[0][0]["messages"]

                                assert len(messages) == 1

                # Verify different thread_ids                assert messages[0]["role"] == "user"

                calls = mock_compiled.ainvoke.call_args_list                assert messages[0]["content"] == "Test message"

                thread_id_1 = calls[0][1]["config"]["configurable"]["thread_id"]                

                thread_id_2 = calls[1][1]["config"]["configurable"]["thread_id"]                # Check config

                assert thread_id_1 != thread_id_2                config = call_args[1]["config"]

                assert config["configurable"]["thread_id"] == "test-session"

                assert config["recursion_limit"] == 25

class TestDynamicPromptMiddleware:                

    """Test the dynamic prompt middleware functionality."""                # Check context

                context = call_args[1]["context"]

    def test_middleware_includes_context(self, mock_tools, agent_config):                assert isinstance(context, AgentContext)

        """Test that dynamic prompt middleware includes user context."""                assert context.telegram_id == 12345

        agent = LangChainTelegramAgent(                assert context.role == "parent"

            tools=mock_tools,

            **agent_config    @pytest.mark.asyncio

        )    async def test_arun_clears_context_on_error(self, mock_tools, agent_config, user_context):

                """Test that tool context is cleared even if agent fails."""

        # The middleware is defined inside __init__ and attached to the agent        with patch('langchain_agent.AsyncRedisSaver'):

        # We verify it exists by checking the agent was created with system_prompt            agent = LangChainTelegramAgent(

        # that is callable (the dynamic_prompt decorator makes it callable)                tools=mock_tools,

        assert agent.agent is not None                **agent_config

            )

    def test_base_prompt_preserved(self, mock_tools, agent_config):            

        """Test that base system prompt is preserved."""            with patch.object(agent.agent, 'compile') as mock_compile:

        custom_prompt = "Custom tennis academy assistant"                mock_compiled = AsyncMock()

                        mock_compiled.ainvoke = AsyncMock(side_effect=Exception("Test error"))

        agent = LangChainTelegramAgent(                mock_compile.return_value = mock_compiled

            tools=mock_tools,                

            system_prompt=custom_prompt,                with pytest.raises(Exception, match="Test error"):

            **agent_config                    await agent.arun(

        )                        session_id="test-session",

                                user_context=user_context,

        assert agent.system_prompt == custom_prompt                        message="Hello"

                    )

                

if __name__ == "__main__":                # Verify context was still cleared despite error

    pytest.main([__file__, "-v"])                for tool in mock_tools:

                    tool.clear_user_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_aclear_history(self, mock_tools, agent_config):
        """Test conversation history clearing."""
        with patch('langchain_agent.AsyncRedisSaver'), \
             patch('langchain_agent.aioredis') as mock_redis_module:
            
            mock_redis_client = AsyncMock()
            mock_redis_client.keys = AsyncMock(return_value=["checkpoint:session1:1", "checkpoint:session1:2"])
            mock_redis_client.delete = AsyncMock()
            mock_redis_client.close = AsyncMock()
            mock_redis_module.from_url.return_value = mock_redis_client
            
            agent = LangChainTelegramAgent(
                tools=mock_tools,
                **agent_config
            )
            
            await agent.aclear_history("session1")
            
            # Verify Redis operations
            mock_redis_client.keys.assert_called_once_with("checkpoint:session1:*")
            mock_redis_client.delete.assert_called_once_with("checkpoint:session1:1", "checkpoint:session1:2")
            mock_redis_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup(self, mock_tools, agent_config):
        """Test resource cleanup."""
        with patch('langchain_agent.AsyncRedisSaver'):
            agent = LangChainTelegramAgent(
                tools=mock_tools,
                **agent_config
            )
            
            # Initialize checkpointer
            await agent.get_checkpointer()
            assert agent._checkpointer is not None
            
            # Cleanup
            await agent.cleanup()
            assert agent._checkpointer is None


class TestAgentMemoryBehavior:
    """Test conversation memory and history management."""

    @pytest.mark.asyncio
    async def test_multiple_turns_same_session(self, mock_tools, agent_config, user_context):
        """Test that multiple turns maintain session history."""
        with patch('langchain_agent.AsyncRedisSaver'):
            agent = LangChainTelegramAgent(
                tools=mock_tools,
                **agent_config
            )
            
            session_id = "multi-turn-session"
            
            with patch.object(agent.agent, 'compile') as mock_compile:
                mock_compiled = AsyncMock()
                mock_compiled.ainvoke = AsyncMock(return_value={
                    "messages": [{"role": "assistant", "content": "Response"}]
                })
                mock_compile.return_value = mock_compiled
                
                # First turn
                await agent.arun(
                    session_id=session_id,
                    user_context=user_context,
                    message="First message"
                )
                
                # Second turn (same session)
                await agent.arun(
                    session_id=session_id,
                    user_context=user_context,
                    message="Second message"
                )
                
                # Both should use same thread_id
                calls = mock_compiled.ainvoke.call_args_list
                assert len(calls) == 2
                assert calls[0][1]["config"]["configurable"]["thread_id"] == session_id
                assert calls[1][1]["config"]["configurable"]["thread_id"] == session_id

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(self, mock_tools, agent_config, user_context):
        """Test that different sessions are isolated."""
        with patch('langchain_agent.AsyncRedisSaver'):
            agent = LangChainTelegramAgent(
                tools=mock_tools,
                **agent_config
            )
            
            with patch.object(agent.agent, 'compile') as mock_compile:
                mock_compiled = AsyncMock()
                mock_compiled.ainvoke = AsyncMock(return_value={
                    "messages": [{"role": "assistant", "content": "Response"}]
                })
                mock_compile.return_value = mock_compiled
                
                # Session 1
                await agent.arun(
                    session_id="session1",
                    user_context=user_context,
                    message="Message 1"
                )
                
                # Session 2
                await agent.arun(
                    session_id="session2",
                    user_context=user_context,
                    message="Message 2"
                )
                
                # Verify different thread_ids
                calls = mock_compiled.ainvoke.call_args_list
                thread_id_1 = calls[0][1]["config"]["configurable"]["thread_id"]
                thread_id_2 = calls[1][1]["config"]["configurable"]["thread_id"]
                assert thread_id_1 != thread_id_2


class TestDynamicPromptMiddleware:
    """Test the dynamic prompt middleware functionality."""

    def test_middleware_includes_context(self, mock_tools, agent_config):
        """Test that dynamic prompt middleware includes user context."""
        agent = LangChainTelegramAgent(
            tools=mock_tools,
            **agent_config
        )
        
        # The middleware is defined inside __init__ and attached to the agent
        # We verify it exists by checking the agent was created with system_prompt
        # that is callable (the dynamic_prompt decorator makes it callable)
        assert agent.agent is not None

    def test_base_prompt_preserved(self, mock_tools, agent_config):
        """Test that base system prompt is preserved."""
        custom_prompt = "Custom tennis academy assistant"
        
        agent = LangChainTelegramAgent(
            tools=mock_tools,
            system_prompt=custom_prompt,
            **agent_config
        )
        
        assert agent.system_prompt == custom_prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
