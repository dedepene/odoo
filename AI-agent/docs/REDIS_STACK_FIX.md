# Redis Stack Requirement for langgraph-checkpoint-redis

## Error Encountered

```
redis.exceptions.ResponseError: unknown command 'FT._LIST', with args beginning with:
```

## Root Cause

The `langgraph-checkpoint-redis` package requires **Redis Stack** (or Redis with the RediSearch module) to function. It uses Redis search indexes to store and retrieve checkpoints efficiently.

The error occurred because we were using `redis:7-alpine`, which is a minimal Redis image that **does not include** the RediSearch module.

## Solution

### Updated Docker Compose Configuration

Changed from plain Redis to Redis Stack:

```yaml
# ❌ OLD - Plain Redis (missing RediSearch)
redis:
  image: redis:7-alpine
  command: ["redis-server", "--save", "60", "1"]
  ports:
    - "6379:6379"

# ✅ NEW - Redis Stack (includes RediSearch + other modules)
redis:
  image: redis/redis-stack:latest
  ports:
    - "6379:6379"
    - "8001:8001"  # RedisInsight web UI (optional but useful)
  environment:
    - REDIS_ARGS=--save 60 1
```

## What is Redis Stack?

**Redis Stack** is a bundled Redis distribution that includes:
- **Redis OSS** - The core Redis database
- **RediSearch** - Full-text search and secondary indexing ✅ **Required by langgraph-checkpoint-redis**
- **RedisJSON** - Native JSON support
- **RedisGraph** - Graph database capabilities
- **RedisTimeSeries** - Time series data structures
- **RedisBloom** - Probabilistic data structures
- **RedisInsight** - Web-based management UI (port 8001)

## Why Does langgraph-checkpoint-redis Need RediSearch?

The package uses RediSearch's indexing capabilities to:
1. **Create search indexes** for checkpoint metadata
2. **Query checkpoints** by thread_id, namespace, and other fields
3. **Efficiently list checkpoints** matching specific criteria
4. **Enable time travel** through conversation history

Without RediSearch, commands like `FT._LIST` (list indexes) fail because they don't exist in plain Redis.

## Alternative Solutions

If you can't use Redis Stack, you have two alternatives:

### Option 1: Use InMemorySaver (Development Only)
```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()  # In-memory only, lost on restart
agent = create_agent(
    model=model,
    tools=tools,
    checkpointer=checkpointer
)
```

**Pros**: No external dependencies
**Cons**: Data lost on restart, not suitable for production

### Option 2: Use PostgresSaver (Production Alternative)
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# You already have Postgres in your stack!
DB_URI = "postgresql://postgres:postgres@postgres:5432/postgres"

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    agent = create_agent(
        model=model,
        tools=tools,
        checkpointer=checkpointer
    )
```

**Pros**: Production-ready, uses existing Postgres
**Cons**: Requires additional package: `pip install langgraph-checkpoint-postgres`

## Recommended Solution

**Use Redis Stack** - It's the simplest solution and provides:
- ✅ Drop-in replacement for plain Redis
- ✅ All required modules included
- ✅ RedisInsight UI for debugging (http://localhost:8001)
- ✅ Battle-tested for LangGraph checkpointing
- ✅ Excellent performance

## Deployment Notes

### Docker Compose (Development)
```yaml
redis:
  image: redis/redis-stack:latest
  ports:
    - "6379:6379"
    - "8001:8001"
  environment:
    - REDIS_ARGS=--save 60 1
```

### Production Considerations
- **Redis Stack Cloud**: Managed Redis Stack service
- **Self-hosted Redis Stack**: `redis/redis-stack-server:latest` (no UI, smaller image)
- **Redis Enterprise**: Commercial offering with Redis Stack modules

## Testing the Fix

1. **Stop current containers**:
   ```cmd
   docker-compose -f AI-agent/docker-compose.poc.yml down
   ```

2. **Remove old Redis volume** (if needed):
   ```cmd
   docker volume rm ai-agent_redis-data
   ```

3. **Rebuild and start**:
   ```cmd
   docker-compose -f AI-agent/docker-compose.poc.yml up -d --build
   ```

4. **Verify Redis Stack is running**:
   ```cmd
   docker-compose -f AI-agent/docker-compose.poc.yml logs redis
   ```
   
   You should see:
   ```
   Ready to accept connections
   RediSearch module loaded
   ```

5. **Access RedisInsight** (optional):
   - Open http://localhost:8001
   - Connect to localhost:6379
   - View checkpoints and indexes

## Files Modified

- **`AI-agent/docker-compose.poc.yml`** - Changed Redis image from `redis:7-alpine` to `redis/redis-stack:latest`

## Impact

- **Breaking Change**: Requires Redis Stack instead of plain Redis
- **Size Impact**: Redis Stack image is larger (~400MB vs ~40MB for Alpine)
- **Performance**: Negligible - Redis Stack includes extra modules but doesn't impact performance if not used
- **Benefits**: Full checkpoint functionality, RedisInsight UI for debugging

---

**Status**: ✅ **FIXED**  
**Date**: November 15, 2025  
**Impact**: Redis Stack now properly supports langgraph-checkpoint-redis indexing
