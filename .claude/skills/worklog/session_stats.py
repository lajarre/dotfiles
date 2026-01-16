#!/usr/bin/env python3
"""
Quick session stats lookup for Claude Code sessions.

Usage:
    python session_stats.py SESSION_ID
    python session_stats.py --list          # List recent sessions
    python session_stats.py --today         # Show today's sessions
"""

import json
import os
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"


def parse_timestamp(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace('Z', '+00:00')
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def get_session_stats(filepath: Path) -> dict:
    """Get quick stats for a session."""
    session_id = filepath.stem
    file_size = filepath.stat().st_size
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)

    first_ts = None
    last_ts = None
    user_count = 0
    assistant_count = 0
    summary_count = 0
    last_usage = None

    with open(filepath, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                ts = parse_timestamp(data.get('timestamp'))
                msg_type = data.get('type', '')

                if ts:
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                if msg_type == 'user' and not data.get('isMeta'):
                    user_count += 1
                elif msg_type == 'assistant':
                    assistant_count += 1
                    usage = data.get('message', {}).get('usage', {})
                    if usage:
                        last_usage = usage
                elif msg_type == 'summary':
                    summary_count += 1

            except json.JSONDecodeError:
                continue

    context_tokens = 0
    context_pct = 0.0
    if last_usage:
        input_t = last_usage.get('input_tokens', 0)
        cache_r = last_usage.get('cache_read_input_tokens', 0)
        cache_c = last_usage.get('cache_creation_input_tokens', 0)
        context_tokens = input_t + cache_r + cache_c
        context_pct = (context_tokens / 200000) * 100

    return {
        'session_id': session_id,
        'file_size': file_size,
        'mtime': mtime,
        'first_ts': first_ts,
        'last_ts': last_ts,
        'user_count': user_count,
        'assistant_count': assistant_count,
        'summary_count': summary_count,
        'context_tokens': context_tokens,
        'context_pct': context_pct,
    }


def find_session(session_id: str) -> tuple[Path, str] | None:
    """Find a session file by ID."""
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        session_file = project_dir / f"{session_id}.jsonl"
        if session_file.exists():
            project_name = project_dir.name
            if project_name.startswith("-Users-alex-"):
                project_name = project_name[len("-Users-alex-"):]
                if project_name.startswith("-"):
                    project_name = "." + project_name[1:]
                project_name = "~/" + project_name.replace("-", "/")
            return session_file, project_name
    return None


def list_recent_sessions(days: int = 7) -> list[tuple[Path, str, datetime]]:
    """List sessions modified in the last N days."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    sessions = []

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            if "subagents" in str(jsonl_file):
                continue

            mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                project_name = project_dir.name
                if project_name.startswith("-Users-alex-"):
                    project_name = project_name[len("-Users-alex-"):]
                    if project_name.startswith("-"):
                        project_name = "." + project_name[1:]
                    project_name = "~/" + project_name.replace("-", "/")
                sessions.append((jsonl_file, project_name, mtime))

    return sorted(sessions, key=lambda x: x[2], reverse=True)


def main():
    parser = argparse.ArgumentParser(description="Quick Claude Code session stats")
    parser.add_argument('session_id', nargs='?', help='Session ID to look up')
    parser.add_argument('--list', action='store_true', help='List recent sessions')
    parser.add_argument('--today', action='store_true', help='Show today\'s sessions')
    parser.add_argument('--days', type=int, default=7, help='Days to look back (default: 7)')
    args = parser.parse_args()

    if args.list or args.today:
        days = 1 if args.today else args.days
        sessions = list_recent_sessions(days)

        if not sessions:
            print(f"No sessions found in the last {days} day(s)")
            return 1

        print(f"Sessions from last {days} day(s):\n")
        for filepath, project, mtime in sessions:
            stats = get_session_stats(filepath)
            print(f"{stats['session_id'][:8]}...  {stats['context_pct']:5.1f}%  {stats['user_count']:3}u/{stats['assistant_count']:3}a  {mtime.strftime('%m-%d %H:%M')}  {project}")

        return 0

    if not args.session_id:
        parser.print_help()
        return 1

    result = find_session(args.session_id)
    if not result:
        print(f"Session {args.session_id} not found")
        return 1

    filepath, project = result
    stats = get_session_stats(filepath)

    print(f"Session: {stats['session_id']}")
    print(f"Project: {project}")
    print(f"Started: {stats['first_ts'].strftime('%Y-%m-%d %H:%M') if stats['first_ts'] else 'unknown'}")
    print(f"Last:    {stats['last_ts'].strftime('%Y-%m-%d %H:%M') if stats['last_ts'] else 'unknown'}")
    print(f"Turns:   {stats['user_count']} user / {stats['assistant_count']} assistant")
    print(f"Context: {stats['context_pct']:.1f}% ({stats['context_tokens']:,} tokens)")
    print(f"Compactions: {stats['summary_count']}")
    print(f"File size: {stats['file_size']:,} bytes")

    return 0


if __name__ == '__main__':
    exit(main())
