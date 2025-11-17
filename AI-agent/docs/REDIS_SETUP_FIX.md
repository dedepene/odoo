# Redis Checkpointer Setup Fix

## Error Observed

```
redis.exceptions.ConnectionError: Connection closed by server.
```

This error occurred during `checkpointer.aget_tuple()` when the agent tried to read from Redis for the first time.

## Root Cause

The `AsyncRedisSaver` checkpointer requires calling `await checkpointer.asetup()` on first use to initialize Redis data structures, including:

1. **RediSearch indices** - For efficient checkpoint querying
2. **Metadata structures** - For tracking checkpoint versions and pointers
3. **Schema definitions** - For JSON document storage

Without calling `asetup()`, the checkpointer attempts to use Redis structures that don't exist yet, causing the Redis server to close the connection when encountering invalid operations.

## Solution

Added `await self._checkpointer.asetup()` after entering the context manager in `_initialize_agent()`:

```python
# Initialize Redis checkpointer
if self._checkpointer is None:
    # from_conn_string returns a context manager, enter it to get the checkpointer
    checkpointer_cm = AsyncRedisSaver.from_conn_string(self._checkpointer_url)
    self._checkpointer = await checkpointer_cm.__aenter__()
    
    # Setup Redis indices/structures on first use (idempotent)
    # This creates the necessary RediSearch indices and data structures
    await self._checkpointer.asetup()
    LOGGER.info("Initialized AsyncRedisSaver checkpointer with Redis indices")
```

## Why This Works

According to LangChain documentation:

> "You need to call `checkpointer.setup()` the first time you're using Redis checkpointer"

The `asetup()` method is **idempotent** - it can be called multiple times safely:
- **First call**: Creates all required Redis indices and structures
- **Subsequent calls**: No-op (structures already exist)

This setup creates:
- RediSearch index for efficient checkpoint lookups
- JSON document schemas for checkpoint metadata
- Pointer structures for tracking latest checkpoints per thread

## Redis Stack Requirements

This fix works because we're using **Redis Stack** (configured in docker-compose.poc.yml):

```yaml
redis:
  image: redis/redis-stack:latest  # Includes RediSearch module
  ports:
    - "6379:6379"
    - "8001:8001"  # RedisInsight UI
```

Redis Stack includes the **RediSearch module** which provides:
- Full-text search capabilities
- Secondary indexing
- JSON document support

Without RediSearch, the `asetup()` call would fail with "unknown command 'FT._LIST'" (as seen in previous error).

## Testing

After this fix:

1. **First message**: Creates Redis indices (one-time setup)
2. **Subsequent messages**: Use existing indices
3. **RedisInsight UI**: Can view checkpoint data at http://localhost:8001

Expected log output:
```
langchain_agent INFO   Redis client is a standalone client
langchain_agent INFO   Initialized AsyncRedisSaver checkpointer with Redis indices
langchain_agent INFO   LangChain v1 agent initialized with checkpointer
```

## Verification Steps

1. **Check Redis indices created**:
   ```bash
   docker exec -it odoo-redis-1 redis-cli FT._LIST
   ```
   Should show checkpoint indices

2. **View checkpoints in RedisInsight**:
   - Open http://localhost:8001
   - Browse keys matching pattern `checkpoint:*`
   - View JSON structure of checkpoint data

3. **Test conversation memory**:
   ```
   User: My name is Bob
   Agent: [responds]
   User: What's my name?
   Agent: Your name is Bob [checkpoint working]
   ```

## Related Files

- `AI-agent/langchain_agent.py` - Added `asetup()` call
- `AI-agent/docker-compose.poc.yml` - Redis Stack configuration
- `AI-agent/docs/REDIS_STACK_FIX.md` - Redis Stack migration

## References

- [LangChain Async Redis Checkpointer Documentation](https://docs.langchain.com/oss/python/langgraph/add-memory#async)
- [langgraph-checkpoint-redis PyPI](https://pypi.org/project/langgraph-checkpoint-redis/)
- [Redis Stack Documentation](https://redis.io/docs/stack/)
