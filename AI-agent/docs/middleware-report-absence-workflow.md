# Middleware Implementation for report_absence Workflow

## Overview

This document describes the middleware-based architecture implemented to control the `report_absence` tool workflow in the LangChain agent. The implementation uses LangChain v1's middleware system to enforce a controlled, predictable user experience when recording player absences, particularly when multiple sessions exist on the same date.

## Problem Statement

### Initial Issue
The agent was offering additional services and asking follow-up questions after successfully recording absences, creating an unpredictable and overly verbose user experience. System prompts proved unreliable in preventing this behavior.

### Secondary Issue
When reporting an absence for a date with multiple sessions, the LLM would extract `session_id` from search results and directly call `report_absence` with a specific session ID, bypassing the tool's built-in multiple-session confirmation workflow. This resulted in only the first session being marked absent.

## Architecture Decision

Rather than relying on system prompts (which are "super unreliable" as the user correctly identified), we implemented an **architectural solution using middleware**. This approach intercepts and modifies the agent's execution flow at strategic points.

## Middleware Components

### 1. Tool Argument Capture (`@wrap_tool_call`)

**Purpose**: Capture arguments from `report_absence` tool calls before execution for later use in response templating.

**Location**: `langchain_agent.py`, lines 154-171

**Implementation**:
```python
@wrap_tool_call
async def capture_absence_details(request, handler):
    """Capture player_name, date, and confirm_all from report_absence tool calls."""
    tool_call = request.tool_call
    tool_name = tool_call.get("name")
    
    if tool_name == "report_absence":
        args = tool_call.get("args", {})
        last_absence_details["player_name"] = args.get("player_name")
        last_absence_details["date"] = args.get("date")
        last_absence_details["confirm_all"] = bool(args.get("confirm_all"))
    
    return await handler(request)
```

**Key Features**:
- Async function (required for `@wrap_tool_call`)
- Stores `player_name`, `date`, and `confirm_all` flag in shared dictionary
- Non-invasive - always calls `handler(request)` to proceed with normal execution
- Logs captured details for debugging

### 2. Response Template Replacement (`@after_model`)

**Purpose**: Replace the LLM's verbose response with a controlled template after successful absence recording.

**Location**: `langchain_agent.py`, lines 173-257

**Implementation**:
```python
@after_model
def replace_tool_response_with_template(state, runtime):
    """Replace AI response with template after successful report_absence execution."""
    messages = state.get("messages", [])
    last_message = messages[-1]
    
    # CRITICAL: Check if tools haven't executed yet
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return None  # Let tools execute first
    
    # Find recent ToolMessage
    recent_tool_message = None
    for msg in reversed(messages[-5:]):
        if isinstance(msg, ToolMessage):
            recent_tool_message = msg
            break
    
    # Verify it's report_absence
    if recent_tool_message and getattr(recent_tool_message, 'name') == 'report_absence':
        # Check for confirmation request
        tool_content = getattr(recent_tool_message, 'content', '')
        if '?' in tool_content or 'Искате ли' in tool_content:
            return None  # Preserve agent's confirmation question
        
        # Build appropriate template
        player_name = last_absence_details.get("player_name")
        date = last_absence_details.get("date")
        confirm_all = last_absence_details.get("confirm_all")
        
        if confirm_all:
            template = f"Разбрано. Регистрирах отсъствие за всички сесии на {date} за {player_name}..."
        else:
            template = f"Разбрано. Регистрирах отсъствие за {player_name} на {date}..."
        
        return {"messages": [AIMessage(content=template)]}
    
    return None
```

**Critical Safeguards**:

1. **Execution State Check** (Lines 196-199):
   - Prevents middleware from triggering when AI plans to call a tool (before execution)
   - Checks for `tool_calls` attribute on AIMessage
   - Returns `None` to allow tool execution to proceed

2. **Confirmation Detection** (Lines 218-224):
   - Detects when tool is asking user for confirmation
   - Checks for question marks (`?`) or Bulgarian phrase (`Искате ли`)
   - Preserves agent's question instead of replacing with template

3. **Dynamic Template Selection** (Lines 226-240):
   - Single session: "Регистрирах отсъствие за {player_name} на {date}"
   - Multiple sessions: "Регистрирах отсъствие за всички сесии на {date} за {player_name}"
   - Fallback template if details unavailable

### 3. Context Injection (`@dynamic_prompt`)

**Purpose**: Inject user-specific context (current date, player names, role) into system prompt.

**Location**: `langchain_agent.py`, lines 259-383

