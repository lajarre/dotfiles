#!/usr/bin/env python3
"""
Deterministic extraction of Claude Code session data.

Outputs JSON with:
- Session metadata (id, project, timestamps, context usage)
- Compaction summaries (from automatic summarization)
- Git commits made during the session

Usage:
    python extract.py --since "2026-01-15 08:00"
    python extract.py --since yesterday
    python extract.py --session SESSION_ID
"""

import json
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
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


def parse_since(since_str: str) -> datetime:
    """Parse --since argument to datetime."""
    since_str = since_str.lower().strip()
    now = datetime.now(tz=timezone.utc)

    if since_str == "yesterday":
        # Yesterday 8am local time
        yesterday = now - timedelta(days=1)
        return yesterday.replace(hour=8, minute=0, second=0, microsecond=0)
    elif since_str == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif since_str == "week":
        return now - timedelta(days=7)
    else:
        # Try parsing as datetime
        try:
            dt = datetime.strptime(since_str, '%Y-%m-%d %H:%M')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                dt = datetime.strptime(since_str, '%Y-%m-%d')
                return dt.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
            except ValueError:
                raise ValueError(f"Cannot parse date: {since_str}")


def decode_project_path(dir_name: str) -> str:
    """Convert encoded directory name to readable path."""
    if dir_name.startswith("-Users-alex-"):
        path = dir_name[len("-Users-alex-"):]
        if path.startswith("-"):
            path = "." + path[1:]
        return "~/" + path.replace("-", "/")
    return dir_name


def get_git_commits(cwd: str, since: datetime, until: datetime) -> list[dict]:
    """Get git commits in a directory between two timestamps."""
    if not cwd or not Path(cwd).exists():
        return []

    try:
        # Format timestamps for git
        since_str = since.strftime('%Y-%m-%d %H:%M:%S')
        until_str = until.strftime('%Y-%m-%d %H:%M:%S')

        result = subprocess.run(
            [
                'git', 'log',
                f'--since={since_str}',
                f'--until={until_str}',
                '--format=%H|%s|%ai',
                '--all'
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 2)
            if len(parts) >= 3:
                commits.append({
                    'hash': parts[0][:8],
                    'message': parts[1],
                    'date': parts[2]
                })

        return commits
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def extract_session(filepath: Path, cutoff: datetime | None = None) -> dict | None:
    """Extract data from a single session file."""
    session_id = filepath.stem
    project_dir = filepath.parent.name
    project = decode_project_path(project_dir)

    first_ts = None
    last_ts = None
    user_msgs = 0
    assistant_msgs = 0
    compactions = []
    cwd = None
    last_usage = None

    with open(filepath, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                ts = parse_timestamp(data.get('timestamp'))
                msg_type = data.get('type', '')

                # Track cwd from messages
                if data.get('cwd') and not cwd:
                    cwd = data.get('cwd')

                # Track timestamps
                if ts:
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                # Extract compaction summaries
                if msg_type == 'summary':
                    summary_text = data.get('summary', '')
                    if summary_text:
                        compactions.append({
                            'summary': summary_text
                        })

                # Count messages in window
                in_window = cutoff is None or (ts and ts >= cutoff)

                if msg_type == 'user' and not data.get('isMeta'):
                    if in_window:
                        user_msgs += 1
                elif msg_type == 'assistant':
                    if in_window:
                        assistant_msgs += 1
                    usage = data.get('message', {}).get('usage', {})
                    if usage:
                        last_usage = usage

            except json.JSONDecodeError:
                continue

    # Skip sessions with no activity in window
    if cutoff and user_msgs == 0 and assistant_msgs == 0:
        return None

    # Calculate context usage
    context_tokens = 0
    context_pct = 0.0
    if last_usage:
        input_t = last_usage.get('input_tokens', 0)
        cache_r = last_usage.get('cache_read_input_tokens', 0)
        cache_c = last_usage.get('cache_creation_input_tokens', 0)
        context_tokens = input_t + cache_r + cache_c
        context_pct = round((context_tokens / DEFAULT_CONTEXT_WINDOW) * 100, 1)

    # Get git commits during session
    git_commits = []
    if cwd and first_ts and last_ts:
        git_commits = get_git_commits(cwd, first_ts, last_ts)

    # Dedupe compactions (often repeated)
    seen_summaries = set()
    unique_compactions = []
    for c in compactions:
        if c['summary'] not in seen_summaries:
            seen_summaries.add(c['summary'])
            unique_compactions.append(c)

    return {
        'session_id': session_id,
        'project': project,
        'cwd': cwd,
        'started': first_ts.isoformat() if first_ts else None,
        'ended': last_ts.isoformat() if last_ts else None,
        'context_pct': context_pct,
        'context_tokens': context_tokens,
        'turns': {
            'user': user_msgs,
            'assistant': assistant_msgs
        },
        'compactions': unique_compactions,
        'git_commits': git_commits
    }


def find_sessions(since: datetime | None = None) -> list[Path]:
    """Find all session files, optionally filtered by modification time."""
    sessions = []

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            # Skip subagent files
            if "subagents" in str(jsonl_file):
                continue

            # Check modification time
            if since:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)
                if mtime < since:
                    continue

            sessions.append(jsonl_file)

    return sessions


def main():
    parser = argparse.ArgumentParser(
        description="Extract Claude Code session data as JSON"
    )
    parser.add_argument(
        '--since',
        type=str,
        help='Filter: "yesterday", "today", "week", or "YYYY-MM-DD HH:MM"'
    )
    parser.add_argument(
        '--session',
        type=str,
        help='Extract specific session by ID'
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        help='Pretty-print JSON output'
    )
    args = parser.parse_args()

    cutoff = None
    if args.since:
        try:
            cutoff = parse_since(args.since)
        except ValueError as e:
            print(json.dumps({'error': str(e)}))
            return 1

    if args.session:
        # Find specific session
        for project_dir in PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            session_file = project_dir / f"{args.session}.jsonl"
            if session_file.exists():
                result = extract_session(session_file, cutoff)
                if result:
                    indent = 2 if args.pretty else None
                    print(json.dumps(result, indent=indent))
                    return 0
        print(json.dumps({'error': f'Session {args.session} not found'}))
        return 1

    # Extract all matching sessions
    session_files = find_sessions(cutoff)

    results = []
    for filepath in session_files:
        session = extract_session(filepath, cutoff)
        if session:
            results.append(session)

    # Sort by start time
    results.sort(key=lambda x: x['started'] or '')

    output = {
        'extracted_at': datetime.now(tz=timezone.utc).isoformat(),
        'since': cutoff.isoformat() if cutoff else None,
        'sessions': results
    }

    indent = 2 if args.pretty else None
    print(json.dumps(output, indent=indent))
    return 0


if __name__ == '__main__':
    exit(main())
