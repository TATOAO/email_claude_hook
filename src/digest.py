#!/usr/bin/env python3
"""Claude Code daily digest: aggregate all sessions from today into a summary email.

Triggered by cron. Scans transcript files modified today, groups by project,
calls claude -p for consolidated summary, renders HTML, sends via msmtp.
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from common import (
    load_config,
    parse_tracker,
    match_project,
    extract_transcript,
    send_email,
    find_today_transcripts,
)


def generate_digest_summary(project_summaries_text, model="claude-haiku-4-5-20251001"):
    """Call claude -p to generate a consolidated daily digest."""
    prompt = (
        f"你是一个每日工作报告助手。请根据以下今天的 Claude Code 工作记录，"
        f"生成一份简洁的每日工作摘要。\n"
        f"\n"
        f"{project_summaries_text}\n"
        f"\n"
        f"请为每个项目输出以下格式（不要加 markdown 代码块）：\n"
        f"\n"
        f"PROJECT: 项目名\n"
        f"TITLE: 一句话概括今天在这个项目做了什么\n"
        f"SUMMARY:\n"
        f"- 要点1\n"
        f"- 要点2\n"
        f"STATUS: 状态\n"
        f"\n"
        f"如果有多个项目，每个项目之间用空行分隔。\n"
    )

    try:
        env = os.environ.copy()
        env["CLAUDE_HOOK_NOTIFY_RUNNING"] = "1"
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True, text=True, timeout=120, env=env,
            cwd="/tmp",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except Exception:
        return None


def parse_digest_output(output):
    """Parse the structured output from claude -p into project summaries."""
    projects = []
    current = None

    for line in output.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("PROJECT:"):
            if current:
                current["summary"] = "\n".join(current["_lines"]).strip()
                del current["_lines"]
                projects.append(current)
            current = {
                "name": line_stripped.replace("PROJECT:", "").strip(),
                "title": "",
                "summary": "",
                "status": "",
                "_lines": [],
            }
        elif current and line_stripped.startswith("TITLE:"):
            current["title"] = line_stripped.replace("TITLE:", "").strip()
        elif current and line_stripped.startswith("STATUS:"):
            current["status"] = line_stripped.replace("STATUS:", "").strip()
        elif current and line_stripped.startswith("SUMMARY:"):
            continue
        elif current:
            current["_lines"].append(line)

    if current:
        current["summary"] = "\n".join(current["_lines"]).strip()
        del current["_lines"]
        projects.append(current)

    return projects


def main():
    if os.environ.get("CLAUDE_HOOK_NOTIFY_RUNNING"):
        return

    config = load_config()
    digest_cfg = config.get("notifications", {}).get("digest", {})

    if not digest_cfg.get("enabled", False):
        return

    to_email = digest_cfg.get("to", "")
    if not to_email:
        return

    model = config.get("summary", {}).get("model", "claude-haiku-4-5-20251001")
    today = datetime.now().strftime("%Y-%m-%d")

    # Find today's transcripts
    transcripts = find_today_transcripts()
    if not transcripts:
        return  # No activity today, skip digest

    # Group transcripts by project and extract content
    project_texts = {}
    for t in transcripts:
        cwd = t["cwd"]
        project_name = os.path.basename(cwd)
        text = extract_transcript(t["path"], max_lines=30)
        if text:
            if project_name not in project_texts:
                project_texts[project_name] = []
            project_texts[project_name].append(text)

    if not project_texts:
        return

    # Build combined text for claude -p
    combined_parts = []
    for project_name, texts in project_texts.items():
        combined_parts.append(f"=== 项目: {project_name} ===")
        for i, text in enumerate(texts):
            combined_parts.append(f"--- 会话 {i+1} ---")
            # Limit each session text to avoid too-large prompt
            combined_parts.append(text[:2000])
        combined_parts.append("")

    combined_text = "\n".join(combined_parts)
    # Limit total size
    if len(combined_text) > 10000:
        combined_text = combined_text[:10000] + "\n...(已截断)"

    # Generate digest with Claude
    digest_output = generate_digest_summary(combined_text, model)

    if digest_output:
        project_summaries = parse_digest_output(digest_output)
    else:
        # Fallback: basic listing
        project_summaries = []
        for project_name in project_texts:
            project_summaries.append({
                "name": project_name,
                "title": "今日有活动",
                "summary": f"共 {len(project_texts[project_name])} 个会话",
                "status": "进行中",
            })

    # Load tracker for project overview
    tracker_projects = []
    template_projects = []
    if config.get("tracker", {}).get("enabled", True):
        from common import CATEGORY_LABELS
        tracker_projects = parse_tracker(config)
        for p in tracker_projects:
            cat = p["category"]
            template_projects.append({
                "name": p["name"],
                "category": cat,
                "category_short": CATEGORY_LABELS.get(cat, "其他"),
                "status": p["status"],
                "progress": (p["progress"][:40]) if p["progress"] else "",
                "todos": ", ".join(p["todos"][:3]) if p["todos"] else "",
            })

    # Enrich project_summaries with category info
    category_map = {p["dir_name"]: p for p in tracker_projects}
    enriched_summaries = []
    for ps in project_summaries:
        cat_info = category_map.get(ps["name"], {})
        cat = cat_info.get("category", "unknown")
        enriched_summaries.append({
            **ps,
            "category": cat,
            "category_short": CATEGORY_LABELS.get(cat, "其他") if cat_info else "探索",
            "category_label": CATEGORY_LABELS.get(cat, "其他") if cat_info else "临时探索",
            "sessions": [{
                "title": ps.get("title", ""),
                "summary": ps.get("summary", ""),
                "status": ps.get("status", ""),
                "time": "",
            }],
        })

    # Render HTML
    template_path = Path(__file__).parent / "templates" / "digest.html"
    try:
        template_str = template_path.read_text("utf-8")
    except Exception:
        template_str = "<html><body><pre>{{ project_summaries }}</pre></body></html>"

    template = Template(template_str)
    html_body = template.render(
        date=today,
        total_sessions=len(transcripts),
        active_project_count=len(project_texts),
        project_summaries=enriched_summaries,
        tracker_projects=template_projects,
    )

    subject = f"[Claude Code 日报] {today} - {len(project_texts)} 个项目活跃"

    try:
        send_email(to_email, subject, html_body)
    except Exception as e:
        print(f"日报发送失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
