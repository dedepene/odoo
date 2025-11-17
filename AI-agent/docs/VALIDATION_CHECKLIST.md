# LangChain V1 Migration Validation Checklist

Use this checklist to validate the migration is working correctly.

## Pre-Deployment Validation

### 1. Environment Setup
- [ ] Python 3.8+ installed
- [ ] Docker and Docker Compose installed
- [ ] Git repository up to date
- [ ] `.env` file configured with required keys

### 2. Dependency Installation
```bash
cd AI-agent
pip install -r requirements.txt
```

- [ ] No installation errors
- [ ] `langchain>=1.0.0` installed
- [ ] `langgraph>=1.0.0` installed
- [ ] `langgraph-checkpoint-redis>=2.0.0` installed

Verify:
```bash
pip show langchain langchain-core langgraph langgraph-checkpoint-redis
```

### 3. Unit Tests
```bash
pytest tests/test_modern_agent.py -v
```

Expected Results:
- [ ] `TestAgentInitialization::test_basic_initialization` PASSED
- [ ] `TestAgentInitialization::test_custom_system_prompt` PASSED
- [ ] `TestAgentContext::test_context_creation` PASSED
- [ ] `TestAgentExecution::test_tool_context_set_and_cleared` PASSED
- [ ] `TestAgentExecution::test_context_cleared_on_error` PASSED
- [ ] `TestMemoryManagement::test_multiple_turns_same_session` PASSED
- [ ] All tests PASSED, no failures

### 4. Docker Stack Startup
```bash
docker-compose -f docker-compose.poc.yml up -d
```

Check services:
```bash
docker-compose -f docker-compose.poc.yml ps
```

Expected:
- [ ] `langchain-agent` - Up and healthy
- [ ] `redis` - Up
- [ ] `postgres` - Up
- [ ] `mcp-server` - Up and healthy

### 5. Service Health Checks
```bash
# Agent health
curl http://localhost:8443/healthz
# Expected: {"status":"ok"}

# MCP server health
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

- [ ] Agent responding to health checks
- [ ] MCP server responding to health checks
- [ ] No errors in agent logs: `docker logs odoo-langchain-agent-1`

### 6. Integration Tests (Optional but Recommended)
```bash
INTEGRATION_TESTS=1 pytest tests/test_integration.py -v -m integration -s
```

- [ ] `test_agent_with_real_services` PASSED
- [ ] `test_redis_checkpointing` PASSED
- [ ] `test_tool_calling` PASSED (if MCP server has data)

---

## Functional Testing

### 7. Basic Conversation
```bash
# Test via API (requires verified user in database)
curl -X POST http://localhost:8443/chat \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 12345,
    "message": "Hello, can you help me?"
  }'
```

Expected Response:
```json
{
  "reply": "<helpful response>",
  "session_id": "telegram:12345"
}
```

- [ ] Agent responds with non-empty reply
- [ ] No errors in response
- [ ] Session ID returned correctly

### 8. Multi-Turn Conversation
Send second message with same telegram_id:
```bash
curl -X POST http://localhost:8443/chat \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 12345,
    "message": "What did I just ask you?"
  }'
```

- [ ] Agent references previous message
- [ ] Conversation context maintained
- [ ] Session ID same as before

### 9. Redis Checkpoint Verification
```bash
docker exec -it odoo-redis-1 redis-cli KEYS "checkpoint:telegram:12345:*"
```

- [ ] Multiple checkpoint keys exist
- [ ] Keys follow pattern: `checkpoint:telegram:{id}:{number}`
- [ ] TTL is set on keys (check with `TTL` command)

### 10. Tool Calling (Absence Reporting)
Test with verified user:
```bash
curl -X POST http://localhost:8443/chat \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 12345,
    "message": "I need to report an absence for my child on November 20"
  }'
```

- [ ] Agent attempts to call `report_absence` tool
- [ ] Tool receives proper context (check logs)
- [ ] Response indicates tool was executed
- [ ] No "tool not found" errors

### 11. Session Isolation
Send message with different telegram_id:
```bash
curl -X POST http://localhost:8443/chat \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 67890,
    "message": "Hello"
  }'
```

- [ ] New session created
- [ ] No reference to previous user's conversation
- [ ] Separate checkpoint keys in Redis

### 12. Error Handling
Send message without authentication (should fail):
```bash
curl -X POST http://localhost:8443/chat \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 99999,
    "message": "Hello"
  }'
```

- [ ] Returns appropriate error (403 Forbidden)
- [ ] Error message clear
- [ ] No server crash

---

## Observability Validation

### 13. LangSmith Tracing
If `LANGSMITH_TRACING=true`:

1. Go to https://smith.langchain.com
2. Select your project (e.g., "telegram-agent")
3. Find recent traces

- [ ] Traces appear for each agent invocation
- [ ] Trace shows tool calls
- [ ] Trace shows LLM requests
- [ ] No errors in traces
- [ ] Token usage visible

### 14. Logging
```bash
docker logs odoo-langchain-agent-1 --tail=100
```

- [ ] INFO logs show agent initialization
- [ ] DEBUG logs (if enabled) show invocation details
- [ ] No ERROR or CRITICAL logs
- [ ] Structured logging format
- [ ] No Python stack traces

### 15. Redis Monitoring
```bash
# Check memory usage
docker exec -it odoo-redis-1 redis-cli INFO memory

