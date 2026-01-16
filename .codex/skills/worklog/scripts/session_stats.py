#!/usr/bin/env python3
"""
Quick session stats lookup for Codex sessions.

Usage:
    python session_stats.py SESSION_ID
    python session_stats.py --list          # List recent sessions
    python session_stats.py --today         # Show today's sessions
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow importing extract.py from same directory.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import (
    SESSIONS_DIR,
    context_sample_from_info,
    count_threshold_hits,
    decode_cwd,
    parse_timestamp,
)


def get_session_stats(filepath: Path) -> dict:
    session_id = None
    cwd = None
    file_size = filepath.stat().st_size
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)

    first_ts = None
    last_ts = None
    user_count = 0
    assistant_count = 0
    context_samples = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = parse_timestamp(data.get("timestamp"))
            if ts:
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts

            if data.get("type") == "session_meta":
                payload = data.get("payload", {})
                session_id = payload.get("id") or session_id
                cwd = payload.get("cwd") or cwd
                continue

            if data.get("type") == "event_msg":
                payload = data.get("payload", {})
                if payload.get("type") == "token_count":
                    sample = context_sample_from_info(payload.get("info"), ts)
                    if sample:
                        context_samples.append(sample)
                continue

            if data.get("type") != "response_item":
                continue

            payload = data.get("payload", {})
            if payload.get("type") == "message":
                role = payload.get("role")
                if role == "user":
                    user_count += 1
                elif role == "assistant":
                    assistant_count += 1

    context_end = context_samples[-1] if context_samples else None
    context_pct = context_end.pct if context_end else 0.0
    context_tokens = context_end.tokens if context_end else 0
    rot_hits = count_threshold_hits(context_samples, 80.0)
    smash_hits = count_threshold_hits(context_samples, 99.0)

    return {
        "session_id": session_id or filepath.stem,
        "cwd": decode_cwd(cwd),
        "file_size": file_size,
        "mtime": mtime,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_count": user_count,
        "assistant_count": assistant_count,
        "context_pct": context_pct,
        "context_tokens": context_tokens,
        "rot_hits": rot_hits,
        "smash_hits": smash_hits,
    }


def find_session(session_id: str) -> Path | None:
    if not SESSIONS_DIR.exists():
        return None
    for path in SESSIONS_DIR.rglob(f"*{session_id}*.jsonl"):
        if path.is_file():
            return path
    return None


def list_recent_sessions(days: int = 7) -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    sessions: list[Path] = []
    for path in SESSIONS_DIR.rglob("rollout-*.jsonl"):
        if not path.is_file():
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if mtime >= cutoff:
            sessions.append(path)
    return sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick Codex session stats")
    parser.add_argument("session_id", nargs="?", help="Session ID to look up")
    parser.add_argument("--list", action="store_true", help="List recent sessions")
    parser.add_argument("--today", action="store_true", help="Show today's sessions")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    args = parser.parse_args()

    if args.list or args.today:
        days = 1 if args.today else args.days
        sessions = list_recent_sessions(days)
        if not sessions:
            print(f"No sessions found in the last {days} day(s)")
            return 1

        print(f"Sessions from last {days} day(s):\n")
        for path in sessions:
            stats = get_session_stats(path)
            ts = stats["mtime"].astimezone().strftime("%m-%d %H:%M")
            print(
                f"{stats['session_id'][:8]}...  {stats['context_pct']:5.1f}%  "
                f"rot {stats['rot_hits']:2} smash {stats['smash_hits']:2}  "
                f"{stats['user_count']:3}u/{stats['assistant_count']:3}a  {ts}  {stats['cwd']}"
            )
        return 0

    if not args.session_id:
        parser.print_help()
        return 1

    path = find_session(args.session_id)
    if not path:
        print(f"Session {args.session_id} not found")
        return 1

    stats = get_session_stats(path)
    print(f"Session: {stats['session_id']}")
    print(f"Project: {stats['cwd']}")
    print(f"Started: {stats['first_ts'].astimezone().strftime('%Y-%m-%d %H:%M') if stats['first_ts'] else 'unknown'}")
    print(f"Last:    {stats['last_ts'].astimezone().strftime('%Y-%m-%d %H:%M') if stats['last_ts'] else 'unknown'}")
    print(f"Turns:   {stats['user_count']} user / {stats['assistant_count']} assistant")
    print(f"Context: {stats['context_pct']:.1f}% ({stats['context_tokens']:,} tokens)")
    print(f"Context hits: rot {stats['rot_hits']}, smash {stats['smash_hits']}")
    print(f"File size: {stats['file_size']:,} bytes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
