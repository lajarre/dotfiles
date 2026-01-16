#!/usr/bin/env python3
"""
Extract and summarize Claude Code conversation sessions.

Usage:
    python conversation_recap.py [--since "YYYY-MM-DD HH:MM"] [--session SESSION_ID]

Examples:
    python conversation_recap.py --since "2026-01-15 08:00"
    python conversation_recap.py --session cfc3f0b3-b9b9-4598-bb26-fc9559823c98
"""

import json
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
DEFAULT_CONTEXT_WINDOW = 200000


def parse_timestamp(ts_str: str) -> datetime | None:
    """Parse ISO timestamp string to datetime."""
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace('Z', '+00:00')
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def find_session_files(since: datetime | None = None) -> list[tuple[Path, str]]:
    """Find all session JSONL files, optionally filtering by modification time."""
    sessions = []

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            # Skip subagent files
            if "subagents" in str(jsonl_file):
                continue

            # Check modification time if filtering
            if since:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)
                if mtime < since:
                    continue

            # Extract project name from directory
            # Format: -Users-alex-foo-bar → ~/foo/bar
            # Format: -Users-alex--claude → ~/.claude (leading dash = dot)
            project_name = project_dir.name
            if project_name.startswith("-Users-alex-"):
                project_name = project_name[len("-Users-alex-"):]
                # Leading dash represents a dot (hidden dir)
                if project_name.startswith("-"):
                    project_name = "." + project_name[1:]
                project_name = "~/" + project_name.replace("-", "/")
            sessions.append((jsonl_file, project_name))

    return sessions


