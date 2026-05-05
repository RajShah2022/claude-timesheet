#!/usr/bin/env bash
set -euo pipefail

TOOLS_DIR="$HOME/.claude/tools"
SKILLS_DIR="$HOME/.claude/skills/timesheet"

echo "Uninstalling claude-timesheet..."

rm -f "$TOOLS_DIR/timesheet.py" "$TOOLS_DIR/daily.py"
rm -rf "$SKILLS_DIR"

echo "Done."
