# Testing Guide - Post-Fix Verification

## Quick Test Commands

### 1. Rebuild Docker Image
```cmd
cd d:\Code\projects\odoo\odoo\AI-agent
docker-compose -f docker-compose.poc.yml build langchain-agent
```

### 2. Start Stack
```cmd
docker-compose -f docker-compose.poc.yml up -d
```

### 3. Check Logs
```cmd
docker-compose -f docker-compose.poc.yml logs -f langchain-agent
```

## Expected Log Output (Success)

```
langchain-agent-1  | LangChain agent configuration ready: model=gpt-4.1-mini, tools=4, max_iterations=25
langchain-agent-1  | INFO:     Started server process [1]
langchain-agent-1  | INFO:     Waiting for application startup.
langchain-agent-1  | Initialized AsyncRedisSaver checkpointer
langchain-agent-1  | LangChain v1 agent initialized with checkpointer
langchain-agent-1  | INFO:     Application startup complete.
```

## Test Request via Telegram

Send a message to your Telegram bot (e.g., "Hello" or "кога е следващата тренировка на Стела?").

### Expected Behavior:
1. ✅ No AttributeError about '_AsyncGeneratorContextManager'
2. ✅ No AttributeError about 'CompiledStateGraph' having no 'compile' attribute
3. ✅ Agent initializes on first request (lazy initialization)
4. ✅ Subsequent requests reuse the initialized agent (no re-initialization)
5. ✅ Conversation history persists across messages

## Verification Checklist

- [ ] Docker build completes successfully
- [ ] Container starts without errors
- [ ] Redis checkpointer initializes on first request
- [ ] Agent processes messages without runtime errors
- [ ] Conversation history persists (test by asking "What did I just ask?")
- [ ] Logs show successful agent invocation

## Troubleshooting

### If agent doesn't initialize:
Check logs for "Initialized AsyncRedisSaver checkpointer" message

### If Redis connection fails:
```cmd
docker-compose -f docker-compose.poc.yml logs redis
```
Ensure Redis is running and accessible

### If checkpointer errors occur:
Check that `langgraph-checkpoint-redis>=0.1.2` and `redis>=5.2.1` are installed:
```cmd
docker-compose -f docker-compose.poc.yml exec langchain-agent pip list | grep -E "(redis|langgraph)"
```

## Success Criteria

✅ **Agent responds to Telegram messages**  
✅ **No AttributeError exceptions in logs**  
✅ **Conversation history works across messages**  
✅ **No "compile" attribute errors**  
✅ **Checkpointer initializes successfully**

---

Once all tests pass, the migration to LangChain v1 is complete and production-ready!