def analyze_session(filepath: Path, cutoff: datetime | None = None) -> dict:
    """Analyze a single session file and extract statistics."""
    session_id = filepath.stem

    first_ts = None
    last_ts = None
    user_msgs = 0
    assistant_msgs = 0
    compactions = []
    user_messages = []
    last_usage = None
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0

    with open(filepath, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                ts = parse_timestamp(data.get('timestamp'))
                msg_type = data.get('type', '')

                # Track timestamps
                if ts:
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                # Track compactions/summaries
                if msg_type == 'summary':
                    summary_text = data.get('summary', 'unknown')
                    compactions.append(summary_text)

                # Count messages and extract content
                in_window = cutoff is None or (ts and ts >= cutoff)

                if msg_type == 'user' and not data.get('isMeta'):
                    if in_window:
                        user_msgs += 1
                        content = data.get('message', {}).get('content', '')
                        if isinstance(content, str):
                            # Skip tool results and commands
                            if not content.startswith('[{') and \
                               not content.startswith('<command') and \
                               not content.startswith('<local-command'):
                                if content.strip():
                                    user_messages.append(content.strip()[:300])

                elif msg_type == 'assistant':
                    if in_window:
                        assistant_msgs += 1

                    usage = data.get('message', {}).get('usage', {})
                    if usage:
                        last_usage = usage
                        total_input += usage.get('input_tokens', 0)
                        total_output += usage.get('output_tokens', 0)
                        total_cache_read += usage.get('cache_read_input_tokens', 0)
                        total_cache_creation += usage.get('cache_creation_input_tokens', 0)

            except json.JSONDecodeError:
                continue

    # Calculate context usage from last turn
    context_tokens = 0
    context_pct = 0.0
    if last_usage:
        input_t = last_usage.get('input_tokens', 0)
        cache_r = last_usage.get('cache_read_input_tokens', 0)
        cache_c = last_usage.get('cache_creation_input_tokens', 0)
        context_tokens = input_t + cache_r + cache_c
        context_pct = (context_tokens / DEFAULT_CONTEXT_WINDOW) * 100

    return {
        'session_id': session_id,
        'filepath': str(filepath),
        'first_ts': first_ts,
        'last_ts': last_ts,
        'user_msgs': user_msgs,
        'assistant_msgs': assistant_msgs,
        'user_messages': user_messages,
        'compactions': compactions,
        'context_tokens': context_tokens,
        'context_pct': context_pct,
        'total_input': total_input,
        'total_output': total_output,
        'total_cache_read': total_cache_read,
        'total_cache_creation': total_cache_creation,
    }


def format_recap(session: dict, project: str, cutoff_str: str | None = None) -> str:
    """Format a session analysis as markdown."""
    lines = []

    lines.append(f"## {project}")
    lines.append(f"- **Session:** `{session['session_id']}`")

    if session['first_ts']:
        lines.append(f"- **Started:** {session['first_ts'].strftime('%Y-%m-%d %H:%M')}")
    if session['last_ts']:
        lines.append(f"- **Last message:** {session['last_ts'].strftime('%Y-%m-%d %H:%M')}")

    lines.append(f"- **Turns:** {session['user_msgs']} user / {session['assistant_msgs']} assistant")
    lines.append(f"- **Context (at session end):** {session['context_pct']:.1f}% ({session['context_tokens']:,} tokens)")

    if session['compactions']:
        lines.append(f"- **Compaction:** {len(session['compactions'])} summarization(s)")
        for c in session['compactions'][:3]:
            lines.append(f"  - \"{c[:50]}...\"")
        if len(session['compactions']) > 3:
            lines.append(f"  - ... and {len(session['compactions']) - 3} more")
    else:
        lines.append(f"- **Compaction:** none")

    if session['user_messages']:
        lines.append(f"- **User messages preview:**")
        for msg in session['user_messages'][:10]:
            clean_msg = msg.replace('\n', ' ')[:100]
            lines.append(f"  - {clean_msg}")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract Claude Code conversation recaps")
    parser.add_argument('--since', type=str, help='Only include activity since this datetime (YYYY-MM-DD HH:MM)')
    parser.add_argument('--session', type=str, help='Analyze a specific session ID')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    cutoff = None
    if args.since:
        try:
            cutoff = datetime.strptime(args.since, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"Error: Invalid date format. Use 'YYYY-MM-DD HH:MM'")
            return 1

    if args.session:
        # Find specific session
        for project_dir in PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            session_file = project_dir / f"{args.session}.jsonl"
            if session_file.exists():
                project_name = project_dir.name
                if project_name.startswith("-Users-alex-"):
                    project_name = project_name[len("-Users-alex-"):]
                    if project_name.startswith("-"):
                        project_name = "." + project_name[1:]
                    project_name = "~/" + project_name.replace("-", "/")
                session = analyze_session(session_file, cutoff)
                if args.json:
                    # Convert datetimes for JSON
                    session['first_ts'] = session['first_ts'].isoformat() if session['first_ts'] else None
                    session['last_ts'] = session['last_ts'].isoformat() if session['last_ts'] else None
                    print(json.dumps(session, indent=2))
                else:
                    print(format_recap(session, project_name))
                return 0
        print(f"Session {args.session} not found")
        return 1

    # Find and analyze all matching sessions
    sessions = find_session_files(cutoff)

    if not sessions:
        print("No sessions found matching criteria")
        return 1

    results = []
    for filepath, project in sessions:
        session = analyze_session(filepath, cutoff)
        # Skip sessions with no activity in window
        if cutoff and session['user_msgs'] == 0 and session['assistant_msgs'] == 0:
            continue
        results.append((session, project))

    if args.json:
        output = []
        for session, project in results:
            session['project'] = project
            session['first_ts'] = session['first_ts'].isoformat() if session['first_ts'] else None
            session['last_ts'] = session['last_ts'].isoformat() if session['last_ts'] else None
            output.append(session)
        print(json.dumps(output, indent=2))
    else:
        cutoff_str = args.since if args.since else "all time"
        print(f"# Claude Code Conversations Recap")
        print(f"**Window:** since {cutoff_str}")
        print()

        for session, project in sorted(results, key=lambda x: x[0]['first_ts'] or datetime.min.replace(tzinfo=timezone.utc)):
            print(format_recap(session, project))

    return 0


if __name__ == '__main__':
    exit(main())
