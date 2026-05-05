#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$HOME/.claude/tools"
SKILLS_DIR="$HOME/.claude/skills/timesheet"

echo "Installing claude-timesheet..."

# Create directories
mkdir -p "$TOOLS_DIR"
mkdir -p "$SKILLS_DIR"

# Copy scripts
cp "$REPO_DIR/tools/timesheet.py" "$TOOLS_DIR/timesheet.py"
cp "$REPO_DIR/tools/daily.py"     "$TOOLS_DIR/daily.py"
chmod +x "$TOOLS_DIR/timesheet.py" "$TOOLS_DIR/daily.py"

# Copy skill
cp "$REPO_DIR/skills/timesheet/SKILL.md" "$SKILLS_DIR/SKILL.md"

echo ""
echo "Installed:"
echo "  $TOOLS_DIR/timesheet.py"
echo "  $TOOLS_DIR/daily.py"
echo "  $SKILLS_DIR/SKILL.md   ← /timesheet skill"
echo ""
echo "Usage in Claude Code:"
echo "  /timesheet                  current month"
echo "  /timesheet \"Feb 2026\"       specific month"
echo "  /timesheet daily            per-day log"
echo ""
echo "Or run directly:"
echo "  python3 ~/.claude/tools/timesheet.py --month \"Feb 2026\""
echo "  python3 ~/.claude/tools/daily.py --month \"Feb 2026\""
