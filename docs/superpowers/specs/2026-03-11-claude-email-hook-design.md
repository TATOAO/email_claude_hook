# claude-email-hook Design Spec

## Overview

An agentic email notification system for Claude Code. Uses Claude's own CLI (`claude -p`) to generate intelligent task summaries, supports tiered notifications (realtime + daily digest), and auto-maintains a cross-project tracker via Claude Code's memory system.

## Architecture

```
claude-email-hook/
├── install.sh              # Interactive installer → generates config.yaml → deploys
├── uninstall.sh            # Clean removal
├── config.example.yaml     # Configuration template
├── src/
│   ├── notify.py           # Realtime notification hook (Stop/Notification events)
│   ├── digest.py           # Daily digest script (cron-triggered)
│   ├── common.py           # Shared: config loading, transcript parsing, email sending, tracker parsing
│   └── templates/
│       ├── notify.html     # Realtime notification HTML (Jinja2)
│       └── digest.html     # Daily digest HTML (Jinja2)
├── tracker/
│   ├── project_tracker.md  # Example tracker file
│   └── CLAUDE.md.snippet   # Instructions for Claude to auto-maintain tracker
├── providers/
│   ├── 126.yaml
│   ├── qq.yaml
│   ├── gmail.yaml
│   ├── outlook.yaml
│   └── custom.yaml
```

## Configuration

```yaml
smtp:
  provider: "126"
  user: "sender@126.com"
  password: "authorization_code"

notifications:
  realtime:
    to: "dev@example.com"
    events: ["Stop", "Notification"]
  digest:
    to: "report@example.com"
    cron: "0 20 * * *"

summary:
  model: "claude-haiku-4-5-20251001"

tracker:
  enabled: true
```

## Two Notification Flows

### Realtime (Email A)
- Triggered by Claude Code hooks (Stop, Notification events)
- Reads transcript → calls `claude -p` for single-task summary
- Includes project tracker overview in email
- Sends immediately via msmtp

### Daily Digest (Email B)
- Triggered by cron at configured time
- Scans all transcript files modified today across all projects
- Calls `claude -p` to generate consolidated daily report
- Includes: per-project work summary, status changes, outstanding TODOs

## Anti-Recursion
- Environment variable `CLAUDE_HOOK_NOTIFY_RUNNING=1` prevents `claude -p` subprocess from re-triggering the hook

## Project Tracker
- Markdown file auto-maintained by Claude Code sessions via CLAUDE.md instructions
- Parsed by hook scripts for email context
- Format: `### ProjectName` with structured `- **field**: value` entries

## SMTP Providers
- Pre-configured provider YAML files with host/port/tls settings
- install.sh merges provider settings + user credentials into ~/.msmtprc

## Install Flow
1. Select email provider
2. Enter sender email + auth code
3. Enter realtime recipient (Email A)
4. Optional: enable digest + recipient (Email B) + cron time
5. Send test email to verify
6. Deploy: config.yaml, ~/.msmtprc, hooks to ~/.claude/hooks/, register in settings.json, cron job, CLAUDE.md injection

## Dependencies
- Python 3.8+ with Jinja2
- msmtp
- Claude Code CLI (`claude -p`)
