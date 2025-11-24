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

### 1. Response Template Replacement (`@after_model`)

**Purpose**: Replace the LLM's verbose response with a controlled template after successful absence recording, supporting both single and multiple player scenarios.

**Location**: `langchain_agent.py`

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
    
    # Find all report_absence tool messages in the current turn
    report_absence_tools = []
    # Iterate backwards to find the sequence of tool messages
    for msg in reversed(messages[:-1]):
        if isinstance(msg, HumanMessage):
            break 
        if isinstance(msg, ToolMessage) and msg.name == 'report_absence':
            report_absence_tools.append(msg)
            
    if not report_absence_tools:
        return None

    # Check for confirmation requests or errors in ANY of the tool outputs
    for tool_msg in report_absence_tools:
        tool_content = str(tool_msg.content)
        if '[CLARIFICATION_NEEDED]' in tool_content:
            return None  # Preserve agent's confirmation question
        if '❌' in tool_content or 'Error' in tool_content:
            return None

    # Aggregate details from all successful tool calls
    processed_absences = []
    
    for tool_msg in report_absence_tools:
        # Find the corresponding tool call in the AIMessage
        # ... (logic to match tool_call_id and extract args) ...
        
        if player_name and (date or session_id):
            processed_absences.append({
                "player": player_name,
                "date": date,
                "session": session_id,
                "all": confirm_all
            })

    # Build appropriate template based on number of absences processed
    if not processed_absences:
        return None
        
    if len(processed_absences) == 1:
        # Single absence template
        info = processed_absences[0]
        if info["all"]:
            template = f"Разбрано. Регистрирах отсъствие за всички сесии на {info['date']} за {info['player']}..."
        elif info["session"]:
            template = f"Разбрано. Регистрирах отсъствие за {info['player']} за тренировка {info['session']}..."
        else:
            template = f"Разбрано. Регистрирах отсъствие за {info['player']} на {info['date']}..."
    else:
        # Multiple absences template
        details = []
        for info in processed_absences:
            if info['date']:
                details.append(f"{info['player']} ({info['date']})")
            # ...
        template = f"Разбрано. Регистрирах отсъствията за: {', '.join(details)}..."

    return {"messages": [AIMessage(content=template)]}
```

**Critical Safeguards**:

1. **Execution State Check**:
   - Prevents middleware from triggering when AI plans to call a tool (before execution)

2. **Explicit Confirmation Signal**:
   - Detects when tool is asking user for confirmation using the `[CLARIFICATION_NEEDED]` marker
   - Preserves agent's question instead of replacing with template

3. **Multi-Tool Aggregation**:
   - Scans *all* tool messages in the current turn, not just the last one
   - Allows handling requests like "Report absence for Stela and Dalia" in a single response

4. **Stateless Argument Extraction**:
   - Extracts arguments directly from the `AIMessage` history, eliminating the need for shared state variables

### 2. Context Injection (`@dynamic_prompt`)

**Purpose**: Inject user-specific context (current date, player names, role) into system prompt.

**Location**: `langchain_agent.py`

**Key Features**:
- Adds current date, Telegram ID, user role to prompt
- Maps player names to IDs for disambiguation
- Truncates message history to prevent prompt bloat (MAX_MESSAGES = 12)
- **Truncation Safety**: Ensures truncated history never starts with a `ToolMessage` to prevent API errors
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
3. **Tool**: Detects 1 session, records absence immediately
4. **Tool Response**: "✓ Отбелязах отсъствието на Стела Величкова..."
5. **Middleware (`@after_model`)**: Detects successful execution (no `?` in response)
6. **Template Applied**: "Разбрано. Регистрирах отсъствие за Стела Величкова на 2025-11-24. Треньорите са уведомени. Мога ли да помогна с още нещо?"

### Multiple Sessions Scenario

1. **User**: "Далия ще отсъства утре"
2. **Agent**: Calls `report_absence(player_name="Далия Величкова", date="2025-11-21")` (no `session_id`)
3. **Tool**: Detects 2 sessions, returns:
   ```
   [CLARIFICATION_NEEDED] Далия Величкова има 2 тренировки на 2025-11-21:
   - 12:00 – Physical Activities (Group) (session_id=1289)
   - 13:00 – Tennis Skills (Group) (session_id=1313)
   
   Искате ли да отбележа отсъствие за всички сесии?
   ```
4. **Middleware (`@after_model`)**: Detects `[CLARIFICATION_NEEDED]` in tool response → returns `None`
5. **Agent**: Preserves tool's question (no template replacement)
6. **User**: "да" (or "всички")
7. **Agent**: Calls `report_absence(player_name="Далия Величкова", date="2025-11-21", confirm_all=True)`
8. **Tool**: Records absence for both sessions (1289 and 1313)
9. **Middleware (`@after_model`)**: Detects `confirm_all=True` → selects multiple session template
10. **Template Applied**: "Разбрано. Регистрирах отсъствие за всички сесии на 2025-11-21 за Далия Величкова. Треньорите са уведомени. Мога ли да помогна с още нещо?"

### Multiple Players Scenario (Parallel Tool Calls)

1. **User**: "Стела и Далия ще отсъстват утре"
2. **Agent**: Calls `report_absence` twice in parallel:
   - `report_absence(player_name="Стела Величкова", date="2025-11-21")`
   - `report_absence(player_name="Далия Величкова", date="2025-11-21")`
3. **Tool**: Executes both calls.
   - Call 1: Records absence for Stela.
   - Call 2: Records absence for Dalia.
4. **Middleware (`@after_model`)**: 
   - Detects successful execution for *both* tools.
   - Aggregates details: `[{player: Stela, date: ...}, {player: Dalia, date: ...}]`
5. **Template Applied**: "Разбрано. Регистрирах отсъствията за: Стела Величкова (2025-11-21), Далия Величкова (2025-11-21). Треньорите са уведомени..."

## Middleware Execution Order

```
1. context_aware_prompt (@dynamic_prompt)
   ↓ Injects user context before model call
   ↓ *Sanitizes history to prevent orphaned ToolMessages*
   
