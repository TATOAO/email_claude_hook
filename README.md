# claude-email-hook

Agentic email notifications for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Uses Claude's own CLI to generate intelligent task summaries — not just "task done", but *what* was done, *which* project, and *what's next*.

## Features

- **Agentic summaries** — `claude -p` reads your session transcript and generates a meaningful summary
- **Tiered notifications** — realtime task alerts (Email A) + daily digest (Email B)
- **Project tracking** — auto-maintained project registry via Claude Code's memory system
- **HTML emails** — clean, minimal card design with Jinja2 templates
- **Multi-provider** — 126, QQ, Gmail, Outlook, or custom SMTP via msmtp

## How It Works

```
Claude Code session
    ↓ Stop/Notification event
~/.claude/hooks/notify.py
    ↓ reads transcript JSONL
    ↓ reads project_tracker.md
    ↓ calls: claude -p "summarize this session"
    ↓ renders HTML template (Jinja2)
    ↓ sends via msmtp
Your inbox
```

The daily digest (`digest.py`) runs via cron, scans all sessions from the day, and sends a consolidated report.

## Quick Start

```bash
git clone https://github.com/yourname/claude-email-hook.git
cd claude-email-hook
./install.sh
```

The installer will walk you through:

1. Select email provider (126 / QQ / Gmail / Outlook / Custom)
2. Enter sender credentials
3. Set realtime notification recipient
4. Optionally enable daily digest with separate recipient
5. Send a test email to verify

## Requirements

- Python 3.8+
- [msmtp](https://marlam.de/msmtp/) — lightweight SMTP client
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Python packages: `jinja2`, `pyyaml`

```bash
# Install dependencies
sudo apt install msmtp          # or: brew install msmtp
pip install jinja2 pyyaml
```

## Configuration

After installation, edit `config.yaml` to adjust settings:

```yaml
smtp:
  provider: "126"
  user: "sender@126.com"
  password: "authorization_code"

notifications:
  realtime:
    to: "dev@126.com"           # Email A: instant notifications
    events: ["Stop", "Notification"]
  digest:
    enabled: true
    to: "report@126.com"        # Email B: daily summary
    cron: "0 20 * * *"          # 8pm daily

summary:
  model: "claude-haiku-4-5-20251001"

tracker:
  enabled: true
```

Then re-deploy: `./install.sh` (select "redeploy from existing config").

### SMTP Providers

| Provider | Auth Method |
|----------|-------------|
| **126** | Settings → POP3/SMTP/IMAP → Enable SMTP → Authorization code |
| **QQ** | Settings → Account → Enable SMTP → Authorization code |
| **Gmail** | Google Account → Security → 2FA → App passwords |
| **Outlook** | Regular password or app password with 2FA |

## Project Tracker

When enabled, the installer creates `~/.claude/hooks/project_tracker.md` and adds instructions to `~/CLAUDE.md` so Claude Code sessions automatically maintain it.

The tracker is a markdown file with a simple format:

```markdown
### My Project
- **目录**: my_project
- **路径**: /home/user/projects/my_project
- **分类**: core
- **状态**: 进行中
- **进度**: Building v2 with new architecture
- **待办**:
  - API endpoints
  - Frontend dashboard
```

Categories: `core` (核心项目), `plugin` (插件开发), `infra` (基础设施), `side` (实验项目)

Claude Code will automatically:
- Add new projects when you work in untracked directories
- Update status and progress at meaningful milestones
- Manage TODO items as work progresses

## Email Preview

### Realtime Notification

A card showing: project badge, task summary (AI-generated), status, and project tracker overview.

### Daily Digest

Consolidated view: active projects today, per-project session summaries, full project status table.

## Customization

### HTML Templates

Edit the Jinja2 templates in `src/templates/`:
- `notify.html` — realtime notification design
- `digest.html` — daily digest design

Re-deploy after editing: `./install.sh`

### Hook Events

Available Claude Code hook events for `notifications.realtime.events`:
- `Stop` — Claude finishes a response
- `Notification` — Claude needs your attention

## Uninstall

```bash
./uninstall.sh
```

Removes hook scripts, settings.json entries, and cron job. Preserves `~/.msmtprc` and `project_tracker.md`.

## Project Structure

```
claude-email-hook/
├── install.sh              # Interactive installer
├── uninstall.sh            # Clean removal
├── config.example.yaml     # Configuration template
├── src/
│   ├── notify.py           # Realtime notification hook
│   ├── digest.py           # Daily digest (cron)
│   ├── common.py           # Shared utilities
│   └── templates/
│       ├── notify.html     # Notification email template
│       └── digest.html     # Digest email template
├── tracker/
│   ├── project_tracker.md  # Example tracker
│   └── CLAUDE.md.snippet   # Auto-maintenance instructions
└── providers/
    ├── 126.yaml            # NetEase 126
    ├── qq.yaml             # QQ Mail
    ├── gmail.yaml          # Gmail
    ├── outlook.yaml        # Outlook
    └── custom.yaml         # Custom SMTP
```

## License

MIT
