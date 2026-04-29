# /timesheet — Claude Code Timesheet Skill

Generate a monthly timesheet or per-day work log from Claude Code session history.

## Prerequisites

The timesheet scripts must be installed. Check with:

```bash
ls ~/.claude/tools/timesheet.py
```

If missing, tell the user:
> The timesheet tools are not installed. Clone https://github.com/<owner>/claude-timesheet and run `./install.sh`.

## Usage

```
/timesheet                    # current month, all projects
/timesheet "Mar 2026"         # March 2026
/timesheet 2026-03            # same, ISO form
/timesheet "Mar 2026" myapp   # restrict to one project (substring match)
/timesheet daily              # per-day log for current month
/timesheet daily "Feb 2026"   # per-day log for a specific month
```

## Monthly timesheet

Run:

```bash
python3 ~/.claude/tools/timesheet.py --month "MONTH" [--project NAME]
```

Present the output block as-is (descriptions + hours + total). Do not reformat or summarise — the two-block plain-text format is intentional for copy-paste into billing systems.

## Per-day log

Run:

```bash
python3 ~/.claude/tools/daily.py --month "MONTH" [--project NAME]
```

Progress lines go to stderr; the day-by-day log goes to stdout. Present each day's entries with its timestamp and project tag. If the user wants to save the output:

```bash
python3 ~/.claude/tools/daily.py --month "MONTH" --output /tmp/daily.txt
```

## Argument parsing

- Empty month → current month (auto-detected from system timezone)
- Accept: `YYYY-MM`, `Mon YYYY`, `Month YYYY`
- Pass the month string verbatim to `--month`; the script handles parsing and timezone

## Error handling

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No such file: ~/.claude/tools/timesheet.py` | Not installed | Run `./install.sh` from the repo |
| `Cannot parse month` | Bad month format | Use `2026-02`, `Feb 2026`, or `February 2026` |
| `No project dirs found` | `--project` filter too strict | Broaden or remove the project filter |
| Output shows 0 events | Month outside session history | Verify `~/.claude/projects/` has JSONL files for that period |