# Check keyspace
docker exec -it odoo-redis-1 redis-cli INFO keyspace

# Count checkpoint keys
docker exec -it odoo-redis-1 redis-cli KEYS "checkpoint:*" | wc -l
```

- [ ] Memory usage reasonable (<100MB for testing)
- [ ] Keyspace shows `db0` with keys
- [ ] Checkpoint count matches expectations
- [ ] No memory warnings

---

## Performance Validation

### 16. Response Time
Use timing in curl:
```bash
time curl -X POST http://localhost:8443/chat \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 12345,
    "message": "What time is it?"
  }'
```

- [ ] Response time < 5 seconds for simple queries
- [ ] Response time < 10 seconds with tool calls
- [ ] No timeouts
- [ ] Consistent performance across requests

### 17. Concurrent Requests
Run multiple requests simultaneously:
```bash
for i in {1..5}; do
  (curl -X POST http://localhost:8443/chat \
    -H "Content-Type: application/json" \
    -d "{\"telegram_id\": $i, \"message\": \"Hello $i\"}" &)
done
wait
```

- [ ] All requests succeed
- [ ] No race conditions
- [ ] No "too many connections" errors
- [ ] Redis handles concurrent checkpointing

---

## Regression Testing

### 18. Telegram Webhook (If Configured)
Send test webhook:
```bash
curl -X POST http://localhost:8443/telegram/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "text": "Test message",
      "chat": {"id": 12345}
    }
  }'
```

- [ ] Webhook accepted (200 OK)
- [ ] Message processed
- [ ] Response sent to Telegram (if bot configured)
- [ ] Audit log created in database

### 19. Database Audit Logging
Check if audit records created:
```sql
-- Connect to postgres
docker exec -it odoo-postgres-1 psql -U postgres -d postgres

SELECT * FROM agent_audit ORDER BY created_at DESC LIMIT 5;
```

- [ ] Audit records created for each chat
- [ ] `telegram_id` recorded correctly
- [ ] `prompt` and `response` populated
- [ ] `session_id` matches expected format

### 20. OTP Registration Flow (If Used)
Test registration endpoints:
```bash
# Send OTP
curl -X POST http://localhost:8443/register/send_otp \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 99999,
    "phone": "+1234567890"
  }'

# Verify OTP (use code from logs/Redis)
curl -X POST http://localhost:8443/register/verify \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 99999,
    "otp": "123456",
    "role": "parent",
    "player_ids": [1, 2]
  }'
```

- [ ] OTP generation works
- [ ] OTP stored in Redis
- [ ] Verification succeeds with correct OTP
- [ ] User record created in database

---

## Final Checks

### 21. Resource Cleanup
```bash
# Clear test data
docker exec -it odoo-redis-1 redis-cli FLUSHDB

# Restart services
docker-compose -f docker-compose.poc.yml restart
```

- [ ] Services restart cleanly
- [ ] No orphaned processes
- [ ] Logs show clean startup
- [ ] Health checks pass after restart

### 22. Documentation Review
- [ ] Handover document read and understood
- [ ] Quick reference accessible
- [ ] Migration summary reviewed
- [ ] Troubleshooting section noted

### 23. Rollback Plan Verified
- [ ] Previous commit identified
- [ ] Rollback commands tested (in dev)
- [ ] Rollback time acceptable (<10 minutes)
- [ ] Team knows how to execute rollback

---

## Sign-Off

### Pre-Deployment
- [ ] All unit tests passing
- [ ] Integration tests passing (if run)
- [ ] Service health checks passing
- [ ] Basic conversation working
- [ ] Multi-turn conversation working
- [ ] Tool calling working
- [ ] Redis checkpointing verified

### Optional (Recommended)
- [ ] LangSmith tracing working
- [ ] Performance acceptable
- [ ] Concurrent requests handled
- [ ] Telegram webhook working
- [ ] Audit logging working

### Deployment Authorization
- [ ] Development validation complete
- [ ] Staging validation complete (if applicable)
- [ ] Team briefed on changes
- [ ] Rollback plan in place
- [ ] Monitoring configured

**Validated By:** ___________________  
**Date:** ___________________  
**Ready for Production:** ☐ Yes ☐ No

---

## Post-Deployment Monitoring (First 24 Hours)

- [ ] Check error rate every 2 hours
- [ ] Monitor Redis memory usage
- [ ] Review LangSmith traces for errors
- [ ] Gather user feedback
- [ ] Check response times
- [ ] Verify no memory leaks
- [ ] Confirm checkpoint cleanup working

---

*Use this checklist systematically to ensure migration success.*
