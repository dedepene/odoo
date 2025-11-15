"""FastAPI service that exposes the LangChain Telegram PoC endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import string
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Bot
from telegram.error import TelegramError
from redis.asyncio import Redis
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from langchain_agent import LangChainTelegramAgent
from mcp_client import MCPClient, MCPClientError
from mcp_tools import MCPTool, build_tools

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Settings(BaseSettings):
    openai_api_key: str = ""
    mcp_server_url: str = "http://mcp-server:8000"
    redis_url: str = "redis://redis:6379/0"
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/postgres"
    llm_model: str = "gpt-4.1-mini"
    session_ttl_seconds: int = 60 * 60 * 24
    otp_ttl_seconds: int = 300
    otp_code_length: int = 6
    telegram_bot_token: str = ""
    # LangSmith configuration for observability
    langsmith_tracing: str = "true"
    langsmith_api_key: str = ""
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "default"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

# Configure LangSmith tracing for observability
if settings.langsmith_tracing.lower() == "true" and settings.langsmith_api_key:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    LOGGER.info(
        "LangSmith tracing enabled for project: %s at %s",
        settings.langsmith_project,
        settings.langsmith_endpoint,
    )
else:
    LOGGER.info("LangSmith tracing disabled or API key not provided")


class Base(DeclarativeBase):
    pass


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    odoo_partner_id: Mapped[Optional[int]] = mapped_column(Integer)
    odoo_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    role: Mapped[Optional[str]] = mapped_column(String(50))
    player_ids: Mapped[Optional[List[int]]] = mapped_column(ARRAY(Integer))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentAudit(Base):
    __tablename__ = "agent_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
mcp_client = MCPClient(settings.mcp_server_url)
TOOLS: List[MCPTool] = build_tools(mcp_client)
agent = LangChainTelegramAgent(
    tools=TOOLS,
    redis_url=settings.redis_url,
    session_ttl=settings.session_ttl_seconds,
    model=settings.llm_model,
    api_key=settings.openai_api_key or None,
    system_prompt=(
        "You are the tennis academy assistant. Reflect the academy voice, be concise, and never"
        " speculate. Only answer with data you have or by calling tools.\n\n"
        "CRITICAL RULES FOR ABSENCE REPORTING:\n"
        "1. When a user wants to report an absence, ALWAYS use the 'report_absence' tool.\n"
        "2. If user mentions a DATE (e.g., 'на 14 ноември', 'on November 14'), use the 'date' parameter in report_absence.\n"
        "3. If the tool asks for clarification about which sessions, help the user understand the options and "
        "then call report_absence again with the specific session_id(s) they choose.\n"
        "4. NEVER create absence records directly using create_record - always use report_absence tool.\n\n"
        "IMPORTANT: When search_sessions returns results, they include session_id and player_id values "
        "in the format 'session_id=123' and 'player_id=456'. Extract these IDs directly from the text "
        "to use with report_absence or other tools. DO NOT call search_sessions again just to get IDs."
    ),
)

telegram_bot: Optional[Bot] = None


async def ensure_database_ready(max_retries: int = 30, delay_seconds: float = 1.0) -> None:
    for attempt in range(1, max_retries + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as exc:  # pylint: disable=broad-except
            if attempt == max_retries:
                LOGGER.error("Database connection failed after %s attempts: %s", attempt, exc)
                raise
            LOGGER.warning(
                "Database not ready (attempt %s/%s): %s", attempt, max_retries, exc
            )
            await asyncio.sleep(delay_seconds)
        else:
            return


class OTPPayload(BaseModel):
    phone: str
    username: Optional[str]


class OTPStore:
    def __init__(self, client: Redis, ttl_seconds: int, code_length: int) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._code_length = code_length

    async def issue(self, telegram_id: int, payload: OTPPayload) -> str:
        token = "".join(secrets.choice(string.digits) for _ in range(self._code_length))
        data = payload.model_dump()
        data["code"] = token
        key = self._key(telegram_id)
        await self._client.set(key, json.dumps(data), ex=self._ttl)
        LOGGER.info("OTP issued for %s: %s", telegram_id, token)
        return token

    async def verify(self, telegram_id: int, code: str) -> Optional[OTPPayload]:
        raw = await self._client.get(self._key(telegram_id))
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("code") != code:
            return None
        await self._client.delete(self._key(telegram_id))
        return OTPPayload(phone=data.get("phone"), username=data.get("username"))

    def _key(self, telegram_id: int) -> str:
        return f"otp:{telegram_id}"


otp_store = OTPStore(redis_client, settings.otp_ttl_seconds, settings.otp_code_length)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def user_context(user: TelegramUser) -> Dict[str, Any]:
    return {
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "current_datetime": datetime.now().isoformat(),
        "telegram_id": user.telegram_id,
        "role": user.role,
        "player_ids": user.player_ids,
        "odoo_partner_id": user.odoo_partner_id,
        "odoo_user_id": user.odoo_user_id,
        "username": user.username,
        "phone": user.phone,
    }


async def fetch_user(session: AsyncSession, telegram_id: int) -> Optional[TelegramUser]:
    result = await session.execute(
        select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def upsert_user(
    session: AsyncSession,
    telegram_id: int,
    payload: "VerifyOtpRequest",
    otp_payload: OTPPayload,
) -> TelegramUser:
    existing = await fetch_user(session, telegram_id)
    now = datetime.utcnow()
    if existing:
        existing.phone = otp_payload.phone
        existing.username = otp_payload.username or existing.username
        existing.role = payload.role
        existing.odoo_partner_id = payload.odoo_partner_id
        existing.odoo_user_id = payload.odoo_user_id
        existing.player_ids = payload.player_ids
        existing.verified_at = now
        await session.flush()
        return existing
    user = TelegramUser(
        telegram_id=telegram_id,
        phone=otp_payload.phone,
        username=otp_payload.username,
        role=payload.role,
        odoo_partner_id=payload.odoo_partner_id,
        odoo_user_id=payload.odoo_user_id,
        player_ids=payload.player_ids,
        verified_at=now,
    )
    session.add(user)
    await session.flush()
    return user


async def log_audit(
    session: AsyncSession,
    *,
    telegram_id: int,
    session_id: str,
    prompt: str,
    response: str,
) -> None:
    audit = AgentAudit(
        telegram_id=telegram_id,
        session_id=session_id,
        prompt=prompt,
        response=response,
    )
    session.add(audit)
    await session.flush()


class ChatRequest(BaseModel):
    telegram_id: int
    message: str
    file_data: Optional[str] = Field(None, description="Base64 encoded attachment data")


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class ChatWebhookResponse(BaseModel):
    status: str


class SendOtpRequest(BaseModel):
    telegram_id: int
    phone: str
    username: Optional[str] = None


class SendOtpResponse(BaseModel):
    status: str


class VerifyOtpRequest(BaseModel):
    telegram_id: int
    otp: str
    role: str
    odoo_partner_id: Optional[int] = None
    odoo_user_id: Optional[int] = None
    player_ids: Optional[List[int]] = None


class VerifyOtpResponse(BaseModel):
    status: str


app = FastAPI(title="LangChain Telegram Agent PoC", version="0.1.0")

# Create a router that will be mounted under /bot
bot_router = APIRouter()


@app.on_event("startup")
async def on_startup() -> None:
    global telegram_bot
    await ensure_database_ready()
    try:
        await mcp_client.ping()
    except MCPClientError as exc:
        LOGGER.warning("MCP server ping failed: %s", exc)
    if not settings.openai_api_key:
        LOGGER.warning("OPENAI_API_KEY is not set; agent calls will fail until configured")
    if settings.telegram_bot_token:
        telegram_bot = Bot(token=settings.telegram_bot_token)
    else:
        LOGGER.warning("TELEGRAM_BOT_TOKEN is not set; webhook replies will be skipped")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await mcp_client.close()
    await redis_client.close()
    await redis_client.wait_closed()


@app.get("/healthz")
@bot_router.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/webhook/test")
@bot_router.get("/webhook/test")
async def webhook_test() -> Dict[str, Any]:
    """Test endpoint to verify the service is reachable."""
    return {
        "status": "ok",
        "message": "Webhook endpoint is reachable",
        "telegram_bot_configured": telegram_bot is not None,
    }


@app.post("/chat", response_model=ChatResponse)
@bot_router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    user = await fetch_user(session, payload.telegram_id)
    if not user or not user.verified_at:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not verified")
    session_id = f"telegram:{payload.telegram_id}"
    agent_result = await agent.arun(
        session_id=session_id,
        user_context=user_context(user),
        message=payload.message,
    )
    reply = agent_result.get("output", "")
    await log_audit(
        session,
        telegram_id=payload.telegram_id,
        session_id=session_id,
        prompt=payload.message,
        response=reply,
    )
    await session.commit()
    return ChatResponse(reply=reply, session_id=session_id)


@app.post("/telegram/webhook", response_model=ChatWebhookResponse)
@bot_router.post("/telegram/webhook", response_model=ChatWebhookResponse)
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ChatWebhookResponse:
    LOGGER.info("=== TELEGRAM WEBHOOK HIT - Raw request received ===")
    data = await request.json()
    LOGGER.info("Full webhook payload: %s", json.dumps(data, indent=2))
    
    # Handle regular text messages
    message = data.get("message") or {}
    LOGGER.info("Received Telegram webhook message: %s", message)
    text = message.get("text")
    if not text:
        return ChatWebhookResponse(status="ignored")
    chat = message.get("chat", {})
    telegram_id = chat.get("id")
    if telegram_id is None:
        LOGGER.error("Missing telegram_id in webhook payload")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing telegram id")
    LOGGER.info("Processing message from telegram_id: %s", telegram_id)
    user = await fetch_user(session, telegram_id)
    if not user:
        LOGGER.warning("User not found for telegram_id: %s", telegram_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not verified")
    if not user.verified_at:
        LOGGER.warning("User %s exists but not verified (verified_at is None)", telegram_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not verified")
    session_id = f"telegram:{telegram_id}"
    agent_result = await agent.arun(
        session_id=session_id,
        user_context=user_context(user),
        message=text,
    )
    reply = agent_result.get("output", "")
    
    await log_audit(
        session,
        telegram_id=telegram_id,
        session_id=session_id,
        prompt=text,
        response=reply,
    )
    await session.commit()
    await send_telegram_message(telegram_id, reply)
    LOGGER.info("Processed Telegram message for %s", telegram_id)
    return ChatWebhookResponse(status="processed")


@app.post("/register/send_otp", response_model=SendOtpResponse)
@bot_router.post("/register/send_otp", response_model=SendOtpResponse)
async def send_otp(payload: SendOtpRequest) -> SendOtpResponse:
    otp_payload = OTPPayload(phone=payload.phone, username=payload.username)
    await otp_store.issue(payload.telegram_id, otp_payload)
    return SendOtpResponse(status="sent")


@app.post("/register/verify", response_model=VerifyOtpResponse)
@bot_router.post("/register/verify", response_model=VerifyOtpResponse)
async def verify_otp(
    payload: VerifyOtpRequest,
    session: AsyncSession = Depends(get_session),
) -> VerifyOtpResponse:
    otp_payload = await otp_store.verify(payload.telegram_id, payload.otp)
    if not otp_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")
    user = await upsert_user(session, payload.telegram_id, payload, otp_payload)
    await session.commit()
    LOGGER.info("User %s verified with role %s", user.telegram_id, user.role)
    return VerifyOtpResponse(status="verified")


@app.exception_handler(MCPClientError)
async def handle_mcp_error(_: Request, exc: MCPClientError) -> JSONResponse:
    LOGGER.error("MCP error: %s", exc)
    return JSONResponse(status_code=502, content={"detail": "Upstream MCP failure"})


async def send_telegram_message(chat_id: int, text: str) -> None:
    if not text:
        LOGGER.debug("Skipping empty Telegram reply for chat %s", chat_id)
        return
    if not telegram_bot:
        LOGGER.warning("Telegram bot token missing; cannot send reply to %s", chat_id)
        return
    try:
        await telegram_bot.send_message(chat_id=chat_id, text=text)
    except TelegramError as exc:
        LOGGER.error("Failed to send Telegram message to %s: %s", chat_id, exc)



# Include all routes under /bot prefix as well
app.include_router(bot_router, prefix="/bot")
