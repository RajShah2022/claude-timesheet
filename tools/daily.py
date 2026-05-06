#!/usr/bin/env python3
"""
Extract user messages from Claude Code JSONL sessions, grouped by local day.
Prints a human-readable per-day work log to stdout (or --output file).

Usage:
    daily.py [--month "Feb 2026"] [--project myapp] [--output /tmp/out.txt]
"""
import sys, json, re, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

PROJECTS_DIR = Path.home() / ".claude" / "projects"


def parse_time_range(time_str):
    """Accept a month ('Feb 2026', '2026-02') or exact date ('12 Feb 2026', '2026-02-12')."""
    local_tz = datetime.now().astimezone().tzinfo

    if not time_str:
        now = datetime.now(local_tz)
        start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=local_tz)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1, 0, 0, 0, tzinfo=local_tz)
        else:
            end = datetime(now.year, now.month + 1, 1, 0, 0, 0, tzinfo=local_tz)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc), local_tz, f"{now.year:04d}-{now.month:02d}"

    # Try exact-date formats first (they include a day component)
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%b %d %Y", "%B %d %Y"):
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            start = datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=local_tz)
            end   = start + timedelta(days=1)
            return start.astimezone(timezone.utc), end.astimezone(timezone.utc), local_tz, start.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Fall back to month-only formats
    for fmt in ("%Y-%m", "%b %Y", "%B %Y"):
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            year, month = dt.year, dt.month
            start = datetime(year, month, 1, 0, 0, 0, tzinfo=local_tz)
            if month == 12:
                end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=local_tz)
            else:
                end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=local_tz)
            return start.astimezone(timezone.utc), end.astimezone(timezone.utc), local_tz, f"{year:04d}-{month:02d}"
        except ValueError:
            continue

    sys.exit(
        f"Cannot parse {time_str!r}. "
        "Use '12 Feb 2026', '2026-02-12' for a day, or 'Feb 2026', '2026-02' for a month."
    )


def proj_label(d: Path) -> str:
    username = Path.home().name
    noise = frozenset({
        "home", "users", "user", "downloads", "documents", "desktop",
        "code", "projects", "dev", "workspace", "src", "repos", username,
    })
    parts = [p for p in d.name.split("-") if p and p.lower() not in noise and len(p) > 1]
    return "-".join(parts[-3:]) if parts else d.name


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.rstrip("Z").split(".")[0]).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def quick_peek(path: Path):
    try:
        with open(path, "rb") as f:
            first_line = f.readline().decode("utf-8", errors="replace")
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 4096)
            f.seek(size - chunk)
            tail = f.read().decode("utf-8", errors="replace")
            last_line = tail.rstrip("\n").rsplit("\n", 1)[-1]
        first_ts = parse_ts(json.loads(first_line).get("timestamp"))
        last_ts  = parse_ts(json.loads(last_line).get("timestamp"))
        return first_ts, last_ts
    except Exception:
        return None, None


_NOISE_PATTERNS = re.compile(
    r"your task is to create a (detailed )?summary"
    r"|SUGGESTION MODE"
    r"|Request interrupted by user"
    r"|suggest what the user might naturally type"
    r"|paying close attention to the user.s explicit requests"
    r"|<local-command-caveat>"
    r"|<local-command-stdout>"
    r"|<command-name>"
    r"|Base directory for this skill"
    r"|This session is being continued from a previous conversation",
    re.IGNORECASE,
)


def clean_text(content):
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("text")]
        content = "\n".join(parts)
    text = str(content or "").strip()

    if _NOISE_PATTERNS.search(text[:1000]):
        return ""

    text = re.sub(r'[A-Za-z0-9+/]{60,}={0,2}', '[binary]', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text[:600].strip()


def main():
    ap = argparse.ArgumentParser(description="Per-day work log from Claude Code sessions")
    ap.add_argument("--month", default="", help="Month or exact date to extract (e.g. 'Feb 2026', '2026-02', '12 Feb 2026', '2026-02-12'). Defaults to current month.")
    ap.add_argument("--project", default="", help="Restrict to project dirs matching this substring.")
    ap.add_argument("--output", default="", help="Write output to this file instead of stdout.")
    args = ap.parse_args()

    after_utc, before_utc, local_tz, month_label = parse_time_range(args.month)
    print(f"Range: {month_label} | UTC: {after_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} → {before_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}", file=sys.stderr, flush=True)

    # Candidate project dirs
    proj_dirs = [d for d in sorted(PROJECTS_DIR.iterdir()) if d.is_dir()]
    if args.project:
        proj_dirs = [d for d in proj_dirs if args.project.lower() in d.name.lower()]

    # Candidate files
    all_files = []
    after_mtime = after_utc.timestamp()
    for d in proj_dirs:
        proj = proj_label(d)
        for f in d.rglob("*.jsonl"):
            if f.stat().st_mtime < after_mtime:
                continue
            first_ts, last_ts = quick_peek(f)
            if last_ts and last_ts < after_utc:
                continue
            if first_ts and first_ts >= before_utc:
                continue
            all_files.append((proj, f))

    print(f"Files to parse: {len(all_files)}", file=sys.stderr, flush=True)

    # Extract user messages grouped by local day
    day_events = defaultdict(list)
    total = 0
    for proj, f in all_files:
        try:
            with open(f, "r", errors="replace") as fh:
                for line in fh:
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    ts = parse_ts(entry.get("timestamp"))
                    if not ts or ts < after_utc or ts >= before_utc:
                        continue

                    role = (entry.get("message") or {}).get("role") or entry.get("role") or ""
                    if role not in ("user", "human"):
                        continue

                    content = (entry.get("message") or {}).get("content") or entry.get("content") or ""
                    # Skip pure tool result turns
                    if isinstance(content, list):
                        items = content
                        if all(isinstance(i, dict) and i.get("type") in ("tool_result", "tool_use") for i in items):
                            continue

                    # Skip slash commands
                    if isinstance(content, str) and content.lstrip().startswith("/"):
                        continue

                    text = clean_text(content)
                    if not text or len(text) < 10:
                        continue

                    local_dt = ts.astimezone(local_tz)
                    day_key  = local_dt.strftime("%Y-%m-%d")
                    time_str = local_dt.strftime("%H:%M")
                    day_events[day_key].append((ts, time_str, proj, text))
                    total += 1
        except Exception:
            pass

    print(f"User messages extracted: {total}", file=sys.stderr, flush=True)

    # Write output
    out = open(args.output, "w") if args.output else sys.stdout
    try:
        for day in sorted(day_events.keys()):
            evts = sorted(day_events[day], key=lambda x: x[0])
            day_dt = datetime.strptime(day, "%Y-%m-%d")
            out.write(f"\n{'=' * 70}\n")
            out.write(f"  {day_dt.strftime('%A, %d %B %Y')}  ({len(evts)} messages)\n")
            out.write(f"{'=' * 70}\n\n")
            last_text = ""
            for ts, time_str, proj, text in evts:
                if text[:80] == last_text[:80]:
                    continue
                last_text = text
                out.write(f"  [{time_str}] [{proj}]\n")
                for line in text.split("\n"):
                    out.write(f"    {line}\n")
                out.write("\n")
    finally:
        if args.output:
            out.close()

    print(f"Days with activity: {len(day_events)}", file=sys.stderr)


if __name__ == "__main__":
    main()
