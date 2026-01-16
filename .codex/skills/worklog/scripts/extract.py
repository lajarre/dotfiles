#!/usr/bin/env python3
"""
Deterministic extraction of Codex session data.

Outputs JSON with:
- Session metadata (id, cwd, timestamps)
- User prompts (filtered)
- Tool activity (exec_command, apply_patch)
- Context usage timeline + rot/smash counts
- Git commits made during the session window

Usage:
    python extract.py --since "2026-01-15 08:00"
    python extract.py --since yesterday
    python extract.py --session SESSION_ID
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

CODEX_DIR = Path.home() / ".codex"
SESSIONS_DIR = CODEX_DIR / "sessions"
DEFAULT_CONTEXT_ROT = 80.0
DEFAULT_CONTEXT_SMASH = 99.0


@dataclass
class ContextSample:
    ts: datetime
    pct: float
    tokens: int
    window: int


def parse_timestamp(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _localize(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_local_now().tzinfo)
    return dt


def parse_since(since_str: str | None) -> datetime:
    """Parse --since argument to UTC datetime.

    Default: yesterday at 08:00 local time.
    """
    now_local = _local_now()

    if not since_str:
        yesterday = now_local - timedelta(days=1)
        cutoff_local = yesterday.replace(hour=8, minute=0, second=0, microsecond=0)
        return cutoff_local.astimezone(timezone.utc)

    value = since_str.strip().lower()

    if value == "yesterday":
        yesterday = now_local - timedelta(days=1)
        cutoff_local = yesterday.replace(hour=8, minute=0, second=0, microsecond=0)
        return cutoff_local.astimezone(timezone.utc)
    if value == "today":
        cutoff_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return cutoff_local.astimezone(timezone.utc)
    if value == "week":
        return (now_local - timedelta(days=7)).astimezone(timezone.utc)

    # Try parsing explicit date/time.
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
        return _localize(dt).astimezone(timezone.utc)
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
            return _localize(dt.replace(hour=0, minute=0, second=0, microsecond=0)).astimezone(timezone.utc)
        except ValueError as exc:
            raise ValueError(f"Cannot parse date: {since_str}") from exc


def decode_cwd(path: str | None) -> str | None:
    if not path:
        return None
    home = str(Path.home())
    if path.startswith(home):
        rest = path[len(home):]
        if not rest:
            return "~"
        if rest.startswith("/"):
            return "~" + rest
        return "~/" + rest
    return path


def _shorten(text: str, limit: int = 120) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def is_noise_user_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if lowered.startswith("# agents.md instructions"):
        return True
    if lowered.startswith("<environment_context>"):
        return True
    if lowered.startswith("<instructions>"):
        return True
    if "agents.md" in lowered and "instructions" in lowered:
        return True
    if lowered.startswith("<user_shell_command>"):
        return True
    return False


def extract_text(content_items: Iterable[dict] | None) -> str:
    if not content_items:
        return ""
    parts: list[str] = []
    for item in content_items:
        if item.get("type") in ("input_text", "output_text", "text"):
            parts.append(item.get("text", ""))
    return "".join(parts)


def derive_title(topics: list[str], commands: list[str], files_touched: Iterable[str]) -> str | None:
    if topics:
        return _shorten(topics[0], 120)
    if commands:
        return _shorten(f"cmd: {commands[0]}", 120)
    for path in files_touched:
        return _shorten(f"files: {path}", 120)
    return None


def parse_patch_files(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("*** Update File: "):
            files.append(line[len("*** Update File: "):].strip())
        elif line.startswith("*** Add File: "):
            files.append(line[len("*** Add File: "):].strip())
        elif line.startswith("*** Delete File: "):
            files.append(line[len("*** Delete File: "):].strip())
        elif line.startswith("*** Move to: "):
            files.append(line[len("*** Move to: "):].strip())
    return files


def context_sample_from_info(info: dict | None, ts: datetime | None) -> ContextSample | None:
    if not info or not ts:
        return None

    window = info.get("model_context_window")
    usage = info.get("last_token_usage") or info.get("total_token_usage")
    if not window or not usage:
        return None

    input_tokens = usage.get("input_tokens", 0)
    cached_tokens = usage.get("cached_input_tokens", 0)
    tokens = int(input_tokens + cached_tokens)
    pct = round((tokens / window) * 100, 1)
    return ContextSample(ts=ts, pct=pct, tokens=tokens, window=int(window))


def count_threshold_hits(samples: list[ContextSample], threshold: float) -> int:
    hits = 0
    prev = False
    for sample in samples:
        now = sample.pct >= threshold
        if now and not prev:
            hits += 1
        prev = now
    return hits


def get_git_commits(cwd: str | None, since: datetime | None, until: datetime | None) -> list[dict]:
    if not cwd or not Path(cwd).exists() or not since or not until:
        return []

    try:
        since_local = since.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        until_local = until.astimezone().strftime("%Y-%m-%d %H:%M:%S")

        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={since_local}",
                f"--until={until_local}",
                "--format=%H|%s|%ai",
                "--all",
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        commits: list[dict] = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) >= 3:
                commits.append({
                    "hash": parts[0][:8],
                    "message": parts[1],
                    "date": parts[2],
                })
        return commits
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def find_session_files(since: datetime | None = None) -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []

    paths = [p for p in SESSIONS_DIR.rglob("rollout-*.jsonl") if p.is_file()]

    if since:
        cutoff = since.astimezone(timezone.utc)
        filtered: list[Path] = []
        for p in paths:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                filtered.append(p)
        paths = filtered

    return sorted(paths)


def extract_session(filepath: Path, cutoff: datetime | None = None) -> dict | None:
    session_id = None
    cwd = None
    first_ts = None
    last_ts = None
    user_msgs = 0
    assistant_msgs = 0
    user_topics: list[str] = []
    commands: list[str] = []
    files_touched: set[str] = set()
    context_samples: list[ContextSample] = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
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

            in_window = cutoff is None or (ts and ts >= cutoff)

            if data.get("type") == "event_msg":
                payload = data.get("payload", {})
                if payload.get("type") == "token_count":
                    if in_window:
                        sample = context_sample_from_info(payload.get("info"), ts)
                        if sample:
                            context_samples.append(sample)
                continue

            if data.get("type") != "response_item":
                continue

            payload = data.get("payload", {})
            ptype = payload.get("type")

            if ptype == "message":
                role = payload.get("role")
                text = extract_text(payload.get("content"))
                if role == "user" and in_window:
                    if not is_noise_user_text(text):
                        user_msgs += 1
                        if len(user_topics) < 10:
                            user_topics.append(text.strip())
                elif role == "assistant" and in_window:
                    if text.strip():
                        assistant_msgs += 1
                continue

            if not in_window:
                continue

            if ptype == "function_call" and payload.get("name") == "exec_command":
                try:
                    args = json.loads(payload.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}
                cmd = args.get("cmd")
                if cmd:
                    commands.append(cmd)
                continue

            if ptype == "custom_tool_call" and payload.get("name") == "apply_patch":
                patch_text = payload.get("input", "")
                for path in parse_patch_files(patch_text):
                    files_touched.add(path)
                continue

    # Skip sessions with no activity in the window
    if cutoff and user_msgs == 0 and assistant_msgs == 0 and not commands and not files_touched:
        return None

    # Normalize cwd for display
    cwd_display = decode_cwd(cwd)

    # Context summary
    context_end = context_samples[-1] if context_samples else None
    context_pct = context_end.pct if context_end else 0.0
    context_tokens = context_end.tokens if context_end else 0
    context_window = context_end.window if context_end else 0
    context_max_pct = max((s.pct for s in context_samples), default=0.0)

    rot_hits = count_threshold_hits(context_samples, DEFAULT_CONTEXT_ROT)
    smash_hits = count_threshold_hits(context_samples, DEFAULT_CONTEXT_SMASH)

    title = derive_title(user_topics, commands, sorted(files_touched))
    git_commits = get_git_commits(cwd, first_ts, last_ts)

    return {
        "session_id": session_id or filepath.stem,
        "filepath": str(filepath),
        "cwd": cwd_display,
        "title": title,
        "started": first_ts.isoformat() if first_ts else None,
        "ended": last_ts.isoformat() if last_ts else None,
        "turns": {
            "user": user_msgs,
            "assistant": assistant_msgs,
        },
        "topics": user_topics,
        "commands": commands,
        "files_touched": sorted(files_touched),
        "context": {
            "pct": context_pct,
            "tokens": context_tokens,
            "window": context_window,
            "max_pct": context_max_pct,
            "rot_hits": rot_hits,
            "smash_hits": smash_hits,
        },
        "git_commits": git_commits,
    }


def extract_sessions(since: datetime | None = None, session_id: str | None = None) -> list[dict]:
    sessions: list[dict] = []

    for path in find_session_files(since):
        if session_id and session_id not in path.stem:
            # session_id is part of the filename; quick filter.
            continue
        session = extract_session(path, since)
        if session:
            sessions.append(session)

    return sessions


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Codex session data as JSON")
    parser.add_argument("--since", type=str, help='Filter: "yesterday", "today", "week", or "YYYY-MM-DD HH:MM"')
    parser.add_argument("--session", type=str, help="Extract specific session by ID")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    cutoff = parse_since(args.since)
    sessions = extract_sessions(cutoff, args.session)

    if not sessions:
        print("No sessions found matching criteria")
        return 1

    if args.pretty:
        print(json.dumps(sessions, indent=2))
    else:
        print(json.dumps(sessions))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
