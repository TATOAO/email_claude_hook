#!/usr/bin/env python3
"""Claude Code hook: agentic realtime email notification.

Triggered by Stop/Notification events. Reads transcript, calls claude -p
for intelligent summary, renders HTML template, sends via msmtp.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Template

from common import (
    load_config,
    parse_tracker,
    parse_todo_line,
    match_project,
    load_project_memory,
    extract_transcript,
    generate_summary,
    send_email,
    CATEGORY_LABELS,
)


def main():
    # Prevent recursion from claude -p subprocess
    if os.environ.get("CLAUDE_HOOK_NOTIFY_RUNNING"):
        return

    # Read hook data from stdin
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    config = load_config()
    realtime_cfg = config.get("notifications", {}).get("realtime", {})
    to_email = realtime_cfg.get("to", "")
    if not to_email:
        return

    # Check if this event type is configured
    allowed_events = realtime_cfg.get("events", ["Stop", "Notification"])
    hook_event = data.get("hook_event_name", "Unknown")
    if hook_event not in allowed_events and "Unknown" not in allowed_events:
        return

    cwd = data.get("cwd", os.getcwd())
    session_id = data.get("session_id", "unknown")[:8]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    transcript_path = data.get("transcript_path", "")
    model = config.get("summary", {}).get("model", "claude-haiku-4-5-20251001")

    # Load project context
    tracker_projects = []
    template_projects = []
    if config.get("tracker", {}).get("enabled", True):
        tracker_projects = parse_tracker(config)
    project_info, template_projects = match_project(cwd, tracker_projects)
    project_memory = load_project_memory(cwd)

    # Generate summary with Claude
    transcript_text = extract_transcript(transcript_path)
    if transcript_text:
        title_suffix, summary, status = generate_summary(
            transcript_text, project_info, project_memory, model
        )
    else:
        message = data.get("message", "")
        title_suffix = "等待输入" if hook_event == "Notification" else "任务完成"
        summary = message or "无法读取会话记录"
        status = "等待用户输入" if hook_event == "Notification" else "已完成"

    # Map status to CSS class
    status_map = {
        "已完成": "status-done",
        "进行中": "status-progress",
        "等待用户输入": "status-waiting",
    }
    status_class = status_map.get(status, "status-progress")

    event_labels = {"Stop": "任务完成", "Notification": "需要输入"}
    event_label = event_labels.get(hook_event, hook_event)

    cat_label = project_info["category_label"]
    project_label = project_info["label"]

    # Email subject
    if hook_event == "Notification":
        subject = f"[{cat_label}] {project_label} - 需要你的注意"
    else:
        subject = f"[{cat_label}] {project_label} - {title_suffix}"

    # Build kanban + gantt data
    today = datetime.now().date()
    status_class_map = {"待办": "todo", "进行中": "in_progress", "已完成": "done"}
    all_todos = []
    all_dates = []

    for tp in template_projects:
        for t in tp.get("todos", []):
            start_date_str = t.get("start_date", "") if isinstance(t, dict) else ""
            task_text = t.get("task", t) if isinstance(t, dict) else t
            task_status = t.get("status", "待办") if isinstance(t, dict) else "待办"

            start_date = None
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    all_dates.append(start_date)
                except ValueError:
                    pass

            days_elapsed = (today - start_date).days + 1 if start_date else 1
            days_elapsed = max(1, days_elapsed)

            all_todos.append({
                "task": task_text,
                "start_date": start_date_str,
                "status": task_status,
                "status_class": status_class_map.get(task_status, "todo"),
                "project_name": tp["name"],
                "project_category": tp["category"],
                "days_elapsed": days_elapsed,
                "_start_date": start_date,
            })

    # Gantt timeline
    gantt_start_date = ""
    gantt_total_days = 1
    gantt_date_labels = []

    if all_dates:
        min_date = min(all_dates)
        max_date = today
        gantt_total_days = max((max_date - min_date).days + 2, 7)
        gantt_start_date = min_date.strftime("%Y-%m-%d")

        for t in all_todos:
            if t["_start_date"]:
                t["bar_left_pct"] = round((t["_start_date"] - min_date).days / gantt_total_days * 100, 1)
                t["bar_width_pct"] = round(t["days_elapsed"] / gantt_total_days * 100, 1)
            else:
                t["bar_left_pct"] = 0
                t["bar_width_pct"] = round(1 / gantt_total_days * 100, 1)

        step = max(gantt_total_days // 4, 1)
        for i in range(0, gantt_total_days, step):
            d = min_date + timedelta(days=i)
            gantt_date_labels.append(d.strftime("%m-%d"))
        gantt_date_labels.append(max_date.strftime("%m-%d"))

    for t in all_todos:
        t.pop("_start_date", None)

    # Render HTML
    template_path = Path(__file__).parent / "templates" / "notify.html"
    try:
        template_str = template_path.read_text("utf-8")
    except Exception:
        template_str = "<html><body><pre>{{ summary }}</pre></body></html>"

    template = Template(template_str)
    html_body = template.render(
        category=project_info["category"],
        category_label=cat_label,
        project_label=project_label,
        event_label=event_label,
        time=now,
        session_id=session_id,
        cwd=cwd,
        summary=summary,
        status=status,
        status_class=status_class,
        tracker_projects=template_projects,
        all_todos=all_todos,
        gantt_start_date=gantt_start_date,
        gantt_total_days=gantt_total_days,
        gantt_date_labels=gantt_date_labels,
    )

    try:
        send_email(to_email, subject, html_body)
    except Exception as e:
        print(f"邮件发送失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
