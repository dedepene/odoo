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
    session_id: int = Field(..., description="Session occurrence identifier")
    player_id: int = Field(..., description="Player missing the session")
    reason: Optional[str] = Field(None, description="Optional free text reason")


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
                        f"No player named '{player_name_filter}' found in your account. "
                        f"You can only view sessions for your own players: {names_list}."
                    )
                else:
                    return "No players are linked to your account."
            players = filtered_players
        
        if not players:
            return "No players are linked to your account."

        start_date = kwargs.get("date_from") or date.today().isoformat()
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
    description: str = (
        "Use to record that a player will miss a scheduled session. "
        "Requires session_id and player_id (extract from search_sessions results). "
        "The reason is optional and will be automatically set if not provided."
    )
    tool_name: str = "report_absence"  # Internal name, not an MCP tool
    args_schema: Type[BaseModel] = ReportAbsenceParams

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Report absence by creating a session absence record."""
        self._ensure_authorized()
        
        session_id = kwargs.get("session_id")
        player_id = kwargs.get("player_id")
        reason = kwargs.get("reason") or "Отсъствие по желание на родителя"
        
        if not session_id or not player_id:
            raise RuntimeError(
                "Both session_id and player_id are required to report absence. "
                "Extract these from search_sessions output (e.g., 'session_id=123')."
            )
        
        try:
            # Check if absence already exists
            existing_payload = await self._call_tool_json(
                "search_records",
                {
                    "model": "academy.session.absence",
                    "domain": [
                        ("occurrence_id", "=", session_id),
                        ("player_id", "=", player_id),
                        ("state", "in", ["reported", "acknowledged"]),
                    ],
                    "fields": ["id", "state", "reason_code"],
                    "limit": 1,
                },
            )
            
            existing_records = []
            if isinstance(existing_payload, dict):
                existing_records = existing_payload.get("records", [])
            elif isinstance(existing_payload, list):
                existing_records = existing_payload
            
            if existing_records:
                # Absence already reported
                return (
                    f"✓ Отсъствието вече е отбелязано за играч {player_id} "
                    f"в тренировка {session_id}."
                )
            else:
                # Create new absence record
                # Map reason text to reason_code (simple keyword matching)
                reason_code = "other"  # default
                reason_lower = reason.lower()
                if any(word in reason_lower for word in ["болест", "болен", "болна", "illness", "sick"]):
                    reason_code = "illness"
                elif any(word in reason_lower for word in ["нараняване", "травма", "injury"]):
                    reason_code = "injury"
                elif any(word in reason_lower for word in ["семейств", "family"]):
                    reason_code = "family"
                elif any(word in reason_lower for word in ["училищ", "school"]):
                    reason_code = "school"
                elif any(word in reason_lower for word in ["ваканция", "почивка", "vacation"]):
                    reason_code = "vacation"
                
                create_result = await self._call_tool_json(
                    "create_record",
                    {
                        "model": "academy.session.absence",
                        "values": {
                            "occurrence_id": session_id,
                            "player_id": player_id,
                            "reason_code": reason_code,
                            "reason_note": reason,
                        },
                    },
                )
                
                return (
                    f"✓ Отсъствието е отбелязано успешно. "
                    f"Играч {player_id} ще отсъства от тренировка {session_id}. "
                    f"Причина: {reason}"
                )
                
        except MCPClientError as exc:
            error_msg = str(exc)
            if "Unknown tool" in error_msg:
                raise RuntimeError(
                    "MCP server tools not available. Please ensure the MCP server is running "
                    "and properly configured with create_record, update_record, and search_records tools."
                ) from exc
            raise RuntimeError(f"Failed to report absence: {exc}") from exc


class GetInvoicesTool(MCPTool):
    name: str = "get_invoices"
    description: str = "Use to retrieve outstanding invoices relevant to the user"
    tool_name: str = "academy.get_invoices"
    args_schema: Type[BaseModel] = GetInvoicesParams


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
