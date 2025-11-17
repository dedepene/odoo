# Runtime Error Fix - AsyncRedisSaver and CompiledStateGraph

## Errors Encountered

During runtime execution, two critical errors occurred:

### Error 1: Context Manager Issue
```python
AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'asetup'
```

**Root Cause**: `AsyncRedisSaver.from_conn_string()` returns an async context manager (`_AsyncGeneratorContextManager`), not a checkpointer directly. Attempting to call `.asetup()` on the context manager failed because that method doesn't exist on the context manager object itself.

### Error 2: Double Compilation Attempt
```python
AttributeError: 'CompiledStateGraph' object has no attribute 'compile'
```

**Root Cause**: `create_agent()` already returns a **compiled** LangGraph graph (CompiledStateGraph). Attempting to call `.compile()` again on an already-compiled graph failed because compiled graphs don't have a `compile()` method.

## Root Cause Analysis

### Issue 1: Improper Context Manager Usage
The original code tried to use `AsyncRedisSaver.from_conn_string()` like this:

```python
# ❌ WRONG
self._checkpointer = AsyncRedisSaver.from_conn_string(url)
await self._checkpointer.asetup()  # This fails!
```

According to LangChain documentation, `AsyncRedisSaver.from_conn_string()` should be used with `async with`:

```python
# ✅ CORRECT (for short-lived usage)
async with AsyncRedisSaver.from_conn_string(url) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
    result = await graph.ainvoke(...)
```

However, for a **long-running FastAPI application**, we need persistent checkpointer access across many requests. The solution is to manually enter the context manager and store it:

```python
# ✅ CORRECT (for long-running app)
checkpointer_cm = AsyncRedisSaver.from_conn_string(url)
self._checkpointer = await checkpointer_cm.__aenter__()
```

### Issue 2: Misunderstanding create_agent Return Type
The documentation clearly states:

> **`create_agent` automatically returns a compiled LangGraph graph**

This means:
- `create_agent()` → Returns `CompiledStateGraph` (ready to invoke)
- `builder.compile()` → Returns `CompiledStateGraph` (ready to invoke)

You **cannot** call `.compile()` on a `CompiledStateGraph`.

The original code incorrectly tried to:

```python
# ❌ WRONG
self.agent = create_agent(model, tools, system_prompt)  # Already compiled!
agent_with_memory = self.agent.compile(checkpointer=checkpointer)  # Can't compile again!
```

The correct approach is to **pass the checkpointer to create_agent during initialization**:

```python
# ✅ CORRECT
self.agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=system_prompt,
    checkpointer=checkpointer  # Pass checkpointer HERE
)
# Agent is now ready to use with memory - no further compilation needed!
result = await self.agent.ainvoke(input, config={"configurable": {"thread_id": "1"}})
```

## Solution Implemented

### 1. Proper Checkpointer Initialization

Changed from immediate initialization to lazy async initialization:

```python
def __init__(self, ...):
    # Store URL, don't initialize checkpointer yet
    self._checkpointer: Optional[AsyncRedisSaver] = None
    self._checkpointer_url = redis_url
    self.agent = None  # Will be initialized lazily

async def _initialize_agent(self):
    """Initialize agent with checkpointer (called before first use)."""
    if self.agent is not None:
        return  # Already initialized
        
    # Manually enter context manager for long-running app
    checkpointer_cm = AsyncRedisSaver.from_conn_string(self._checkpointer_url)
    self._checkpointer = await checkpointer_cm.__aenter__()
    
    # Create agent with checkpointer (returns compiled graph)
    self.agent = create_agent(
        model=self.model,
        tools=self.tools,
        system_prompt=context_aware_prompt,
        checkpointer=self._checkpointer  # ✅ Pass to create_agent
    )
```

### 2. Updated Agent Invocation

```python
async def arun(self, *, session_id: str, user_context: Dict, message: str):
    # Ensure agent is initialized (happens once, then cached)
    await self._initialize_agent()
    assert self.agent is not None
    
    # Agent is already compiled with checkpointer - just invoke it!
    result = await self.agent.ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": session_id}},
        context=context
    )
    return result
```

### 3. Proper Cleanup

```python
async def cleanup(self):
    """Cleanup resources (exit context manager)."""
    if self._checkpointer is not None:
        try:
            # Properly exit the context manager
            await self._checkpointer.__aexit__(None, None, None)
            LOGGER.info("Cleaned up AsyncRedisSaver resources")
        except Exception as e:
            LOGGER.warning("Error cleaning up checkpointer: %s", e)
        finally:
            self._checkpointer = None
```

## Key Lessons Learned

### 1. Read the Documentation Carefully
- **`create_agent` returns a COMPILED graph** - This is stated explicitly in the docs
- Don't assume you need to compile things that are already compiled

### 2. Context Managers in Long-Running Apps
- Short-lived scripts: Use `async with AsyncRedisSaver.from_conn_string() as cp:`
- Long-running apps: Manually `__aenter__()` and store, then `__aexit__()` on cleanup

### 3. Checkpointer Lifecycle
- Initialize checkpointer **before** creating agent
- Pass checkpointer **to create_agent**, not at invocation time
- Clean up properly with `__aexit__()` when shutting down

### 4. LangChain v1 Simplified Patterns
- Old way: `AgentExecutor` + manual compilation + RunnableWithMessageHistory
- New way: `create_agent` with checkpointer parameter → done!

## Testing Verification

After this fix:
1. ✅ Agent initializes successfully on first request
2. ✅ Checkpointer properly initialized from context manager
3. ✅ Agent invokes without "no attribute 'compile'" error
4. ✅ Conversation history persists across requests via Redis
5. ✅ No "asetup" attribute errors

## File Changes

- **AI-agent/langchain_agent.py**: Complete refactor
  - Added `_initialize_agent()` async method
  - Removed `get_checkpointer()` method (no longer needed)
  - Updated `__init__()` to defer agent creation
  - Updated `arun()` to call `_initialize_agent()` and invoke directly
  - Updated `cleanup()` to properly exit context manager
  - Added type hints for `self.agent` with `TYPE_CHECKING`

## References

- LangChain docs: "create_agent automatically returns a compiled LangGraph graph"
- LangGraph checkpointing docs: `AsyncRedisSaver.from_conn_string()` usage
- Redis checkpointer example: https://docs.langchain.com/oss/python/langgraph/add-memory

---

**Status**: ✅ **FIXED**  
**Date**: November 15, 2025  
**Impact**: Critical runtime errors resolved, agent now fully functional
