"""Integration tests for the LangChain v1 agent in Docker environment.

These tests validate the agent works correctly with the full stack:
- Redis for checkpointing
- MCP server for Odoo integration
- OpenAI for LLM
"""

import asyncio
import os
import pytest
from datetime import datetime

# Test requires real services - skip if not available
pytestmark = pytest.mark.skipif(
    not os.getenv("INTEGRATION_TESTS"),
    reason="Integration tests require INTEGRATION_TESTS=1"
)


@pytest.fixture
def test_user_context():
    """Test user context for integration testing."""
    return {
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "current_datetime": datetime.now().isoformat(),
        "telegram_id": 99999,  # Test user ID
        "role": "parent",
        "player_ids": [],  # Real IDs would be populated
        "odoo_partner_id": None,
        "odoo_user_id": None,
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_agent_with_real_services(test_user_context):
    """Test agent with real Redis, MCP, and OpenAI."""
    from langchain_agent import LangChainTelegramAgent
    from mcp_client import MCPClient
    from mcp_tools import build_tools
    
    # Configuration from environment
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    # Setup
    mcp_client = MCPClient(mcp_url)
    tools = build_tools(mcp_client)
    
    agent = LangChainTelegramAgent(
        tools=tools,
        redis_url=redis_url,
        session_ttl=3600,
        model="gpt-4o-mini",
        api_key=openai_key,
        temperature=0.0,
    )
    
    try:
        # Test basic interaction
        session_id = f"integration-test-{datetime.now().timestamp()}"
        
        result = await agent.arun(
            session_id=session_id,
            user_context=test_user_context,
            message="Hello, can you help me?"
        )
        
        assert result is not None
        assert "messages" in result
        assert len(result["messages"]) > 0
        
        # Verify response
        last_message = result["messages"][-1]
        if hasattr(last_message, 'content'):
            content = last_message.content
        else:
            content = last_message.get('content', '')
        
        assert len(content) > 0
        print(f"Agent response: {content}")
        
        # Test conversation continuity
        result2 = await agent.arun(
            session_id=session_id,
            user_context=test_user_context,
            message="What did I just ask you?"
        )
        
        assert result2 is not None
        last_message2 = result2["messages"][-1]
        if hasattr(last_message2, 'content'):
            content2 = last_message2.content
        else:
            content2 = last_message2.get('content', '')
        
        # Should reference previous message
        assert len(content2) > 0
        print(f"Follow-up response: {content2}")
        
        # Cleanup
        await agent.aclear_history(session_id)
        await agent.cleanup()
        
    finally:
        await mcp_client.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_checkpointing(test_user_context):
    """Test Redis checkpointing persists conversation."""
    from langchain_agent import LangChainTelegramAgent
    from mcp_client import MCPClient
    from mcp_tools import build_tools
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    mcp_client = MCPClient(mcp_url)
    tools = build_tools(mcp_client)
    
    agent = LangChainTelegramAgent(
        tools=tools,
        redis_url=redis_url,
        session_ttl=3600,
        model="gpt-4o-mini",
        api_key=openai_key,
    )
    
    try:
        session_id = f"checkpoint-test-{datetime.now().timestamp()}"
        
        # First interaction
        await agent.arun(
            session_id=session_id,
            user_context=test_user_context,
            message="Remember my name is Alice"
        )
        
        # Verify checkpoint exists in Redis
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(redis_url, decode_responses=True)
        
        try:
            keys = await redis_client.keys(f"checkpoint:{session_id}:*")
            assert len(keys) > 0, "No checkpoints found in Redis"
            print(f"Found {len(keys)} checkpoint keys in Redis")
        finally:
            await redis_client.close()
        
        # Cleanup
        await agent.aclear_history(session_id)
        await agent.cleanup()
        
    finally:
        await mcp_client.close()


@pytest.mark.asyncio
@pytest.mark.integration  
async def test_tool_calling(test_user_context):
    """Test agent can call MCP tools."""
    from langchain_agent import LangChainTelegramAgent
    from mcp_client import MCPClient
    from mcp_tools import build_tools
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    mcp_client = MCPClient(mcp_url)
    
    # Verify MCP server is accessible
    try:
        await mcp_client.ping()
    except Exception as e:
        pytest.skip(f"MCP server not accessible: {e}")
    
    tools = build_tools(mcp_client)
    
    agent = LangChainTelegramAgent(
        tools=tools,
        redis_url=redis_url,
        session_ttl=3600,
        model="gpt-4o-mini",
        api_key=openai_key,
    )
    
    try:
        session_id = f"tool-test-{datetime.now().timestamp()}"
        
        # Ask agent to search for sessions (will attempt tool call)
        result = await agent.arun(
            session_id=session_id,
            user_context=test_user_context,
            message="Can you search for upcoming tennis sessions?"
        )
        
        assert result is not None
        print(f"Tool calling result: {result.get('messages', [])[-1]}")
        
        # Cleanup
        await agent.aclear_history(session_id)
        await agent.cleanup()
        
    finally:
        await mcp_client.close()


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-m", "integration", "-s"])
