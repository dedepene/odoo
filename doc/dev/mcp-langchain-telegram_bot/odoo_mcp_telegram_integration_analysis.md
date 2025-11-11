# Odoo MCP Server + LangChain Agent Integration Analysis for Tennis Academy
**Analysis Date:** November 7, 2025  
**Odoo Version:** 19.0  
**MCP Server Repository:** https://github.com/vzeman/odoo-mcp-server  
**Agent Framework:** LangChain (Agent + Tooling)

## Executive Summary

This document analyzes the feasibility of using the Odoo MCP Server together with a LangChain-based agent to build Telegram/WhatsApp chatbots for the Tennis Academy Management System. The LangChain agent will provide LLM-driven natural language capabilities, conversation memory, and explicit tool calling (MCP tool wrappers) to interact with Odoo.

## 1. Can the MCP Server + LangChain Agent Support Academy Chatbot Implementation?

Answer: YES — LangChain provides the primitives we need (LLM, memory, tools) and is a good fit for production-grade agents that call MCP tools to query and update Odoo.

Key capabilities we will implement with LangChain:
- XML-RPC / MCP access via lightweight HTTP wrappers (search_records, get_record, create_record, execute_method)
- Conversation memory (Redis-backed ConversationBufferMemory or custom memory store)
- Tool orchestration using LangChain tools (each tool wraps an MCP operation)
- FastAPI wrapper exposing a /chat endpoint for the Telegram/WhatsApp bot
- Streaming LLM responses and structured tool outputs when needed

---

## 2. Guardian Query: "What are my kids' upcoming practice sessions?"

**Answer: YES - Fully Supported with ADK Agent**

### ADK Agent Implementation

**User Message:**
```
"What are Stella's upcoming practice sessions?"
```

**ADK Agent Process (Automatic):**
```python
# ADK agent automatically:
# 1. Understands intent: query_upcoming_sessions
# 2. Extracts entities: player_name="Stella", timeframe="upcoming"
# 3. Plans MCP tool sequence:
#    a) search_records(academy.player) to find Stella
#    b) search_records(academy.session.occurrence) for her sessions
# 4. Executes tools with context awareness
# 5. Generates natural language response

# NO CUSTOM CODE NEEDED - ADK handles everything
```

**Agent Configuration (agent_config.yaml):**

## 2. User scenarios (examples)

Below are concise LangChain-based flows for the main use cases. Each flow uses a small set of LangChain tools that wrap MCP calls; tools are invoked explicitly by the agent.

Guardian: "What are Stella's upcoming practice sessions?"
- Agent: uses SearchSessionsTool(player_name="Stella", start_date=today)
- Tool: calls MCP search_records on `academy.session.occurrence`
- Agent: formats and returns friendly response with dates, times, courts, coach

Guardian: "Report absence for Stella on Thursday"
- Agent: runs SearchSessionsTool to disambiguate the session
- Agent: asks clarifying question if multiple matches
- Agent: uses ReportAbsenceTool(occurrence_id, player_id, reason_code)
- Tool: calls MCP create_record on `academy.session.absence`
- Agent: confirms creation to guardian

Coach: "What's the phone number for Stella's dad?"
- Agent: checks user_role from injected context (must be coach/admin)
- Agent: uses GetContactInfoTool(player_name="Stella") which calls MCP search/get on academy.player and res.partner
- Agent: returns guardian contact fields or requests clarification

Guardian: "What do I owe for Stella?"
- Agent: uses GetInvoicesTool(partner_id=guardian_partner_id) to query `account.move`
- Tool: aggregates amount_residual and formats a billing summary

## 3. Implementation plan (LangChain-only)

High level tasks to implement the LangChain approach:
- Create small async MCP client (HTTP) that calls the MCP server JSON-RPC endpoints
- Implement LangChain Tools: SearchSessionsTool, ReportAbsenceTool, GetInvoicesTool, GetContactInfoTool (each returns a friendly string and structured metadata)
- Build LangChain agent using an OpenAI-compatible chat model (ChatOpenAI or similar). Use ConversationBufferMemory and Redis for persistence.
- FastAPI wrapper exposing /chat and /webhooks/odoo endpoints. Inject authenticated user context per request.
- Lightweight Telegram bot that forwards messages to /chat and handles registration/OTP and file uploads; keep the bot free of NLP logic.
- Add monitoring via LangSmith (optional) and Redis for caching/memory.

## 4. Tool contract (short)
- Inputs: user message, user context (telegram_id, user_role, guardian_id, player_ids)
- Outputs: natural language response plus optional structured actions (e.g., created_record_id)
- Error modes: MCP call failures, permission denied, ambiguous query
- Success criteria: agent correctly answers 90% of PoC queries and can create absence records end-to-end

## 5. Edge cases to cover
- Ambiguous player names (ask clarifying questions)
- Guardians requesting other families' data (enforce RBAC)
- Offline MCP server or timeouts (user-friendly error and retry guidance)
- Large result sets (paginate and summarize)

## 6. Minimal code artifacts to add
- `langchain_agent.py` — agent and memory wiring
- `mcp_tools.py` — LangChain tools wrapping MCP calls
- `main.py` — FastAPI wrapper (health, /chat, /webhooks/odoo)
- `Dockerfile` and `docker-compose.yml` — for langchain-agent, redis, and mcp-server
- small `README.md` with run instructions

## 7. Quick PoC checklist
1. Implement MCP client and one tool (SearchSessionsTool)
2. Wire ChatOpenAI + ConversationBufferMemory + tool into an agent
3. Add FastAPI /chat endpoint and a minimal Telegram forwarder
4. Test 3 queries: sessions, absence (create), billing

## 8. Deployment notes
- Use Redis for memory and caching.
- Deploy LangChain agent behind HTTPS; communicate with MCP server via internal network.
- Use environment variables for OPENAI_API_KEY, REDIS_URL, MCP_SERVER_URL.
- Add rate limiting on /chat and caching for frequent queries.

## 9. Recommendation (final)

Use LangChain as the single agent framework for the Tennis Academy chatbot. LangChain gives us explicit tool control, robust memory patterns, better observability (LangSmith), and broader community support. The repository should remove ADK-related docs and code paths and consolidate examples, Docker configs, and FastAPI wrappers around the LangChain implementation.

---

**Document Version:** 3.0 (LangChain-only)  
**Last Updated:** November 7, 2025  
**Author:** AI Analysis  
**Status:** Draft - Pending Stakeholder Review  
**Architecture:** LangChain Agent + MCP Server + Telegram Bot
🎾 Thursday, November 7th
