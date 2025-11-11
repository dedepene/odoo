# LangChain Telegram PoC – Handover Notes

Date: 2025-11-07
Owner: GitHub Copilot (GPT-5-Codex)

## Delivered scope
- Scaffolded FastAPI service (`AI-agent/main.py`) exposing `/chat`, `/telegram/webhook`, `/register/send_otp`, `/register/verify`, and `/healthz`.
- Implemented MCP client (`mcp_client.py`) and LangChain tool wrappers with RBAC guards (`mcp_tools.py`).
- Wired LangChain agent (`langchain_agent.py`) with Redis-backed `RedisChatMessageHistory` and contextual prompting.
- Added Docker assets (`Dockerfile`, `docker-compose.poc.yml`) and dependency lock (`requirements.txt`).
- Authored developer README with run instructions (`AI-agent/README.md`).
- Enabled outbound Telegram replies via Bot API when `TELEGRAM_BOT_TOKEN` is configured.

## Runtime architecture
- **FastAPI app** manages HTTP interfaces, OTP lifecycle, persistence, and pushes responses to Telegram chats when `TELEGRAM_BOT_TOKEN` is configured.
- **LangChain agent** uses `create_tool_calling_agent` + `AgentExecutor` with Redis message history to preserve chat context per Telegram session.
- **MCP tools** (`SearchSessions`, `ReportAbsence`, `GetInvoices`, `GetContactInfo`) enforce role-based access via in-process guards before invoking JSON-RPC `tools.invoke` on the MCP server.
- **Persistence**: PostgreSQL (SQLAlchemy async ORM) for `telegram_users` and `agent_audit`; Redis for chat memory and OTP tokens.
- **Containers**: Compose stack bundles Redis, Postgres, MCP server (`ghcr.io/vzeman/odoo-mcp-server:latest`), and the agent service.

## Configuration
Environment variables (defaults in `Settings`):
- `OPENAI_API_KEY` – required for OpenAI Chat model access.
- `MCP_SERVER_URL`, `REDIS_URL`, `DATABASE_URL`, `LLM_MODEL`.
- `SESSION_TTL_SECONDS`, `OTP_TTL_SECONDS`, `OTP_CODE_LENGTH` tune Redis-backed histories and registration flows.
- `TELEGRAM_BOT_TOKEN` enables outbound chat replies (required for webhook-driven conversations).

## Operation / observability
- OTP codes logged via `LOGGER.info` to console for PoC simplicity.
- Agent prompts/responses persisted to `agent_audit` for traceability.
- Startup pings MCP server and warns if OpenAI key missing.
- Shutdown closes HTTP and Redis resources cleanly.

## Follow-ups
1. **Testing** – Add pytest coverage for registration, chat happy-path, and MCP error propagation.
2. **Security** – Replace console OTP logging with secure delivery and add request authentication (e.g., shared secret for Telegram webhook).
3. **LLM provider** – Permit alternative providers (Azure OpenAI, Anthropic) via configurable LangChain model factory.
4. **Observability** – Integrate LangSmith callbacks or structured logging for tool traces.
5. **Deployment** – Add CI workflow, production-ready Docker image publishing, and secrets management docs.

## References
- Odoo MCP design doc: `doc/dev/mcp-langchain-telegram_bot/odoo_mcp_telegram_langchain_poc_design.md`
- LangChain v1.0 overview consulted via LangChain MCP documentation search.
