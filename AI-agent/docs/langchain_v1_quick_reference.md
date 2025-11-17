# LangChain V1 Quick Reference

## Quick Start

### Running Tests

```bash
# Unit tests (no external dependencies)
pytest AI-agent/tests/test_modern_agent.py -v

# Integration tests (requires Docker stack)
docker-compose -f AI-agent/docker-compose.poc.yml up -d
INTEGRATION_TESTS=1 pytest AI-agent/tests/test_integration.py -v -m integration
```

### Starting the Agent

```bash
cd AI-agent

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY=your-key
export REDIS_URL=redis://localhost:6379/0
export MCP_SERVER_URL=http://localhost:8000

# Run with Docker
docker-compose -f docker-compose.poc.yml up -d

# Check logs
docker-compose -f docker-compose.poc.yml logs -f langchain-agent
```

## API Comparison

### Agent Creation

**Legacy:**
```python
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([...])
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
```

**Modern (v1):**
```python
from langchain.agents import create_agent

agent = create_agent(
    model="gpt-4o-mini",
    tools=tools,
    system_prompt="You are a helpful assistant"
)
```

### Memory Management

**Legacy:**
```python
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import RedisChatMessageHistory

runnable = RunnableWithMessageHistory(
    executor,
    lambda sid: RedisChatMessageHistory(session_id=sid, url=redis_url),
    input_messages_key="input",
    history_messages_key="chat_history",
)
```

**Modern (v1):**
```python
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

checkpointer = AsyncRedisSaver.from_conn_string(redis_url)
await checkpointer.asetup()

agent_with_memory = agent.compile(checkpointer=checkpointer)
```

### Invocation

**Legacy:**
```python
result = await runnable.ainvoke(
    {"input": "Hello"},
    config={"configurable": {"session_id": "user123"}}
)
reply = result["output"]  # String
```

**Modern (v1):**
```python
result = await agent_with_memory.ainvoke(
    {"messages": [{"role": "user", "content": "Hello"}]},
    config={"configurable": {"thread_id": "user123"}}
)
reply = result["messages"][-1].content  # Message object
```

## Common Patterns

### Dynamic System Prompts

```python
from langchain.agents.middleware import dynamic_prompt, ModelRequest

@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    base = "You are a helpful assistant."
    
    # Access runtime context
    if hasattr(request.runtime, 'context'):
        user_role = request.runtime.context.role
        base += f"\nUser role: {user_role}"
    
    # Access conversation state
    message_count = len(request.messages)
    if message_count > 10:
        base += "\nKeep responses concise."
    
    return base

agent = create_agent(
    model="gpt-4o-mini",
    tools=tools,
    system_prompt=context_aware_prompt
)
```

### Context Schema

```python
from dataclasses import dataclass

@dataclass
class UserContext:
    user_id: str
    role: str
    preferences: dict

agent = create_agent(
    model="gpt-4o-mini",
    tools=tools,
    context_schema=UserContext
)

# Use in invocation
result = await agent.ainvoke(
    {"messages": [...]},
    context=UserContext(user_id="123", role="admin", preferences={})
)
```

### Message History Trimming

```python
# Automatic via SummarizationMiddleware
from langchain.agents.middleware import SummarizationMiddleware

agent = create_agent(
    model="gpt-4o-mini",
    tools=tools,
    middleware=[
        SummarizationMiddleware(
            model="gpt-4o-mini",
            max_tokens_before_summary=4000,
            messages_to_keep=20,
        )
    ]
)
```

## Debugging

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### LangSmith Tracing

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=your-key
export LANGSMITH_PROJECT=my-project
```

### Check Redis Checkpoints

```bash
# List all checkpoint keys
redis-cli KEYS "checkpoint:*"

# Get checkpoint details
redis-cli GET checkpoint:telegram:12345:1

# Delete old checkpoints
redis-cli DEL checkpoint:telegram:12345:*
```

### Inspect Agent State

```python
# Print full result structure
result = await agent.ainvoke(...)
print(f"Result keys: {result.keys()}")
print(f"Messages: {result['messages']}")

# Access intermediate steps (tool calls)
for message in result['messages']:
    print(f"Role: {message.role}, Content: {message.content}")
```

## Migration Checklist

- [ ] Update `requirements.txt` with LangChain v1 packages
- [ ] Replace `create_tool_calling_agent` with `create_agent`
- [ ] Replace `AgentExecutor` with direct agent compilation
- [ ] Update memory from `RunnableWithMessageHistory` to checkpointer
- [ ] Change invocation from `{"input": ...}` to `{"messages": [...]}`
- [ ] Update response extraction from `result["output"]` to `result["messages"]`
- [ ] Test basic conversation flow
- [ ] Test tool calling
- [ ] Test multi-turn conversations
- [ ] Test session isolation
- [ ] Verify LangSmith tracing works

## Key Differences

| Feature | Legacy | Modern (v1) |
|---------|--------|-------------|
| Agent Creation | `create_tool_calling_agent` + `AgentExecutor` | `create_agent` |
| Prompt | `ChatPromptTemplate` | `system_prompt` parameter |
| Memory | `RunnableWithMessageHistory` | `checkpointer` parameter |
| Invocation Input | `{"input": "..."}` | `{"messages": [...]}` |
| Invocation Output | `{"output": "..."}` | `{"messages": [...]}` |
| Context | String concatenation | Typed dataclass |
| Middleware | Not available | `@dynamic_prompt` decorator |
| Streaming | Limited | First-class support |

## Useful Commands

```bash
# Install/upgrade LangChain v1
pip install -U langchain langchain-openai langgraph langgraph-checkpoint-redis

# Run specific test
pytest AI-agent/tests/test_modern_agent.py::TestAgentInitialization::test_basic_initialization -v

# Check package versions
pip show langchain langchain-core langgraph

# Docker cleanup
docker-compose -f AI-agent/docker-compose.poc.yml down -v

# View agent logs
docker logs odoo-langchain-agent-1 --tail=100 -f

# Redis CLI in Docker
docker exec -it odoo-redis-1 redis-cli
```

## Resources

- **Documentation:** https://docs.langchain.com/oss/python/langchain/overview
- **Migration Guide:** https://docs.langchain.com/oss/python/migrate/langchain-v1
- **Examples:** https://docs.langchain.com/oss/python/langchain/quickstart
- **API Reference:** https://python.langchain.com/api_reference/

## Support

For issues:
1. Check the handover document: `AI-agent/docs/langchain_v1_migration_handover.md`
2. Review test cases: `AI-agent/tests/`
3. Consult LangChain docs: https://docs.langchain.com
4. Check LangSmith traces for debugging
