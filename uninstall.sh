#!/usr/bin/env bash
set -euo pipefail

# claude-email-hook uninstaller

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "\033[0;34m[info]\033[0m $1"; }
ok()    { echo -e "${GREEN}[ok]${NC} $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $1"; }

HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"
CLAUDE_MD="$HOME/CLAUDE.md"

echo ""
echo -e "${CYAN}claude-email-hook uninstaller${NC}"
echo ""

read -rp "This will remove claude-email-hook from your system. Continue? (y/n): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[yY] ]]; then
    echo "Cancelled."
    exit 0
fi

# Remove hook files
for f in notify.py digest.py common.py config.yaml; do
    if [ -f "$HOOKS_DIR/$f" ]; then
        rm "$HOOKS_DIR/$f"
        ok "Removed $HOOKS_DIR/$f"
    fi
done

if [ -d "$HOOKS_DIR/templates" ]; then
    rm -rf "$HOOKS_DIR/templates"
    ok "Removed $HOOKS_DIR/templates/"
fi

# Remove hooks from settings.json
if [ -f "$SETTINGS_FILE" ]; then
    python3 -c "
import json
with open('$SETTINGS_FILE', 'r') as f:
    s = json.load(f)
s.pop('hooks', None)
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
    f.write('\n')
"
    ok "Removed hooks from settings.json"
fi

# Remove cron job
if crontab -l 2>/dev/null | grep -q "claude-email-hook"; then
    (crontab -l 2>/dev/null || true) | grep -v "claude-email-hook" | crontab -
    ok "Removed cron job"
fi

# Remove CLAUDE.md snippet
if [ -f "$CLAUDE_MD" ] && grep -qF "## Project Tracker (claude-email-hook)" "$CLAUDE_MD"; then
    python3 -c "
import re
with open('$CLAUDE_MD', 'r') as f:
    content = f.read()
content = re.sub(r'\n## Project Tracker \(claude-email-hook\).*?(?=\n## |\Z)', '', content, flags=re.DOTALL)
with open('$CLAUDE_MD', 'w') as f:
    f.write(content.strip() + '\n')
"
    ok "Removed tracker instructions from ~/CLAUDE.md"
fi

echo ""
echo -e "${GREEN}Uninstall complete.${NC}"
echo ""
echo "Preserved (manual cleanup if needed):"
echo "  ~/.msmtprc           (may be used by other programs)"
echo "  ~/.claude/hooks/project_tracker.md  (your project data)"
echo ""
