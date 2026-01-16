#!/usr/bin/env python3
"""
Generate a human-readable recap of Codex sessions.

Usage:
    python conversation_recap.py --since "2026-01-15 08:00"
    python conversation_recap.py --session SESSION_ID
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Allow importing extract.py from same directory.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import extract_sessions, parse_since  # noqa: E402


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_dt_local(dt: datetime | None) -> str:
    if not dt:
        return "unknown"
    return dt.astimezone().strftime("%b %d %H:%M")


def _format_duration(start: datetime | None, end: datetime | None) -> str:
    if not start or not end:
        return "unknown"
    delta = end - start
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _shorten(text: str, limit: int = 120) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "..."


def _summarize_sessions(sessions: list[dict]) -> list[str]:
    if not sessions:
        return ["No sessions in this window."]

    projects = {s.get("cwd") or "unknown" for s in sessions}
    total = len(sessions)
    rot_hits = sum((s.get("context", {}).get("rot_hits", 0) for s in sessions))
    smash_hits = sum((s.get("context", {}).get("smash_hits", 0) for s in sessions))

    topics: list[str] = []
    for s in sessions:
        for t in s.get("topics", [])[:1]:
            if t and t not in topics:
                topics.append(_shorten(t, 80))
            if len(topics) >= 3:
                break
        if len(topics) >= 3:
            break

    lines = [
        f"{total} sessions across {len(projects)} project(s).",
        f"Context stress: {rot_hits} rot hit(s), {smash_hits} smash hit(s).",
    ]
    if topics:
        lines.append("Main topics: " + "; ".join(topics) + ".")

    return [" ".join(lines)]


def _render_session(session: dict) -> str:
    started = _parse_iso(session.get("started"))
    ended = _parse_iso(session.get("ended"))
    duration = _format_duration(started, ended)

    ctx = session.get("context", {})
    ctx_pct = ctx.get("pct", 0.0)
    ctx_tokens = ctx.get("tokens", 0)
    rot_hits = ctx.get("rot_hits", 0)
    smash_hits = ctx.get("smash_hits", 0)

    lines: list[str] = []
    title = session.get("title")
    if not title:
        title = "(no title)"
    lines.append(f"🗨️ \"{_shorten(title, 120)}\"")
    cwd = session.get("cwd")
    if cwd:
        lines.append(cwd)
    else:
        lines.append("(no working folder recorded)")
    lines.append("")
    lines.append(f"- Session: {session.get('session_id')}")
    lines.append(f"- Time: {_format_dt_local(started)} -> {_format_dt_local(ended)} ({duration})")
    lines.append(f"- Context: {ctx_pct:.1f}% ({ctx_tokens:,} tokens)")
    lines.append(f"- Context hits: rot {rot_hits}, smash {smash_hits}")

    lines.append("")
    lines.append("What was discussed:")

    topics = session.get("topics", [])
    files_touched = session.get("files_touched", [])
    commands = session.get("commands", [])

    bullets: list[str] = []
    for topic in topics[:3]:
        bullets.append(_shorten(topic, 120))

    if files_touched:
        shown = ", ".join(files_touched[:6])
        suffix = "" if len(files_touched) <= 6 else ", ..."
        bullets.append(f"Files touched: {shown}{suffix}")

    if not bullets and commands:
        bullets.append(f"Commands run: {_shorten(commands[0], 120)}")

    if not bullets:
        bullets.append("No user prompts captured; activity was mostly tool-driven.")

    for bullet in bullets:
        lines.append(f"- {bullet}")

    lines.append("")
    lines.append("Git commits:")
    commits = session.get("git_commits", [])
    if not commits:
        lines.append("- None")
    else:
        for c in commits:
            lines.append(f"- {c['hash']} {c['message']}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Codex worklog recap")
    parser.add_argument("--since", type=str, help='Filter: "yesterday", "today", "week", or "YYYY-MM-DD HH:MM"')
    parser.add_argument("--session", type=str, help="Generate recap for specific session")
    args = parser.parse_args()

    cutoff = parse_since(args.since)
    sessions = extract_sessions(cutoff, args.session)

    if not sessions:
        print("No sessions found matching criteria")
        return 1

    # Sort sessions by start time.
    def _sort_key(s: dict) -> float:
        started = _parse_iso(s.get("started"))
        return started.timestamp() if started else 0.0

    sessions.sort(key=_sort_key)

    header_start = cutoff.astimezone().strftime("%b %d %H:%M")
    header_end = datetime.now().astimezone().strftime("%b %d %H:%M")

    print(f"Worklog: {header_start} -> {header_end}\n")
    print("Summary\n")
    for line in _summarize_sessions(sessions):
        print(line)
    print("\nSessions\n")

    for session in sessions:
        print()
        print(_render_session(session))
        print("\n---\n")

    print("Next steps:")
    print("1. Resume any session?")
    print("2. Save this recap to a file?")
    print("3. More details on a specific session?")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
