# Dynamic Prompt Middleware Fix

## Error Observed

```python
pydantic_core._pydantic_core.ValidationError: 2 validation errors for SystemMessage
content.str
  Input should be a valid string [type=string_type, input_value=<langchain.agents.middlew...bject at 0x7d89cac723c0>, input_type=context_aware_prompt]
content.list[union[str,dict[any,any]]]
  Input should be a valid list [type=list_type, input_value=<langchain.agents.middlew...bject at 0x7d89cac723c0>, input_type=context_aware_prompt]
```

This Pydantic validation error occurred when the agent tried to create a `SystemMessage` with the system prompt. Instead of receiving a string, it received a function object decorated with `@dynamic_prompt`.

## Root Cause

The `@dynamic_prompt` decorator was being incorrectly passed to the `system_prompt` parameter of `create_agent()`:

```python
# ❌ INCORRECT - Passing decorated function to system_prompt
@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    return "You are a helpful assistant."

agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=context_aware_prompt,  # Wrong parameter!
    context_schema=AgentContext,
)
```

### Why This Failed

According to LangChain v1 API documentation:

1. **`system_prompt` parameter** expects a **string literal**:
   ```python
   agent = create_agent(
       model=model,
       tools=tools,
       system_prompt="You are a helpful assistant.",  # String
   )
   ```

2. **`middleware` parameter** expects **decorated callable(s)** like `@dynamic_prompt`:
   ```python
   agent = create_agent(
       model=model,
       tools=tools,
       middleware=[context_aware_prompt],  # List of middleware
   )
   ```

When the decorated function was passed to `system_prompt`, LangChain tried to use the function object itself as a string, causing the Pydantic validation error.

## Solution

Move the `@dynamic_prompt` decorated function from `system_prompt` to `middleware` parameter:

```python
# ✅ CORRECT - Pass decorated function to middleware
@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    """Inject user context into system prompt."""
    base = self.system_prompt  # Use base static prompt
    
    # Add dynamic context from runtime
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

# Create the agent with middleware
agent = create_agent(
    model=self.model,
    tools=self.tools,
    middleware=[context_aware_prompt],  # Correct parameter
    context_schema=AgentContext,
    checkpointer=self._checkpointer,
)
```

## How Dynamic Prompts Work

The `@dynamic_prompt` decorator creates middleware that:

1. **Intercepts model calls** before they reach the LLM
2. **Executes the wrapped function** with a `ModelRequest` object containing:
   - `request.state` - Current agent state (messages, custom fields)
   - `request.runtime.context` - Runtime context (user context passed to `invoke()`)
   - `request.messages` - Conversation history
3. **Returns the generated string** which becomes the system prompt for that specific model call
4. **Allows dynamic prompt generation** based on:
   - User role, permissions, preferences
   - Conversation length or complexity
   - Runtime configuration
   - External data (from stores, databases, APIs)

### Example: Context-Aware Prompts

```python
from dataclasses import dataclass
from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt, ModelRequest

@dataclass
class Context:
    user_role: str
    deployment_env: str

@dynamic_prompt
def role_based_prompt(request: ModelRequest) -> str:
    user_role = request.runtime.context.user_role
    env = request.runtime.context.deployment_env
    
    base = "You are a helpful assistant."
    
    if user_role == "admin":
        base += "\nYou have admin access. You can perform all operations."
    elif user_role == "viewer":
        base += "\nYou have read-only access. Guide users to read operations only."
    
    if env == "production":
        base += "\nBe extra careful with any data modifications."
    
    return base

agent = create_agent(
    model="gpt-4o",
    tools=[...],
    middleware=[role_based_prompt],
    context_schema=Context
)

# Invoke with context
result = agent.invoke(
    {"messages": [{"role": "user", "content": "Show me the database"}]},
    context=Context(user_role="admin", deployment_env="production")
)
```

## Key Differences: system_prompt vs middleware

| Feature | `system_prompt` | `middleware=[dynamic_prompt]` |
|---------|----------------|------------------------------|
| Type | Static string | Dynamic function |
| When evaluated | Once at agent creation | On every model call |
| Access to state | ❌ No | ✅ Yes (via `request.state`) |
| Access to context | ❌ No | ✅ Yes (via `request.runtime.context`) |
| Use case | Fixed instructions | Context-aware prompts |
| Example | `"You are a helpful assistant."` | `@dynamic_prompt def f(request): ...` |

## Testing

After this fix, the agent should:

1. ✅ Initialize without Pydantic validation errors
2. ✅ Generate dynamic prompts based on user context
3. ✅ Include runtime context in system prompt
4. ✅ Adapt prompt length based on conversation history

Expected log output:
```
18:29:52 main INFO   LangSmith tracing enabled for project: playhub-bg-dev
18:29:53 langchain_agent INFO   LangChain agent configuration ready: model=gpt-4.1-mini, tools=4, max_iterations=25
18:29:53 httpx INFO   HTTP Request: POST http://mcp-server:8000/mcp "HTTP/1.1 200 OK"
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Verification Steps

1. **Send test message via Telegram**
2. **Check logs** - No Pydantic validation errors
3. **Verify dynamic prompt** - User context should be injected in LangSmith traces
4. **Test context variations** - Different roles, player IDs should generate different prompts

## Related Files

- `AI-agent/langchain_agent.py` - Fixed middleware parameter usage
- `AI-agent/docs/REDIS_SETUP_FIX.md` - Previous Redis setup fix
- `AI-agent/docs/RUNTIME_ERROR_FIX.md` - Context manager fix

## References

- [LangChain Dynamic System Prompt Documentation](https://docs.langchain.com/oss/python/langchain/agents#dynamic-system-prompt)
- [LangChain Middleware Guide](https://docs.langchain.com/oss/python/langchain/middleware/custom)
- [LangChain Context Engineering](https://docs.langchain.com/oss/python/langchain/context-engineering)
- [LangChain v1 Migration Guide - Dynamic Prompts](https://docs.langchain.com/oss/python/migrate/langchain-v1#dynamic-prompts)