**Key Features**:
- Adds current date, Telegram ID, user role to prompt
- Maps player names to IDs for disambiguation
- Truncates message history to prevent prompt bloat (MAX_MESSAGES = 12)
- Creates background summary tasks for long conversations (SUMMARY_TRIGGER = 40)

## System Prompt Enhancements

### Critical Instruction for Multiple Sessions

**Location**: `langchain_agent.py`, lines 96-101

```
2. CRITICAL: When reporting absence by DATE, ALWAYS use ONLY the 'date' parameter (NEVER use 'session_id')
   - This lets the tool detect multiple sessions and ask for confirmation
   - Tool will handle single vs multiple session logic automatically
3. If tool asks for confirmation about multiple sessions, wait for user response
4. After confirmation, call report_absence again with confirm_all=True or specific session_id
```

**Rationale**: Forces the LLM to delegate multiple-session detection to the tool, preventing it from arbitrarily selecting the first session.

## Execution Flow

### Single Session Scenario

1. **User**: "Стела ще отсъства на 24 ноември"
2. **Agent**: Calls `report_absence(player_name="Стела Величкова", date="2025-11-24")` (no `session_id`)
3. **Middleware (`@wrap_tool_call`)**: Captures `player_name`, `date`, `confirm_all=False`
4. **Tool**: Detects 1 session, records absence immediately
5. **Tool Response**: "✓ Отбелязах отсъствието на Стела Величкова..."
6. **Middleware (`@after_model`)**: Detects successful execution (no `?` in response)
7. **Template Applied**: "Разбрано. Регистрирах отсъствие за Стела Величкова на 2025-11-24. Треньорите са уведомени. Мога ли да помогна с още нещо?"

### Multiple Sessions Scenario

1. **User**: "Далия ще отсъства утре"
2. **Agent**: Calls `report_absence(player_name="Далия Величкова", date="2025-11-21")` (no `session_id`)
3. **Middleware (`@wrap_tool_call`)**: Captures `player_name`, `date`, `confirm_all=False`
4. **Tool**: Detects 2 sessions, returns:
   ```
   Далия Величкова има 2 тренировки на 2025-11-21:
   - 12:00 – Physical Activities (Group) (session_id=1289)
   - 13:00 – Tennis Skills (Group) (session_id=1313)
   
   Искате ли да отбележа отсъствие за всички сесии?
   ```
5. **Middleware (`@after_model`)**: Detects `?` in tool response → returns `None`
6. **Agent**: Preserves tool's question (no template replacement)
7. **User**: "да" (or "всички")
8. **Agent**: Calls `report_absence(player_name="Далия Величкова", date="2025-11-21", confirm_all=True)`
9. **Middleware (`@wrap_tool_call`)**: Captures `confirm_all=True`
10. **Tool**: Records absence for both sessions (1289 and 1313)
11. **Middleware (`@after_model`)**: Detects `confirm_all=True` → selects multiple session template
12. **Template Applied**: "Разбрано. Регистрирах отсъствие за всички сесии на 2025-11-21 за Далия Величкова. Треньорите са уведомени. Мога ли да помогна с още нещо?"

## Middleware Execution Order

```
1. context_aware_prompt (@dynamic_prompt)
   ↓ Injects user context before model call
   
2. Model generates response
   ↓
   
3. capture_absence_details (@wrap_tool_call)
   ↓ Captures tool arguments before execution
   
4. Tools execute
   ↓
   
5. replace_tool_response_with_template (@after_model)
   ↓ Replaces response with template after execution
```

**Important Note**: `@after_model` runs after **every** model response, including when the model decides to call a tool (before execution). The execution state check is critical to distinguish between:
- **Planning phase**: AIMessage has `tool_calls` attribute (tools not executed yet)
- **Response phase**: AIMessage has no `tool_calls`, recent ToolMessage exists (tools executed)

## State Management

### Shared Dictionary Pattern

```python
last_absence_details = {"player_name": None, "date": None, "confirm_all": False}
```

**Lifecycle**:
1. **Capture**: Populated by `@wrap_tool_call` when tool is called
2. **Use**: Read by `@after_model` for template population
3. **Clear**: Reset to `None`/`False` after template replacement

**Scope**: Closure variable within `_initialize_agent()` - shared between middleware functions but isolated per agent instance.

## Key Design Patterns

### 1. Architectural Over Prompt-Based Control

**Rationale**: System prompts are unreliable for enforcing strict behavioral constraints. Middleware provides deterministic control over agent behavior.

**Trade-offs**:
- ✅ Predictable, testable behavior
- ✅ No reliance on LLM instruction-following
- ⚠️ More complex implementation
- ⚠️ Requires understanding of middleware lifecycle

