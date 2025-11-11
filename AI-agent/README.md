# LangChain + MCP + Telegram PoC

This directory hosts the proof-of-concept FastAPI service that bridges a Telegram bot with LangChain tools backed by the Odoo MCP server. The implementation follows the design documented in `doc/dev/mcp-langchain-telegram_bot/odoo_mcp_telegram_langchain_poc_design.md`.

## Components
- `main.py` – FastAPI application with `/chat`, `/telegram/webhook`, and registration endpoints.
- `langchain_agent.py` – LangChain agent wiring with Redis-backed conversation history.
- `mcp_tools.py` / `mcp_client.py` – Tool and client abstractions for MCP JSON-RPC calls.
- `docker-compose.poc.yml` – Local stack with Postgres, Redis, MCP server, and the agent service.
- `Dockerfile` – Container build for the agent.
- `requirements.txt` – Python dependencies pinned for reproducible builds.

## Prerequisites
- Docker and Docker Compose v2
- An OpenAI API key (or alternative LangChain-compatible model credentials)
- Access to the Odoo instance exposed by the MCP server

## Quick start
```cmd
cd AI-agent
set OPENAI_API_KEY=sk-...
docker compose -f docker-compose.poc.yml up --build
```

The FastAPI app listens on `http://localhost:8000`. Redis, Postgres, and the MCP server are reachable within the compose network. Adjust `.env` or environment variables to target other deployments.

## Local development
```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Environment variables (default values shown):
```
MCP_SERVER_URL=http://mcp-server:8000
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
LLM_MODEL=gpt-4.1-mini
SESSION_TTL_SECONDS=86400
TELEGRAM_BOT_TOKEN=<set to enable outbound replies>
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-langsmith-api-key>
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=<your-project-name>
```

## LangSmith Observability
This PoC is fully instrumented with LangSmith for tracing and observability. When properly configured, all agent interactions, tool calls, and LLM invocations are automatically logged to your LangSmith project.

### Configuration
1. Sign up for LangSmith at https://smith.langchain.com
2. Create an API key from your settings page
3. Set the following environment variables in your `.env` file:
   - `LANGSMITH_TRACING=true` - Enables tracing
   - `LANGSMITH_API_KEY=<your-key>` - Your LangSmith API key
   - `LANGSMITH_ENDPOINT=https://api.smith.langchain.com` - LangSmith API endpoint
   - `LANGSMITH_PROJECT=<project-name>` - Project name for organizing traces

### What Gets Traced
- Every agent invocation with full conversation context
- All MCP tool calls with input parameters and outputs
- LLM calls with prompts, completions, and token usage
- Error traces for debugging failed operations
- Session history and user context

### Viewing Traces
Once configured, navigate to your LangSmith dashboard to view:
- Real-time trace logs of all agent interactions
- Performance metrics and latency breakdowns
- Token usage and cost tracking
- Debugging information for failed requests

Visit https://docs.smith.langchain.com for detailed documentation on analyzing traces and setting up alerts.

## API overview
- `POST /chat` accepts `{telegram_id, message}` and returns the agent reply.
- `POST /telegram/webhook` processes Telegram updates when the bot is configured for webhooks and responds by sending a message back to the originating chat via the Telegram Bot API.
- `POST /register/send_otp` issues one-time codes (logged to console for the PoC).
- `POST /register/verify` completes registration and stores user metadata.
- `GET /healthz` returns service health.

## Database schema
Tables are created automatically on startup:
- `telegram_users` – Maps Telegram IDs to Odoo entities and roles.
- `agent_audit` – Stores prompts and responses for observability.

## Next steps
- Integrate with production OTP delivery (SMS/email) instead of console logging.
- Extend MCP tools with richer validation and telemetry.
- Add tests covering OTP flow, RBAC, and MCP error handling.
