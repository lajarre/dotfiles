---
name: worklog
description: Use when a Codex worklog or session recap is requested, or when auditing context usage (rot/smash) across recent Codex CLI sessions.
---

# Worklog - Codex Session Recap Generator

Generate a human-readable recap of recent Codex conversations, including context health.

## Usage

```
/worklog                    # Sessions since yesterday 08:00 (local time)
/worklog --since today      # Today's sessions
/worklog --since week       # Last 7 days
/worklog --since "2026-01-15 08:00"  # Specific datetime
/worklog --session <id>     # Single session
```

## Process

1. **Extract** session data (default window is yesterday 08:00 local -> now):

```
python3 ~/.codex/skills/worklog/scripts/extract.py --since <timespec> --pretty
```

2. **Generate recap** from the JSON output:

```
python3 ~/.codex/skills/worklog/scripts/conversation_recap.py --since <timespec>
```

3. **Quick stats** (optional):

```
python3 ~/.codex/skills/worklog/scripts/session_stats.py --today
```

## Output format

- Header: `Worklog: <start> -> <end>`
- Summary: 1-3 short sentences
- Sessions grouped by `cwd`, each with:
  - Title line first (`🗨️ "..."`)
  - Working folder on next line (or explicit note if missing)
  - Session ID
  - Time range + duration
  - Context percent + tokens
  - Context hits: rot >= 80%, smash >= 99%
  - What was discussed (2-4 bullets)
  - Git commits (if any)
- Next steps prompt

## Context health definitions

- **Context rot**: number of times context usage crosses >= 80%.
- **Context smash**: number of times context usage crosses >= 99%.

These are computed from Codex `token_count` events (last_token_usage / model_context_window).

## Common mistakes

- Wrong date format: use `YYYY-MM-DD HH:MM` (24h) or keywords `yesterday`, `today`, `week`.
- Empty results: confirm the time window and that sessions exist in `~/.codex/sessions/`.
- Missing git commits: commits are only detected if the session `cwd` is a git repo.

## Guidelines

- Keep recaps concise (quick reference, not full logs).
- Prefer user prompts + tool edits over raw tool outputs.
- If context rot/smash hits are high, call it out in the summary.
