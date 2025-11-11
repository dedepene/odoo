# PoC System Design: LangChain Agent + MCP + Telegram Bot

**Purpose:**
This design document outlines a minimal, runnable Proof-of-Concept (PoC) to integrate Odoo via the MCP Server with a LangChain-based agent and a Telegram webhook. The PoC focuses on three core scenarios: querying upcoming sessions, reporting an absence (creating a record), and checking outstanding invoices. It prioritizes a clear separation of concerns, observability, and easy local deployment.

**Location:** `doc/dev/mcp-langchain-telegram_bot/odoo_mcp_telegram_langchain_poc_design.md`

---

## 1. Goals
- Demonstrate LangChain agent calling MCP tools to interact with Odoo models.
- Provide a FastAPI service that exposes `/chat` (agent endpoint) and `/telegram/webhook` (Telegram webhook handler).
- Keep the Telegram bot logic thin: routes, file downloads, registration/OTP; all NLP and decision-making in LangChain agent.
- Provide a reproducible local deployment using Docker Compose.
- Store conversation memory and agent state in a reliable store (Redis + Postgres for metadata). Evaluate whether a vector DB for RAG is needed.

## 2. High-level architecture

Client (Telegram) -> Telegram webhook -> FastAPI (webhook handler) -> LangChain Agent (tools call MCP server) -> MCP Server -> Odoo

Supporting services: Redis (memory/caching), Postgres (optional: persistent conversation metadata / user mappings), Optional vector DB (Milvus / Weaviate / SQLite + FAISS) for RAG if we add document retrieval.

Diagram (ASCII):

Telegram Bot
    |
    v
FastAPI (telegram webhook + /chat)
    |
    v
LangChain Agent
    - Tool wrappers -> MCP Server (HTTP JSON-RPC)
    - Memory -> Redis
    - Optional RAG vector store -> Milvus/Weaviate/FAISS
    |
    v
MCP Server -> Odoo (XML-RPC)

Storage:
- Redis: ConversationBufferMemory, caching, rate-limiting
- Postgres: telegram_users table, registration mapping, audit logs
- Vector DB (optional): embeddings + docs for RAG

## 3. Component responsibilities

- LangChain Tools (mcp_tools.py)
  - SearchSessionsTool
  - ReportAbsenceTool
  - GetInvoicesTool
  - GetContactInfoTool (RBAC enforced)
  - Each tool calls MCP server via a small MCP client wrapper

- LangChain Agent (langchain_agent.py)
  - Loads LLM (ChatOpenAI or environment-chosen model)
  - Creates AgentExecutor, wires tools, memory, and RedisChatMessageHistory
  - Exposes a synchronous async-friendly run API used by FastAPI

- FastAPI App (main.py)
  - `/chat` endpoint: accepts telegram_id, message, optional file_data
  - `/telegram/webhook` endpoint: receives Telegram updates (or use polling in PoC)
  - `/get_current_user` dependency: validates and injects user context
  - `/register` endpoints: send_otp, verify_otp (simple PoC using DB+console OTP)

- Telegram bot (lightweight)
  - For PoC, either use webhook (preferred) or polling (easier locally)
  - For webhook: configure bot to call `/telegram/webhook`
  - Bot downloads files and forwards base64 to `/chat` when attachments are sent

## 4. Data model (minimal)

Postgres schema (PoC):

```
CREATE TABLE telegram_users (
  id SERIAL PRIMARY KEY,
  telegram_id BIGINT UNIQUE NOT NULL,
  username VARCHAR(255),
  phone VARCHAR(50),
  odoo_partner_id INTEGER,
  odoo_user_id INTEGER,
  role VARCHAR(50), -- guardian, coach, admin
  player_ids INTEGER[],
  verified_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE agent_audit (
  id SERIAL PRIMARY KEY,
  telegram_id BIGINT,
  session_id VARCHAR(255),
  prompt TEXT,
  response TEXT,
  created_at TIMESTAMP DEFAULT now()
);
```

Redis:
- ConversationBufferMemory stored per-session
- Cache of frequent MCP query results

Vector DB (optional):
- Store embeddings of frequently asked docs (policies, pricing, FAQs). Use for RAG only if we need document grounding.

## 5. Docker Compose (PoC) - services

- mcp-server: ghcr.io/vzeman/odoo-mcp-server:latest (or local dev build)
- langchain-agent: our PoC image (FastAPI + LangChain agent)
- telegram-bot: (optional) simple forwarder or omitted if using webhook directly
- redis: redis:7-alpine
- postgres: postgres:15-alpine
- vector-db: (optional) milvus / weaviate / or vector-db-disabled by default

Tips:
- For PoC keep vector-db disabled; add a separate compose file when enabling RAG.
- Keep service ports internal; expose FastAPI for local testing.

## 6. Choice of vector DB for RAG (short exploration)

Options:
- FAISS (local, file-backed): simplest for local PoC; can persist to disk. Good if scale is small.
- SQLite + LlamaIndex/Chroma: lightweight embedded stores.
- Milvus / Weaviate: production-grade, require more infra but integrate well.

Recommendation for PoC: skip vector DB initially. If after PoC we need document retrieval (policy doc lookup, invoices context, contracts), add a local FAISS or Chroma store and persist to disk. For production, use managed Milvus or Weaviate.

## 7. Security and RBAC

- Telegram registration flow should map Telegram ID to Odoo partner via phone + OTP verification.
- Inject user context (role, partner_id, player_ids) into every agent run. Tools must enforce RBAC.
- Do not return raw Odoo errors to end users. Log technical errors to audit logs.

## 8. Observability

- Log agent inputs/outputs to `agent_audit` table (mask sensitive data)
- Use structured logging in FastAPI (JSON), and enable basic request tracing
- Optionally enable LangChain callbacks to log tool calls

## 9. Minimal PoC file list to create

- `doc/dev/mcp-langchain-telegram_bot/odoo_mcp_telegram_langchain_poc_design.md` (this file)
- `langchain_agent.py` — agent wiring
- `mcp_tools.py` — MCP tool wrappers
- `mcp_client.py` — small async client for MCP server
- `main.py` — FastAPI app (/chat, /telegram/webhook, /register)
- `Dockerfile` — for `langchain-agent`
- `docker-compose.poc.yml` — compose file for the PoC
- `requirements.txt` — minimal deps: langchain, openai, fastapi, uvicorn, httpx, redis, asyncpg, sqlalchemy, python-telegram-bot (if needed)
- `README.md` — run & test instructions

## 10. Run steps (local dev)

1. Start MCP server (local or docker)
2. Start Redis and Postgres via docker-compose
3. Set environment variables:

```powershell
# Windows cmd/powershell style
set OPENAI_API_KEY=...
set MCP_SERVER_URL=http://mcp-server:8000
set REDIS_URL=redis://redis:6379/0
set DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres
```

4. Build and run langchain-agent:

```powershell
docker compose -f docker-compose.poc.yml up --build
```

5. Register a test Telegram user (send OTP via console in PoC), then send messages via Telegram or curl `/chat` for testing.

## 11. Open questions / future enhancements

- Do we need RAG and a vector DB for policy/FAQ retrieval? Start without, iterate after usage analysis.
- Which LLM provider for PoC? OpenAI Chat models are easiest; consider local/cheaper models later.
- Should we use polling for Telegram in PoC or webhook? Webhook is more realistic; polling is simpler locally.
- How much conversation history do we want to persist permanently? Memory TTL vs full audit.

---

If you want, I can now scaffold the minimal PoC files (agent, tools, main, requirements, docker-compose) and run a quick syntax check. Which next step would you like me to take?