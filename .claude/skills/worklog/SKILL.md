---
name: worklog
description: Generate a recap of recent Claude Code sessions with summaries of what was discussed and accomplished
---

# Worklog - Session Recap Generator

Generate a human-readable recap of recent Claude Code conversations.

## Usage

```
/worklog                    # Sessions since yesterday 8am
/worklog --since today      # Today's sessions
/worklog --since week       # Last 7 days
/worklog --since "2026-01-15 08:00"  # Specific datetime
```

## Process

1. **Extract**: Run `python3 ~/.claude/skills/worklog/extract.py --since <timespec> --pretty`
   - Default `<timespec>` to `yesterday` if not provided
   - Run `--help` for all options

2. **Generate recap** from the JSON output:

```markdown
# Worklog: <date range>

## Summary
<2-3 sentence overview of what was accomplished across all sessions>

## Sessions

### 🗨️ "<title>"
`<project path>`
- **Session:** `<session_id>`
- **Time:** <started> → <ended> (<duration>)
- **Context:** <context_pct>% (<context_tokens> tokens)
- **Compactions:** <count> (hit context limit: yes/no)

**What was discussed:**
<2-4 bullets synthesized from compaction summaries, removing redundancy>

**Git commits:**
<List commits if any, otherwise "None">

If title is null, use project path as heading instead: `### <project path>`

---
```

3. **Offer next steps**: Resume a session? Save to file? More details?

## Common Mistakes

- **Wrong date format**: Use `"YYYY-MM-DD HH:MM"` with quotes, or keywords: `yesterday`, `today`, `week`
- **Empty results**: Check if the timespec is correct; sessions must have activity in that window
- **Missing git commits**: Commits only show if made during the session timeframe in the session's cwd

## Guidelines

- **Session title** comes from compaction summary, or fallback to first user message (truncated)
- **Title is null** only for sessions with no meaningful user input (use project name instead)
- **Compaction summaries** are the primary source for "what was discussed"
- **Git commits** show concrete output from the session
- **Context %** indicates session intensity; many compactions = hit context limit
- Keep recaps concise - quick reference, not detailed log