2. Model generates response (potentially with tool_calls)
   ↓
   
3. Tools execute (if applicable)
   ↓
   
4. replace_tool_response_with_template (@after_model)
   ↓ Inspects history for tool results
   ↓ Replaces response with template if criteria met
```

**Important Note**: `@after_model` runs after **every** model response, including when the model decides to call a tool (before execution). The execution state check is critical to distinguish between:
- **Planning phase**: AIMessage has `tool_calls` attribute (tools not executed yet)
- **Response phase**: AIMessage has no `tool_calls`, recent ToolMessage exists (tools executed)

## State Management

### Stateless Argument Extraction

**Old Approach**: Used a shared dictionary `last_absence_details` to store tool arguments via a `@wrap_tool_call` decorator. This was not thread-safe and caused race conditions.

**New Approach**: The middleware is now **stateless**. It inspects the message history to find the `AIMessage` that triggered the `report_absence` tool call(s) and extracts the arguments (`player_name`, `date`, `confirm_all`, `session_id`) directly from the `tool_calls` payload.

**Benefits**:
- **Thread-safe**: Can handle multiple concurrent users/agents.
- **Robust**: No risk of stale state from previous interactions.
- **Self-contained**: All necessary information is derived from the conversation history.
- **Multi-Tool Support**: Can easily aggregate data from multiple parallel tool calls.

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

### 3. Explicit Confirmation Signal

**Problem**: Need to reliably distinguish between "confirmation request" and "success confirmation" responses without relying on fragile string parsing.

**Solution**: The tool prepends a `[CLARIFICATION_NEEDED]` marker when it needs user input. The middleware checks for this specific marker.
```python
if '[CLARIFICATION_NEEDED]' in tool_content:
    return None  # Preserve agent's question
```

**Benefit**: Creates a robust contract between the Tool and Middleware. The Tool explicitly signals when it needs "Human in the Loop" intervention.



## Debugging and Observability

### LangSmith Tracing

All agent invocations are automatically traced to LangSmith when environment variables are set:
- `LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY=<key>`
- `LANGSMITH_PROJECT=<project-name>`

### Log Messages

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
6. **Statelessness is superior** - inspecting message history is more robust than capturing state in side-effects
7. **History Sanitization is mandatory** - LLM APIs (like OpenAI) are strict about message order; truncated history must be validated to avoid orphaned `ToolMessage`s.

---

**Document Version**: 1.0  
**Last Updated**: November 20, 2025  
**Author**: AI Development Team  
**Status**: Production