### 2. State Checking for Timing

**Problem**: `@after_model` runs after model generates output, but before tools execute when model plans tool calls.

**Solution**: Check for `tool_calls` attribute on AIMessage to determine execution phase:
```python
if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
    return None  # Don't replace - tools haven't executed yet
```

### 3. Content-Based Confirmation Detection

**Problem**: Need to distinguish between "confirmation request" and "success confirmation" responses.

**Solution**: Heuristic-based detection using question marks and Bulgarian phrases:
```python
if '?' in tool_content or 'Искате ли' in tool_content:
    return None  # Preserve agent's question
```

**Alternative Considered**: Structured tool responses with explicit flags (rejected for simplicity).

### 4. Async Middleware Functions

**Requirement**: `@wrap_tool_call` must be async to support async tool execution.

**Implementation**:
```python
@wrap_tool_call
async def capture_absence_details(request, handler):
    # ...
    return await handler(request)  # Must await
```

## Debugging and Observability

### LangSmith Tracing

All agent invocations are automatically traced to LangSmith when environment variables are set:
- `LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY=<key>`
- `LANGSMITH_PROJECT=<project-name>`

### Log Messages

**Tool Argument Capture**:
```python
LOGGER.info(
    f"Captured report_absence details: player_name={player_name}, "
    f"date={date}, confirm_all={confirm_all}"
)
```

**Confirmation Detection**:
```python
LOGGER.info("Tool is asking for confirmation - preserving agent's question")
```

**Template Replacement**:
```python
LOGGER.info(
    f"Replaced AI response with template after report_absence. "
    f"Player: {player_name}, Date: {date}, Confirm_all: {confirm_all}"
)
```

### Trace Analysis Example

When debugging the "Далия ще отсъства утре" issue, LangSmith traces revealed:
1. AIMessage with `tool_calls` for Daliya (planning phase)
2. NO corresponding ToolMessage (tool never executed)
3. Middleware found OLD ToolMessage from Stela's previous absence
4. Premature template replacement before tool execution

**Fix**: Added execution state check (lines 196-199).

## Testing Checklist

- [ ] Single session absence: Records correctly, uses single session template
- [ ] Multiple sessions: Agent asks for confirmation before recording
- [ ] User confirms all sessions: Both/all sessions marked absent, uses multiple session template
- [ ] User specifies specific session_id: Only that session marked absent
- [ ] Middleware doesn't trigger on confirmation questions (preserves agent's question)
- [ ] Middleware doesn't trigger before tool execution (no premature replacement)
- [ ] Old ToolMessages in history don't cause false triggers
- [ ] Template includes correct player_name and date
- [ ] Fallback template works when capture fails

## Future Enhancements

### Potential Improvements

1. **Structured Tool Responses**: Replace heuristic-based confirmation detection with explicit response flags
   ```python
   {"type": "confirmation_request", "sessions": [...]}
   ```

2. **Middleware Composition**: Extract common patterns into reusable middleware factories
   ```python
   create_template_replacement_middleware(tool_name, templates)
   ```

3. **Configurable Templates**: Move templates to configuration file for easier customization

4. **Multi-Language Support**: Detect user language and select appropriate template

5. **Rich Confirmation UI**: For Telegram, use inline keyboards for session selection instead of text responses

## Related Files

- **Agent Configuration**: `AI-agent/langchain_agent.py`
- **Tool Implementation**: `AI-agent/mcp_tools.py` (lines 396-736)
- **Telegram Bot**: `AI-agent/telegram_bot.py`
- **Odoo MCP Server**: `AI-agent/odoo-mcp-server/mcp_server_odoo/server.py`

## References

- [LangChain v1 Middleware Documentation](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [LangGraph Human-in-the-Loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [LangSmith Tracing](https://docs.smith.langchain.com/)

## Lessons Learned

1. **System prompts are unreliable** for enforcing strict behavioral constraints - use architectural solutions
2. **Middleware timing is critical** - `@after_model` runs after every model response, not just final responses
3. **State checks are essential** - always verify execution phase before taking action
4. **Heuristic detection works** - simple pattern matching is sufficient for confirmation detection
5. **Logging is invaluable** - comprehensive logging enabled rapid debugging via LangSmith traces
6. **Shared state is acceptable** - closure-scoped dictionaries provide clean state sharing between middleware functions

---

**Document Version**: 1.0  
**Last Updated**: November 20, 2025  
**Author**: AI Development Team  
**Status**: Production
