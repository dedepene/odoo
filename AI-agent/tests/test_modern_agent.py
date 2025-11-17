"""Tests for the modernized LangChain v1 agent implementation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_agent import LangChainTelegramAgent, AgentContext


@pytest.fixture
def mock_tools():
    """Create mock MCP tools."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.set_user_context = MagicMock()
    tool.clear_user_context = MagicMock()
    return [tool]


@pytest.fixture
def agent_config():
    """Basic agent configuration."""
    return {
        "redis_url": "redis://localhost:6379/1",
        "session_ttl": 86400,
        "model": "gpt-4o-mini",
        "api_key": "test-key",
        "temperature": 0.0,
    }


@pytest.fixture
def user_context():
    """Sample user context."""
    return {
        "current_date": "2024-11-15",
        "current_datetime": "2024-11-15T10:30:00",
        "telegram_id": 12345,
        "role": "parent",
        "player_ids": [100, 101],
        "odoo_partner_id": 50,
        "odoo_user_id": 25,
    }


class TestAgentInitialization:
    """Test agent initialization with modern API."""

    def test_basic_initialization(self, mock_tools, agent_config):
        """Test agent creates successfully."""
        agent = LangChainTelegramAgent(tools=mock_tools, **agent_config)
        
        assert agent is not None
        assert len(agent.tools) == 1
        assert agent.model_name == "gpt-4o-mini"
        assert agent.max_iterations == 25

    def test_custom_system_prompt(self, mock_tools, agent_config):
        """Test custom prompt override."""
        custom = "Custom assistant"
        agent = LangChainTelegramAgent(
            tools=mock_tools, system_prompt=custom, **agent_config
        )
        assert agent.system_prompt == custom


class TestAgentContext:
    """Test AgentContext dataclass."""

    def test_context_creation(self, user_context):
        """Test context dataclass construction."""
        ctx = AgentContext(
            current_date=user_context["current_date"],
            current_datetime=user_context["current_datetime"],
            telegram_id=user_context["telegram_id"],
            role=user_context["role"],
            player_ids=user_context["player_ids"],
            odoo_partner_id=user_context["odoo_partner_id"],
            odoo_user_id=user_context["odoo_user_id"],
        )
        
        assert ctx.telegram_id == 12345
        assert ctx.role == "parent"
        assert ctx.player_ids == [100, 101]


class TestAgentExecution:
    """Test agent execution."""

    @pytest.mark.asyncio
    async def test_tool_context_set_and_cleared(
        self, mock_tools, agent_config, user_context
    ):
        """Test tool context lifecycle."""
        with patch('langchain_agent.AsyncRedisSaver'):
            agent = LangChainTelegramAgent(tools=mock_tools, **agent_config)
            
            mock_result = {"messages": [{"role": "assistant", "content": "Hi"}]}
            
            with patch.object(agent.agent, 'compile') as mock_compile:
                mock_compiled = AsyncMock()
                mock_compiled.ainvoke = AsyncMock(return_value=mock_result)
                mock_compile.return_value = mock_compiled
                
                await agent.arun(
                    session_id="test",
                    user_context=user_context,
                    message="Hello"
                )
                
                # Verify context was set and cleared
                mock_tools[0].set_user_context.assert_called_once_with(user_context)
                mock_tools[0].clear_user_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_cleared_on_error(
        self, mock_tools, agent_config, user_context
    ):
        """Test context cleanup on failure."""
        with patch('langchain_agent.AsyncRedisSaver'):
            agent = LangChainTelegramAgent(tools=mock_tools, **agent_config)
            
            with patch.object(agent.agent, 'compile') as mock_compile:
                mock_compiled = AsyncMock()
                mock_compiled.ainvoke = AsyncMock(side_effect=Exception("Error"))
                mock_compile.return_value = mock_compiled
                
                with pytest.raises(Exception):
                    await agent.arun(
                        session_id="test",
                        user_context=user_context,
                        message="Hello"
                    )
                
                # Context still cleared despite error
                mock_tools[0].clear_user_context.assert_called_once()


class TestMemoryManagement:
    """Test conversation memory."""

    @pytest.mark.asyncio
    async def test_multiple_turns_same_session(
        self, mock_tools, agent_config, user_context
    ):
        """Test session persistence."""
        with patch('langchain_agent.AsyncRedisSaver'):
            agent = LangChainTelegramAgent(tools=mock_tools, **agent_config)
            
            with patch.object(agent.agent, 'compile') as mock_compile:
                mock_compiled = AsyncMock()
                mock_compiled.ainvoke = AsyncMock(return_value={
                    "messages": [{"role": "assistant", "content": "Reply"}]
                })
                mock_compile.return_value = mock_compiled
                
                # Two turns
                await agent.arun(
                    session_id="session1",
                    user_context=user_context,
                    message="Turn 1"
                )
                await agent.arun(
                    session_id="session1",
                    user_context=user_context,
                    message="Turn 2"
                )
                
                # Same thread_id used
                calls = mock_compiled.ainvoke.call_args_list
                assert len(calls) == 2
                assert calls[0][1]["config"]["configurable"]["thread_id"] == "session1"
                assert calls[1][1]["config"]["configurable"]["thread_id"] == "session1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
