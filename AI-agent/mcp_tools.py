"""LangChain tool wrappers around the Odoo MCP server."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Type

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from langchain_core.tools import BaseTool

from mcp_client import MCPClient, MCPClientError

LOGGER = logging.getLogger(__name__)


class _ToolContextError(RuntimeError):
    """Raised when a tool is executed without a bound user context."""


class MCPTool(BaseTool):
    """Base class that binds the MCP client and enforces RBAC."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    tool_name: str
    description: str
    args_schema: Type[BaseModel]
    client: MCPClient = Field(repr=False)
    allowed_roles: Set[str] = Field(default_factory=set, repr=False)
    _user_context: Optional[Dict[str, Any]] = PrivateAttr(default=None)

    def __init__(
        self,
        client: MCPClient,
        *,
        allowed_roles: Optional[Iterable[str]] = None,
        **kwargs: Any,
    ) -> None:
        roles = set(allowed_roles or [])
        super().__init__(client=client, allowed_roles=roles, **kwargs)

    def set_user_context(self, context: Dict[str, Any]) -> None:
        self._user_context = context

    def clear_user_context(self) -> None:
        self._user_context = None

    def _ensure_authorized(self) -> None:
        if not self.allowed_roles:
            return
        if not self._user_context:
            raise _ToolContextError("User context not set for tool execution")
        role = self._user_context.get("role")
        if role not in self.allowed_roles:
            raise PermissionError(
                f"Role '{role}' is not allowed to execute tool '{self.tool_name}'"
            )

    def _normalize_arguments(self, **kwargs: Any) -> Dict[str, Any]:
        return {name: value for name, value in kwargs.items() if value is not None}

    def _coerce_result(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False)

    async def _call_tool_json(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Invoke a tool and decode JSON responses when possible."""

        raw = await self.client.call_tool(tool_name, params)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
        return raw

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("Synchronous execution is not supported; use async mode")

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        self._ensure_authorized()
        params = self._normalize_arguments(**kwargs)
        try:
            result = await self.client.call_tool(self.tool_name, params)
        except MCPClientError as exc:
            raise RuntimeError(str(exc)) from exc
        return self._coerce_result(result)


class SearchSessionsParams(BaseModel):
    player_name: Optional[str] = Field(None, description="Filter by player display name")
    date_from: Optional[str] = Field(None, description="ISO date lower bound")
    date_to: Optional[str] = Field(None, description="ISO date upper bound")
    coach_id: Optional[int] = Field(None, description="Only sessions for a coach")
    session_type: Optional[str] = Field(
        None, 
        description="Filter by session type: 'tennis_group' (Tennis Skills Group), "
                    "'physical_group' (Physical Activities Group), "
                    "'tennis_individual' (Tennis Skills Individual), "
                    "'physical_individual' (Physical Activities Individual)"
    )


class ReportAbsenceParams(BaseModel):
    session_id: Optional[int] = Field(None, description="Direct session identifier (use this OR date)")
    player_id: Optional[int] = Field(None, description="Player ID - normally resolved from player_name")
    player_name: Optional[str] = Field(None, description="Player display name as provided by the parent")
    date: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD) used to locate sessions")
    confirm_all: Optional[bool] = Field(None, description="Set to true after the parent confirms reporting all sessions on that date")
    reason: Optional[str] = Field(None, description="Optional note from the parent")


class GetInvoicesParams(BaseModel):
    partner_id: Optional[int] = Field(None, description="Partner to query invoices for")
    status: Optional[str] = Field(None, description="Invoice status filter")


class GetContactInfoParams(BaseModel):
    player_id: int = Field(..., description="Player identifier to fetch guardian contact")


class SearchSessionsTool(MCPTool):
    name: str = "search_sessions"
    description: str = (
        "Use to list upcoming academy sessions for the authenticated user. "
        "Supports filtering by player name, date range, coach, and session type. "
        "Session types include: Tennis Skills (Group/Individual) and Physical Activities (Group/Individual). "
        "If user mentions a specific activity type like 'tennis', 'physical', or 'individual'/'group', "
        "use the session_type parameter to filter accordingly."
    )
    args_schema: Type[BaseModel] = SearchSessionsParams
    tool_name: str = "search_sessions"

    @staticmethod
    def _build_or_expression(conditions: List[Any]) -> List[Any]:
        """Build a flattened Odoo domain OR expression.
        
        For multiple conditions, returns: ['|', cond1, '|', cond2, cond3]
        For two conditions: ['|', cond1, cond2]
        For one condition: [cond1]
        """
        filtered = [cond for cond in conditions if cond]
        if not filtered:
            return []
        if len(filtered) == 1:
            return filtered
        
        # Build prefix OR operators
        result: List[Any] = []
        for i in range(len(filtered) - 1):
            result.append('|')
        result.extend(filtered)
        return result

    @staticmethod
    def _format_datetime(value: Optional[str]) -> str:
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _format_session_type(session_type: Optional[str]) -> str:
        """Convert session_type code to human-readable label."""
        if not session_type:
            return 'Unknown'
        type_map = {
            'tennis_group': 'Tennis Skills (Group)',
            'physical_group': 'Physical Activities (Group)',
            'tennis_individual': 'Tennis Skills (Individual)',
            'physical_individual': 'Physical Activities (Individual)',
        }
        return type_map.get(session_type, session_type)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:  # noqa: D401
        self._ensure_authorized()
        context = self._user_context or {}
        player_ids: List[int] = context.get("player_ids") or []
        if not player_ids:
            raise RuntimeError("No linked players found for this account.")

        player_name_filter = (kwargs.get("player_name") or "").strip().lower() or None
        players_payload = await self._call_tool_json(
            "get_record",
            {
                "model": "academy.player",
                "ids": player_ids,
                "fields": [
                    "id",
                    "name",
                    "skill_group_id",
                ],
            },
        )
        if not isinstance(players_payload, dict) or "records" not in players_payload:
            raise RuntimeError("Unexpected response while loading player details.")

        players: List[Dict[str, Any]] = players_payload["records"]
        
        # Get all player names for helpful error messages
        all_player_names: List[str] = [p.get("name", "") for p in players if p.get("name")]
        
        if player_name_filter:
            filtered_players = [
                player
                for player in players
                if player.get("name") and player_name_filter in player["name"].lower()
            ]
            if not filtered_players:
                if all_player_names:
                    names_list = ", ".join(all_player_names)
                    return (
                        f"❌ ГРЕШКА: Играч с име '{player_name_filter}' не е намерен във вашия акаунт.\n\n"
                        f"Можете да преглеждате тренировки и да отбелязвате отсъствия САМО за вашите собствени деца:\n"
                        f"• {names_list}\n\n"
                        f"Ако искате информация за друг играч, моля свържете се с администрацията на академията."
                    )
                else:
                    return "No players are linked to your account."
            players = filtered_players
        
        if not players:
            return "No players are linked to your account."

        # GUARDRAIL: Ensure date_from is never before today when searching for "next" sessions
        # Get the current date from user context (if available) or use today
        today_str = context.get("current_date") or date.today().isoformat()
        today_date = date.fromisoformat(today_str)
        
        start_date_param = kwargs.get("date_from")
        if start_date_param:
            try:
                start_date_obj = date.fromisoformat(start_date_param)
                # If requested date is in the past, use today instead
                if start_date_obj < today_date:
                    LOGGER.info(
                        "Guardrail: Adjusted date_from from %s to %s (today) to prevent showing past sessions",
                        start_date_param, today_str
                    )
                    start_date = today_str
                else:
                    start_date = start_date_param
            except (ValueError, TypeError):
                # If parsing fails, use today
                start_date = today_str
        else:
            start_date = today_str
            
        end_date = kwargs.get("date_to")
        coach_id = kwargs.get("coach_id")
        session_type = kwargs.get("session_type")
        limit = kwargs.get("limit") or 10

        aggregated: Dict[int, Dict[str, Any]] = {}
        player_id_map: Dict[str, int] = {}  # Map player names to IDs for report_absence
        
        for player in players:
            player_id = player.get("id")
            if not player_id:
                continue
            player_name = player.get("name")
            if player_name:
                player_id_map[player_name] = player_id
                
            skill_group = player.get("skill_group_id")
            skill_group_id = skill_group[0] if isinstance(skill_group, list) else None

            base_conditions: List[Any] = [
                ("date", ">=", start_date),
                ("state", "in", ["planned", "confirmed"]),
            ]
            if end_date:
                base_conditions.append(("date", "<=", end_date))
            if coach_id:
                base_conditions.append(("coach_id", "=", coach_id))
            if session_type:
                base_conditions.append(("session_type", "=", session_type))

            or_conditions: List[Any] = [("player_ids", "in", [player_id])]
            if skill_group_id:
                or_conditions.append(("skill_group_id", "=", skill_group_id))
                or_conditions.append(("skill_group_ids", "in", [skill_group_id]))

            or_expr = self._build_or_expression(or_conditions)

            domain: List[Any] = base_conditions.copy()
            if or_expr:
                # Flatten the OR expression into the domain
                if isinstance(or_expr, list):
                    domain.extend(or_expr)
                else:
                    domain.append(or_expr)

            LOGGER.debug(
                "Guardian session domain (player=%s): %s", player_id, domain
            )

            if not domain:
                continue

            session_payload = await self._call_tool_json(
                "search_records",
                {
                    "model": "academy.session.occurrence",
                    "domain": domain,
                    "fields": [
                        "id",
                        "name",
                        "date",
                        "start_datetime",
                        "session_type",
                        "skill_group_id",
                        "coach_id",
                    ],
                    "limit": limit,
                    "order": "date,start_datetime",
                },
            )
            records = []
            if isinstance(session_payload, dict):
                records = session_payload.get("records", [])
            elif isinstance(session_payload, list):
                records = session_payload

            for record in records:
                occ_id = record.get("id")
                if not occ_id:
                    continue
                entry = aggregated.setdefault(
                    occ_id,
                    {
                        **record,
                        "player_names": set(),
                    },
                )
                player_name = player.get("name")
                if player_name:
                    entry["player_names"].add(player_name)

        if not aggregated:
            return "No upcoming sessions match the requested filters."

        sessions = sorted(
            aggregated.values(),
            key=lambda item: (
                item.get("start_datetime") or item.get("date") or "",
                item.get("id"),
            ),
        )

        lines: List[str] = []
        for session in sessions:
            start_value = session.get("start_datetime") or session.get("date")
            when_label = self._format_datetime(start_value)
            if not when_label:
                when_label = session.get("date", "Unknown date")
            
            # Get session type
            session_type_code = session.get("session_type")
            session_type_label = self._format_session_type(session_type_code)
            
            group = session.get("skill_group_id")
            group_name = group[1] if isinstance(group, list) and len(group) > 1 else None
            coach = session.get("coach_id")
            coach_name = coach[1] if isinstance(coach, list) and len(coach) > 1 else "Unassigned"
            player_names_set = session.get("player_names", set())
            title = session.get("name") or group_name or "Session"
            session_id = session.get("id")
            
            # Build player list with IDs for easy extraction by LLM
            player_info_list = []
            for pname in sorted(player_names_set):
                pid = player_id_map.get(pname)
                if pid:
                    player_info_list.append(f"{pname} (player_id={pid})")
                else:
                    player_info_list.append(pname)
            player_info = ", ".join(player_info_list) if player_info_list else "N/A"
            
            # Format with session_id and player_ids for report_absence tool
            lines.append(
                f"{when_label} – {title} [{session_type_label}] "
                f"(Coach: {coach_name}, session_id={session_id}) · Players: {player_info}"
            )

        return "Upcoming sessions:\n" + "\n".join(lines[:limit])


class ReportAbsenceTool(MCPTool):
    name: str = "report_absence"
    return_direct: bool = False
    requires_confirmation: bool = True
    description: str = (
        "Create session absences. Pass player_name with date or session_id. "
        "If multiple sessions are returned, ask the parent to confirm and call again with confirm_all=True."
    )
    tool_name: str = "report_absence"
    args_schema: Type[BaseModel] = ReportAbsenceParams

    @staticmethod
    def _derive_reason_code(reason: Optional[str]) -> str:
        if not reason:
            return "other"
        lowered = reason.lower()
        if any(keyword in lowered for keyword in ("болест", "болен", "illness", "sick")):
            return "illness"
        if any(keyword in lowered for keyword in ("травма", "контуз", "injury")):
            return "injury"
        if any(keyword in lowered for keyword in ("семей", "family")):
            return "family"
        if any(keyword in lowered for keyword in ("училищ", "school")):
            return "school"
        if any(keyword in lowered for keyword in ("ваканц", "почивк", "vacation", "holiday")):
            return "vacation"
        return "other"

    async def _resolve_player(
        self,
        player_id: Optional[int],
        player_name: Optional[str],
    ) -> tuple[int, str]:
        """Resolve the player id and return (id, display_name)."""

        context_ids = self._user_context.get("player_ids", []) if self._user_context else []
        if not context_ids:
            raise RuntimeError("No players linked to your account")

        player_records: List[Dict[str, Any]] = []
        payload = await self._call_tool_json(
            "search_records",
            {
                "model": "academy.player",
                "domain": [("id", "in", context_ids)],
                "fields": ["id", "name"],
            },
        )
        if isinstance(payload, dict):
            player_records = payload.get("records", [])
        elif isinstance(payload, list):
            player_records = payload

        if not player_records:
            raise RuntimeError("No players available for this user")

        if player_id:
            for record in player_records:
                if record.get("id") == player_id:
                    return player_id, record.get("name") or f"Играч {player_id}"
            raise RuntimeError("Player is not linked to this account")

        if not player_name:
            raise RuntimeError("Player name is required when player_id is absent")

        target = player_name.strip().lower()
        matches = [
            record
            for record in player_records
            if record.get("name") and target in record["name"].lower()
        ]

        if not matches:
            available = ", ".join(filter(None, (p.get("name") for p in player_records)))
            raise RuntimeError(
                f"❌ ГРЕШКА: Играч с име '{player_name}' не е намерен във вашия акаунт.\n\n"
                f"Можете да отбелязвате отсъствия САМО за вашите собствени деца:\n"
                f"• {available}\n\n"
                f"Ако искате да отбележите отсъствие за друг играч, моля свържете се с администрацията на академията."
            )
        if len(matches) > 1:
            names = ", ".join(filter(None, (p.get("name") for p in matches)))
            raise RuntimeError(
                f"More than one player matches '{player_name}': {names}. Please use full name."
            )

        record = matches[0]
        return record["id"], record.get("name") or player_name

    async def _absence_exists(self, session_id: int, player_id: int) -> bool:
        payload = await self._call_tool_json(
            "search_records",
            {
                "model": "academy.session.absence",
                "domain": [
                    ("occurrence_id", "=", session_id),
                    ("player_id", "=", player_id),
                    ("state", "in", ["reported", "acknowledged"]),
                ],
                "fields": ["id"],
                "limit": 1,
            },
        )
        if isinstance(payload, dict):
            return bool(payload.get("records"))
        if isinstance(payload, list):
            return bool(payload)
        return False

    async def _record_session_absence(
        self,
        session_id: int,
        player_id: int,
        reason: Optional[str],
    ) -> str:
        if await self._absence_exists(session_id, player_id):
            return "exists"

        try:
            await self._call_tool_json(
                "create_record",
                {
                    "model": "academy.session.absence",
                    "values": {
                        "occurrence_id": session_id,
                        "player_id": player_id,
                        "reason_code": self._derive_reason_code(reason),
                        "reason_note": reason or "",
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001 - need to inspect MCP client errors
            if isinstance(exc, MCPClientError) and "already exists" in str(exc).lower():
                return "exists"
            raise
        return "created"

    @staticmethod
    def _format_session_line(session: Dict[str, Any]) -> str:
        start_value = session.get("start_datetime") or session.get("date")
        when = SearchSessionsTool._format_datetime(start_value) or session.get("date", "")
        session_type = SearchSessionsTool._format_session_type(session.get("session_type"))
        group = session.get("skill_group_id")
        title = session.get("name")
        if isinstance(group, list) and len(group) > 1:
            title = title or group[1]
        session_id = session.get("id")
        return f"- {when} – {title or 'Тренировка'} ({session_type}, session_id={session_id})"

    async def _get_sessions_for_date(
        self, player_id: int, target_date: str
    ) -> List[Dict[str, Any]]:
        """Get all sessions for a player on a specific date."""
        context = self._user_context or {}
        
        # First, get the player's skill group
        player_payload = await self._call_tool_json(
            "get_record",
            {
                "model": "academy.player",
                "ids": [player_id],
                "fields": ["id", "skill_group_id"],
            },
        )
        
        skill_group_id = None
        if isinstance(player_payload, dict):
            records = player_payload.get("records", [])
            if records:
                skill_group = records[0].get("skill_group_id")
                if isinstance(skill_group, list) and len(skill_group) > 0:
                    skill_group_id = skill_group[0]
        
        # Build domain for sessions on the specified date
        domain = [
            ("date", "=", target_date),
            ("state", "in", ["planned", "confirmed"]),
        ]
        
        # Add OR conditions for player assignment
        or_conditions = []
        or_conditions.append(("player_ids", "in", [player_id]))
        
        if skill_group_id:
            or_conditions.append(("skill_group_id", "=", skill_group_id))
            # Also check skill_group_ids for multi-group sessions
            or_conditions.append(("skill_group_ids", "in", [skill_group_id]))
        
        # Build the OR expression properly
        if len(or_conditions) == 1:
            domain.append(or_conditions[0])
        elif len(or_conditions) == 2:
            domain.extend(["|", or_conditions[0], or_conditions[1]])
        elif len(or_conditions) == 3:
            # For 3 conditions: |, |, cond1, cond2, cond3
            domain.extend(["|", "|", or_conditions[0], or_conditions[1], or_conditions[2]])
        
        # Search for sessions on the specified date
        session_payload = await self._call_tool_json(
            "search_records",
            {
                "model": "academy.session.occurrence",
                "domain": domain,
                "fields": [
                    "id",
                    "name",
                    "date",
                    "start_datetime",
                    "session_type",
                    "skill_group_id",
                    "coach_id",
                ],
                "order": "start_datetime,id",
            },
        )
        
        records = []
        if isinstance(session_payload, dict):
            records = session_payload.get("records", [])
        elif isinstance(session_payload, list):
            records = session_payload
            
        return records

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        self._ensure_authorized()

        session_id = kwargs.get("session_id")
        player_id = kwargs.get("player_id")
        player_name = kwargs.get("player_name")
        date_param = kwargs.get("date")
        confirm_all = bool(kwargs.get("confirm_all"))
        reason = kwargs.get("reason")

        # Resolve player - propagate errors clearly to user
        try:
            player_id, player_label = await self._resolve_player(player_id, player_name)
        except MCPClientError as exc:
            return f"❌ Не успях да заредя информация за играчите. Моля опитайте отново след малко. Грешка: {exc}"
        except RuntimeError as exc:
            return str(exc)

        # Process absence recording
        try:
            if session_id:
                status = await self._record_session_absence(session_id, player_id, reason)
                if status == "created":
                    reason_info = f" Причина: {reason}." if reason else ""
                    return (
                        f"✓ Отбелязах отсъствието на {player_label} за тренировка {session_id}.{reason_info}"
                    )
                return (
                    f"✓ Отсъствието вече е записано за {player_label} в тренировка {session_id}."
                )

            if not date_param:
                raise RuntimeError("Provide either session_id or date when reporting absence")

            sessions = await self._get_sessions_for_date(player_id, date_param)
            if not sessions:
                return f"Няма тренировки за {player_label} на {date_param}."

            # AUTOMATIC CONFIRMATION: If only 1 session on the date, record immediately
            # MANUAL CONFIRMATION REQUIRED: Only if multiple sessions and confirm_all not set
            if len(sessions) == 1:
                # Single session - record immediately without asking
                sess_id = sessions[0].get("id")
                if not sess_id:
                    raise RuntimeError("Тренировката няма валиден ID")
                
                result = await self._record_session_absence(sess_id, player_id, reason)
                if result == "created":
                    reason_info = f" Причина: {reason}." if reason else ""
                    return f"✓ Отбелязах отсъствието на {player_label} на {date_param}.{reason_info}"
                return f"✓ Отсъствието вече беше отбелязано за {player_label} на {date_param}."
            
            # Multiple sessions - need confirmation
            if confirm_all:
                # Parent confirmed - record all sessions
                created = 0
                existing = 0
                for session in sessions:
                    sess_id = session.get("id")
                    if not sess_id:
                        continue
                    result = await self._record_session_absence(sess_id, player_id, reason)
                    if result == "created":
                        created += 1
                    elif result == "exists":
                        existing += 1

                total = len(sessions)
                if created:
                    reason_info = f" Причина: {reason}." if reason else ""
                    return (
                        f"✓ Отбелязах отсъствие за всички тренировки на {date_param} за {player_label}.{reason_info}"
                    )
                if existing == total:
                    return (
                        f"✓ Отсъствията вече бяха отбелязани за всички тренировки на {date_param} за {player_label}."
                    )
                raise RuntimeError("Неуспешно записване на отсъствие за една или повече тренировки")
            
            # Multiple sessions without confirmation - ask parent
            session_lines = [self._format_session_line(session) for session in sessions]
            return (
                f"[CLARIFICATION_NEEDED] {player_label} има {len(sessions)} тренировки на {date_param}:\n"
                + "\n".join(session_lines)
                + "\n\nИскате ли да отбележа отсъствие за всички сесии? Отговорете 'да' за всички, или посочете session_id за конкретна сесия."
            )
        except MCPClientError as exc:
            return f"❌ Не успях да запиша отсъствието. Моля опитайте отново след малко. Грешка: {exc}"
        except RuntimeError as exc:
            return f"❌ {exc}"


class GetInvoicesTool(MCPTool):
    name: str = "get_invoices"
    description: str = "Use to retrieve outstanding invoices relevant to the user"
    tool_name: str = "academy.get_invoices"
    args_schema: Type[BaseModel] = GetInvoicesParams

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        print(f"DEBUG: GetInvoicesTool._arun called with args={args} kwargs={kwargs}")
        self._ensure_authorized()
        context = self._user_context or {}
        
        print(f"DEBUG: Context keys: {list(context.keys())}")
        print(f"DEBUG: Initial partner_id: {context.get('partner_id')}")
        print(f"DEBUG: Player IDs: {context.get('player_ids')}")

        # If partner_id is not provided, try to get it from context
        if not kwargs.get("partner_id"):
            partner_id = context.get("partner_id")
            player_ids = context.get("player_ids") or []
            
            # ALWAYS try to resolve the billing contact (guardian) if players are linked
            # In this academy, invoices are issued to the guardian, not the player.
            if player_ids:
                try:
                    print(f"DEBUG: Attempting to resolve guardian for players: {player_ids}")
                    players_payload = await self._call_tool_json(
                        "search_records",
                        {
                            "model": "academy.player",
                            "domain": [("id", "in", player_ids)],
                            "fields": ["primary_guardian_id"],
                            "limit": 1
                        },
                    )
                    print(f"DEBUG: Guardian resolution payload: {players_payload}")
                    
                    records = []
                    if isinstance(players_payload, dict):
                        records = players_payload.get("records", [])
                    elif isinstance(players_payload, list):
                        records = players_payload

                    if records:
                        guardian = records[0].get("primary_guardian_id")
                        # Many2one field returns [id, name] or False
                        if isinstance(guardian, list) and len(guardian) > 0:
                            guardian_id = guardian[0]
                            if guardian_id != partner_id:
                                print(f"DEBUG: Resolved billing partner from players: {partner_id} -> {guardian_id}")
                                partner_id = guardian_id
                            else:
                                print(f"DEBUG: Guardian ID {guardian_id} matches context partner_id")
                        else:
                            print(f"DEBUG: Primary guardian field is empty or invalid: {guardian}")
                    else:
                        print("DEBUG: No player records found for guardian resolution")
                except Exception as e:
                    print(f"DEBUG: Failed to resolve guardian from players: {e}")

            if not partner_id:
                # If we are here, it means the user didn't provide partner_id and we couldn't find it in context
                # This might happen if an admin calls the tool without partner_id
                raise RuntimeError("Partner ID is required. Please specify a partner_id.")
            kwargs["partner_id"] = partner_id
            
        print(f"DEBUG: Calling academy.get_invoices with partner_id: {kwargs.get('partner_id')}")
        result_json = await super()._arun(*args, **kwargs)
        print(f"DEBUG: academy.get_invoices result: {result_json}")
        
        try:
            data = json.loads(result_json)
            total_due = data.get("total_due", 0.0)
            currency = data.get("currency", "")
            invoices = data.get("invoices", [])
            
            # If requesting unpaid invoices (default) and total_due is 0, return "No obligations"
            # But if requesting 'paid' or 'all', we should list them even if total_due is 0
            status_arg = kwargs.get("status")
            if (not status_arg or status_arg == "unpaid") and total_due <= 0 and not invoices:
                return "Нямате задължения за момента."
            
            if not invoices:
                return "Няма намерени фактури."

            msg = f"Общо дължима сума: {total_due:.2f} {currency}.\n\nДетайли по фактури:\n"
            for inv in invoices:
                due_date = inv.get("due_date") or "N/A"
                amount = inv.get("residual", 0.0)
                total_amount = inv.get("amount", 0.0)
                number = inv.get("number", "Unknown")
                status_label = inv.get("status", "")
                
                # Show residual for unpaid, total for paid
                display_amount = amount if amount > 0 else total_amount
                
                msg += f"- Фактура {number}: {display_amount:.2f} {currency} ({status_label}), падеж: {due_date}\n"
                
            return msg
        except Exception:
            # If parsing fails, return original result
            return result_json


class GetContactInfoTool(MCPTool):
    name: str = "get_contact_info"
    description: str = "Use to get guardian contact details for a player (restricted)"
    tool_name: str = "academy.get_contact_info"
    args_schema: Type[BaseModel] = GetContactInfoParams


def build_tools(client: MCPClient) -> List[MCPTool]:
    """Factory that wires default RBAC policy for the PoC."""

    tools: Sequence[tuple[type[MCPTool], Iterable[str]]] = (
        (SearchSessionsTool, {"guardian", "coach", "admin"}),
        (ReportAbsenceTool, {"guardian", "coach"}),
        (GetInvoicesTool, {"guardian", "admin"}),
        (GetContactInfoTool, {"coach", "admin", "guardian"}),
    )
    return [tool_cls(client=client, allowed_roles=roles) for tool_cls, roles in tools]
