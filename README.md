# claude-timesheet

A Claude Code skill and tools for generating timesheets from your Claude Code session history.

Reads `~/.claude/projects/**/*.jsonl` — the session files Claude Code writes locally — and produces:

- **Monthly timesheet** — hours per project per theme, formatted for copy-paste into billing systems
- **Per-day log** — chronological view of what you asked Claude to work on, grouped by day

No external services, no API calls. Everything runs locally against your own session files.

## Requirements

- Python 3.8+
- Claude Code (session files in `~/.claude/projects/`)

## Install

```bash
git clone https://github.com/<owner>/claude-timesheet.git
cd claude-timesheet
./install.sh
```

This copies two scripts to `~/.claude/tools/` and the skill file to `~/.claude/skills/timesheet/`.

## Usage

### In Claude Code (via skill)

```
/timesheet                    current month
/timesheet "Mar 2026"         specific month
/timesheet 2026-03            ISO form
/timesheet "Mar 2026" myapp   restrict to one project (substring match)
/timesheet daily              per-day log, current month
/timesheet daily "Feb 2026"   per-day log, specific month
```

### Direct CLI

```bash
# Monthly timesheet
python3 ~/.claude/tools/timesheet.py
python3 ~/.claude/tools/timesheet.py --month "Feb 2026"
python3 ~/.claude/tools/timesheet.py --month 2026-02 --project backend

# Per-day log
python3 ~/.claude/tools/daily.py
python3 ~/.claude/tools/daily.py --month "Feb 2026"
python3 ~/.claude/tools/daily.py --month "Feb 2026" --output ~/feb-log.txt
```

## How it works

1. **Two-stage file filter** — skips files by mtime first, then by reading only the first and last line's timestamp. Rejects ~95% of historical files before parsing any content.
2. **Stream parse** — reads surviving JSONL files line by line; never loads a whole file into memory.
3. **Session detection** — events with a >30 min gap between them are treated as separate sessions. Active time = sum of session durations.
4. **Theme classification** — regex patterns match snippet text to work themes (API, frontend, DevOps, etc.).
5. **Timezone** — auto-detected from the system. Day boundaries for the per-day log use local time.

## Uninstall

```bash
./uninstall.sh
```

## Output format (monthly)

Two plain-text blocks separated by a blank line, one entry per line. Designed for direct copy-paste into billing or invoicing tools:

```
[backend] Authentication and authorization
[backend] Backend API, services, models
[frontend] Frontend UI, components, views

8
12
6

Total: 26.0h
```
