---
name: handoff
description: Use when ending a session, switching context, or wanting to preserve state for a future session to pick up
---

# Handoff

Create a handoff document for session continuity. The handoff is the baton a future session picks up.

## Process

1. **Get session ID** (in order of preference):
   - `$CLAUDE_SESSION_ID` env var (new sessions)
   - Look for "Session ID: <uuid>" in SessionStart hook output in your context
   - **FALLBACK**: Use `unknownsession-<YYYYMMDD-HHMMSS>` and WARN USER LOUDLY:
     ```
     ⚠️  SESSION ID NOT FOUND - using fallback identifier.
     Check ~/.claude/hooks/session_start.sh is working correctly.
     ```

2. **Create handoff file:**
   ```bash
   mkdir -p "${project_root:-.}/.agent"
   # File: .agent/HANDOFF.<session-id>.md
   ```

3. **Write content** using the template below

## Template

```markdown
# Handoff: <session-id> (<session-title>)

## Current State (Baton)

<What needs to be picked up. What was I working on? What's the current status?>

## What's Left

<Remaining todos, blockers, next steps>

## Context

<Important decisions made, gotchas discovered, relevant file paths>

---

## Log

### <timestamp>
<What was accomplished in this update>
```

## Update Behavior

When updating an existing handoff:
- **Overwrite** the baton sections (Current State, What's Left, Context)
- **Append** new entries to the Log section with timestamps

## Notes

- `$CLAUDE_SESSION_ID` set by SessionStart hook (new sessions)
- For resumed sessions, hook output visible in context as "Session ID: <uuid>"
- One file per session ID prevents collisions
- Baton sections overwritten; Log is append-only
