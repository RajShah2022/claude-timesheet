#!/usr/bin/env python3
"""
Monthly timesheet generator from Claude Code JSONL sessions.

Usage:
    timesheet.py [--month "Feb 2026"] [--project myapp]

Output:
    1. Per-day breakdown: all real user messages + key agent task descriptions
    2. Monthly summary grouped by project + theme

Main session files (depth-1 under project dir) contain real user messages.
Sub-agent session files (subdirectories) contain agent task injections — these
are labelled as [agent] in the per-day view.

Timezone is auto-detected from the system.
"""
import sys, json, re, argparse
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

PROJECTS_DIR = Path.home() / ".claude" / "projects"
IDLE_GAP = 1800  # 30 min gap ends a session

THEME_PATTERNS = [
    ("Import and export, data migration",           r"docker.compose|export|import|minio|postgres|redis|backup|restore"),
    ("Backend API, services, models",               r"api|router|service|model|schema|endpoint|fastapi|sqlalchemy|alembic|django|express|rails"),
    ("Frontend UI, components, views",              r"flutter|widget|screen|component|view|react|nextjs|page|ui|frontend|css|html|svelte|vue"),
    ("Authentication and authorization",            r"keycloak|auth|oauth|token|jwt|login|permission|role|session|password"),
    ("Database migrations and schema changes",      r"migrat|alembic|schema|table|column|alter|drop|create table|prisma|knex"),
    ("DevOps, Docker, deployment",                  r"docker|docker-compose|deploy|nginx|ci|pipeline|build|yml|kubernetes|helm|terraform"),
    ("Claude API and AI integration",               r"claude|anthropic|llm|ai|prompt|chat|message|agent|openai|gemini"),
    ("Automation and bots",                         r"task.*bot|automation|cron|scheduler|remind|telegram|bot|webhook|script"),
    ("Bug fixes and QA",                            r"fix|bug|error|issue|test|assert|fail|crash|exception|debug|broken"),
    ("Documentation and setup",                     r"readme|doc|setup|install|config|env|\.md|onboard"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_month(month_str):
    local_tz = datetime.now().astimezone().tzinfo
    if not month_str:
        now = datetime.now(local_tz)
        year, month = now.year, now.month
    else:
        for fmt in ("%Y-%m", "%b %Y", "%B %Y"):
            try:
                dt = datetime.strptime(month_str.strip(), fmt)
                year, month = dt.year, dt.month
                break
            except ValueError:
                continue
        else:
            sys.exit(f"Cannot parse month: {month_str!r}. Use YYYY-MM, 'Feb 2026', or 'February 2026'.")

    start = datetime(year, month, 1, 0, 0, 0, tzinfo=local_tz)
    end   = datetime(year + (month == 12), (month % 12) + 1, 1, 0, 0, 0, tzinfo=local_tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc), local_tz, f"{year:04d}-{month:02d}"


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


def extract_snippet(entry):
    content = entry.get("message", {}).get("content") or entry.get("content") or ""
    if isinstance(content, list):
        parts = [c.get("text") or c.get("input", {}).get("command", "") or ""
                 for c in content if isinstance(c, dict)]
        content = " ".join(parts)
    return re.sub(r"\s+", " ", str(content))[:240]


# Patterns that indicate a system-injected or internal message
_NOISE_PATTERNS = re.compile(
    r"your task is to create a (detailed )?summary"
    r"|SUGGESTION MODE"
    r"|Request interrupted by user"
    r"|suggest what the user might naturally type"
    r"|paying close attention to the user.s explicit requests"
    r"|^\s*\[binary\]\s*$",
    re.IGNORECASE,
)


def clean_text(content):
    """Return full cleaned text from raw message content, or '' if system noise."""
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("text")]
        content = "\n".join(parts)
    text = str(content or "").strip()

    if _NOISE_PATTERNS.search(text[:400]):
        return ""

    # Drop base64/binary blobs
    text = re.sub(r'[A-Za-z0-9+/]{60,}={0,2}', '', text)
    # Shorten absolute paths to last 2 segments
    text = re.sub(r'/(?:[^\s/]+/){3,}([^\s/]+/[^\s/]+)', r'.../\1', text)
    # Collapse excess blank lines
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    return text if len(text) >= 10 else ""


def classify(snippets):
    combined = " ".join(snippets).lower()
    scores = {theme: len(re.findall(pat, combined)) for theme, pat in THEME_PATTERNS}
    scores = {k: v for k, v in scores.items() if v > 0}
    return max(scores, key=scores.get) if scores else "General development"


def dedup_entries(entries):
    """Remove entries whose first 60 chars are near-identical to an earlier one."""
    seen, result = [], []
    for item in entries:
        key = re.sub(r'\s+', ' ', item[-1][:60].lower())
        if key not in seen:
            seen.append(key)
            result.append(item)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Monthly timesheet from Claude Code sessions")
    ap.add_argument("--month", default="", help="Month to summarise (e.g. 'Feb 2026' or '2026-02'). Defaults to current month.")
    ap.add_argument("--project", default="", help="Restrict to project dirs matching this substring.")
    args = ap.parse_args()

    after_utc, before_utc, local_tz, month_label = parse_month(args.month)
    print(f"Month: {month_label} | UTC range: {after_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} → {before_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}", flush=True)

    # Stage 1: candidate project dirs + files
    # Track whether each file is a main session (depth 1) or sub-agent session (depth 2+)
    proj_dirs = [d for d in sorted(PROJECTS_DIR.iterdir()) if d.is_dir()]
    if args.project:
        proj_dirs = [d for d in proj_dirs if args.project.lower() in d.name.lower()]

    main_files  = []   # (proj, path) — direct children of project dir
    agent_files = []   # (proj, path) — subdirectory sessions (sub-agent runs)
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
            if f.parent == d:
                main_files.append((proj, f))
            else:
                agent_files.append((proj, f))

    all_files = main_files + agent_files
    print(f"Files after filter: {len(all_files)} ({len(main_files)} main, {len(agent_files)} agent)", flush=True)

    # Stage 2: extract events
    # all_events[proj]  = [(epoch, snippet)]           — for hours/themes
    # day_entries[date] = [(epoch, time_str, label, proj, text)]  — for per-day display
    #   label "user"  = real user input from ~/.claude/history.jsonl
    #   label "agent" = sub-agent task description or first assistant response
    all_events  = defaultdict(list)
    day_entries = defaultdict(list)
    total_lines = 0

    def maybe_add(epoch, time_str, label, proj, text):
        if not text:
            return
        day_key = datetime.fromtimestamp(epoch, tz=local_tz).strftime("%Y-%m-%d")
        day_entries[day_key].append((epoch, time_str, label, proj, text))

    # Stage 2a: real user messages from ~/.claude/history.jsonl
    # Each entry: {display, timestamp (ms), project, sessionId}
    # Project path → label mapping (last path segment, same logic as proj_label)
    history_file = Path.home() / ".claude" / "history.jsonl"
    history_days_covered = set()
    if history_file.exists():
        with open(history_file, "r", errors="replace") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                    epoch = entry.get("timestamp", 0) / 1000.0
                    ts = datetime.fromtimestamp(epoch, tz=timezone.utc)
                    if ts < after_utc or ts >= before_utc:
                        continue
                    display = str(entry.get("display") or "").strip()
                    if not display or display.startswith("/") or len(display) < 5:
                        continue
                    # Map the project path to a project label
                    proj_path = entry.get("project", "")
                    proj = proj_path.rstrip("/").split("/")[-1] if proj_path else "unknown"
                    time_str = ts.astimezone(local_tz).strftime("%H:%M")
                    text = clean_text(display)
                    if text:
                        maybe_add(epoch, time_str, "user", proj, text)
                        history_days_covered.add(ts.astimezone(local_tz).strftime("%Y-%m-%d"))
                except Exception:
                    pass
    print(f"User messages from history.jsonl: {sum(len(v) for v in day_entries.values())}", flush=True)

    # Stage 2b: sub-agent task descriptions and first assistant responses from JSONL files
    # For days NOT covered by history.jsonl, sub-agent task descriptions fill in user intent.
    # For ALL days, first assistant response per file shows what was done.
    for proj, f in all_files:
        try:
            first_user_done   = False
            first_asst_done   = False
            with open(f, "r", errors="replace") as fh:
                for line in fh:
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    ts = parse_ts(entry.get("timestamp"))
                    if not ts or ts < after_utc or ts >= before_utc:
                        continue

                    snippet = extract_snippet(entry)
                    all_events[proj].append((ts.timestamp(), snippet))
                    total_lines += 1

                    local_dt = ts.astimezone(local_tz)
                    day_key  = local_dt.strftime("%Y-%m-%d")
                    time_str = local_dt.strftime("%H:%M")
                    role = (entry.get("message") or {}).get("role") or entry.get("role") or ""
                    content = (entry.get("message") or {}).get("content") or entry.get("content") or ""

                    # Sub-agent task description: first user message per file
                    # Only add as "agent" label if history.jsonl didn't cover this day
                    if role in ("user", "human") and not first_user_done:
                        if isinstance(content, list):
                            if all(isinstance(i, dict) and i.get("type") in ("tool_result", "tool_use")
                                   for i in content):
                                continue
                        text = clean_text(content)
                        if text:
                            label = "agent" if day_key in history_days_covered else "user"
                            maybe_add(ts.timestamp(), time_str, label, proj, text)
                            first_user_done = True

                    # First assistant text response per file — always useful
                    elif role == "assistant" and not first_asst_done:
                        text_parts = []
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                        else:
                            text_parts = [str(content)]
                        text = clean_text(" ".join(text_parts))
                        if text:
                            maybe_add(ts.timestamp(), time_str, "agent", proj, text)
                            first_asst_done = True
        except Exception:
            pass

    print(f"Total in-range JSONL events: {total_lines}", flush=True)

    # Stage 3: per-day hours (combined sessions, attributed to start day)
    day_hours = defaultdict(float)
    combined = sorted(
        (epoch, proj, snip)
        for proj, evts in all_events.items()
        for epoch, snip in evts
    )
    if combined:
        s_start = combined[0][0]
        s_prev  = combined[0][0]
        for epoch, proj, snip in combined[1:]:
            if epoch - s_prev > IDLE_GAP:
                start_day = datetime.fromtimestamp(s_start, tz=local_tz).strftime("%Y-%m-%d")
                day_hours[start_day] += (s_prev - s_start) / 3600.0
                s_start = epoch
            s_prev = epoch
        start_day = datetime.fromtimestamp(s_start, tz=local_tz).strftime("%Y-%m-%d")
        day_hours[start_day] += (s_prev - s_start) / 3600.0

    # Stage 4: per-project hours + themes
    proj_hours = {}
    proj_themes = {}
    for proj, evts in all_events.items():
        evts.sort(key=lambda x: x[0])
        sessions = []
        s_start = evts[0][0]; s_prev = evts[0][0]; s_snips = [evts[0][1]]
        for epoch, snip in evts[1:]:
            if epoch - s_prev > IDLE_GAP:
                sessions.append((s_start, s_prev, s_snips))
                s_start, s_snips = epoch, []
            s_prev = epoch
            s_snips.append(snip)
        sessions.append((s_start, s_prev, s_snips))
        proj_hours[proj]  = sum(e - s for s, e, _ in sessions) / 3600.0
        proj_themes[proj] = sessions

    theme_hours = defaultdict(float)
    for proj, sessions in proj_themes.items():
        for start, end, snips in sessions:
            theme_hours[(proj, classify(snips))] += (end - start) / 3600.0

    # ── Output ────────────────────────────────────────────────────────────────

    # Part 1: per-day breakdown
    print()
    for day in sorted(day_entries.keys()):
        day_dt   = datetime.strptime(day, "%Y-%m-%d")
        hrs      = day_hours.get(day, 0.0)
        entries  = sorted(day_entries[day], key=lambda x: x[0])

        # Deduplicate within each label group independently, then merge back
        user_msgs  = dedup_entries([(e, t, l, p, x) for e, t, l, p, x in entries if l == "user"])
        agent_msgs = dedup_entries([(e, t, l, p, x) for e, t, l, p, x in entries if l == "agent"])
        all_msgs   = sorted(user_msgs + agent_msgs, key=lambda x: x[0])

        print(f"{'=' * 70}")
        print(f"  {day_dt.strftime('%A, %d %B %Y')}  ({hrs:.1f}h)")
        print(f"{'=' * 70}")
        for _, time_str, label, proj, text in all_msgs:
            prefix = "  " if label == "user" else "    → "
            lines = text.splitlines() if text else [""]
            indent = " " * len(prefix)
            print(f"{prefix}[{time_str}] [{proj}] {lines[0]}")
            for continuation in lines[1:]:
                print(f"{indent}{continuation}")
        print()

    # Part 2: monthly summary
    entries = []
    for (proj, theme), hrs in theme_hours.items():
        rounded = round(hrs * 2) / 2
        if rounded >= 0.5:
            entries.append((proj, theme, rounded))
    entries.sort(key=lambda x: (x[0], -x[2]))

    grand = sum(h for _, _, h in entries)

    print(f"{'=' * 70}")
    print(f"  MONTHLY SUMMARY — {month_label}")
    print(f"{'=' * 70}")
    print()
    print("\n".join(f"[{p}] {t}" for p, t, _ in entries))
    print()
    print("\n".join(str(int(h) if h == int(h) else h) for _, _, h in entries))
    print()
    print(f"Total: {grand:.1f}h")
    print()
    print(
        f"Projects: {len(all_events)} | "
        f"Sessions scanned: {len(all_files)} | "
        f"Events in range: {total_lines} | "
        f"Active hours (summed): {sum(proj_hours.values()):.1f} | "
        f"Timesheet total: {grand:.1f}"
    )


if __name__ == "__main__":
    main()
