---
name: timesheet
description: |
  Generate a detailed monthly timesheet from Claude Code session history.
  Produces a per-day breakdown of what was worked on (real user messages +
  agent task descriptions with daily hours) and a monthly summary grouped
  by project and theme. Use when asked for "timesheet", "what did I work on
  in <month>", "fill timesheet", or "monthly work summary".
allowed-tools:
  - Bash
---

# /timesheet — Detailed Timesheet from Claude Code Sessions

## Step 1: Check installation

```bash
ls "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/tools/timesheet.py" 2>/dev/null && echo "ok" || echo "missing"
```

If missing, install via one of:
- Claude Code plugin: `/plugin marketplace add RajShah2022/claude-timesheet` then `/plugin install timesheet@claude-timesheet`
- Manual: `git clone https://github.com/RajShah2022/claude-timesheet && cd claude-timesheet && ./install.sh`

## Step 2: Parse arguments

```
/timesheet                     → current month, all projects
/timesheet "Mar 2026"          → specific month
/timesheet 2026-03             → specific month, ISO form
/timesheet "12 Mar 2026"       → exact day
/timesheet 2026-03-12          → exact day, ISO form
/timesheet "Mar 2026" myapp    → month + project filter
/timesheet "12 Mar 2026" myapp → exact day + project filter
```

- First argument after `/timesheet`: month or exact date string — pass to `--month`
- Second argument: project filter — pass to `--project`
- No arguments: omit both flags (script defaults to current month)

## Step 3: Run

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/tools/timesheet.py" --month "MONTH_OR_DATE" [--project "NAME"]
```

Capture and print the **full stdout output verbatim**. Do not truncate, summarise, or reformat it.

## Step 4: Output format

The script produces two sections:

**Per-day section** — for each active day, shows hours and what was worked on:
```
======================================================================
  Monday, 02 March 2026  (2.3h)
======================================================================
  [tml] read @linear.csv and make a plan to fix each issue
  [tml] PROJ-305. Check the vehicle card in inwarding screens
    → [tml] Explore the frontend TML admin modules to find page/screen files
    → [tml] I'll search for the sidebar menu implementation
```

- Lines **without** `→` prefix = real user-typed messages (from session JSONL files)
- Lines **with** `→` prefix = agent task descriptions or first assistant response per session

**Monthly summary section** — hours by project and theme, formatted for billing copy-paste:
```
======================================================================
  MONTHLY SUMMARY — 2026-03
======================================================================

[tml] Frontend UI, components, views
[tml] Backend API, services, models
[tml] Bug fixes and QA

18
8
4

Total: 30.0h
```

## Step 5: Explain data sources if asked

- User messages come directly from session JSONL files in `~/.claude/projects/`
- Each turn where `message.role == "user"` with plain-text content is a message you typed
- Tool-result turns are skipped (they're Claude's internal tool output, not your words)

## Error handling

| Symptom | Fix |
|---------|-----|
| `No such file: .../tools/timesheet.py` | Plugin: `/plugin install timesheet@claude-timesheet` · Manual: `./install.sh` |
| `Cannot parse ...` | Use `12 Feb 2026` / `2026-02-12` for a day, or `Feb 2026` / `2026-02` for a month |
| All lines start with `→` | Normal for months before history.jsonl coverage |
| 0 events for a day | No Claude Code sessions that day |
