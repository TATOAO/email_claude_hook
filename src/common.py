#!/usr/bin/env python3
"""Shared utilities for claude-email-hook."""

import json
import os
import re
import subprocess
import yaml
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def _find_config():
    """Find config.yaml: same dir (deployed) → parent dir (dev) → None."""
    for candidate in [SCRIPT_DIR / "config.yaml", SCRIPT_DIR.parent / "config.yaml"]:
        if candidate.exists():
            return candidate
    return None


def load_config():
    """Load config.yaml, return dict."""
    config_path = _find_config()
    if not config_path:
        return {}
    try:
        return yaml.safe_load(config_path.read_text("utf-8"))
    except Exception:
        return {}

def load_provider(provider_name):
    """Load SMTP provider settings from providers/*.yaml."""
    provider_path = SCRIPT_DIR.parent / "providers" / f"{provider_name}.yaml"
    try:
        return yaml.safe_load(provider_path.read_text("utf-8"))
    except Exception:
        return {}

def parse_todo_line(line):
    """Parse a single todo line. Supports:
    New format: - [ ] description | 2026-03-08 | 进行中
    New format: - [x] description | 2026-03-08 | 已完成
    Old format: - description (no date/status, backward compatible)
    Returns dict {task, start_date, status} or None.
    """
    text = line.strip()
    if text.startswith("- "):
        text = text[2:]

    checkbox_match = re.match(r"\[([x ])\]\s*(.+)", text)
    if checkbox_match:
        is_done = checkbox_match.group(1) == "x"
        rest = checkbox_match.group(2)
        parts = [p.strip() for p in rest.split("|")]
        task = parts[0]
        start_date = parts[1] if len(parts) > 1 else ""
        status = parts[2] if len(parts) > 2 else ("已完成" if is_done else "待办")
        return {"task": task, "start_date": start_date, "status": status}

    if text and not text.startswith("**"):
        return {"task": text, "start_date": "", "status": "待办"}

    return None


def parse_tracker(config):
    """Parse project_tracker.md, return list of project dicts."""
    tracker_path = Path.home() / ".claude" / "hooks" / "project_tracker.md"
    if not tracker_path.exists():
        return []

    content = tracker_path.read_text("utf-8")
    projects = []
    current = None
    in_todos = False

    for line in content.splitlines():
        if line.startswith("### "):
            if current:
                projects.append(current)
            current = {
                "name": line[4:].strip(),
                "dir_name": "",
                "category": "unknown",
                "status": "",
                "progress": "",
                "todos": [],
            }
            in_todos = False
        elif current and line.startswith("- **目录**:"):
            current["dir_name"] = line.split(":", 1)[1].strip()
            in_todos = False
        elif current and line.startswith("- **分类**:"):
            current["category"] = line.split(":", 1)[1].strip()
            in_todos = False
        elif current and line.startswith("- **状态**:"):
            current["status"] = line.split(":", 1)[1].strip()
            in_todos = False
        elif current and line.startswith("- **进度**:"):
            current["progress"] = line.split(":", 1)[1].strip()
            in_todos = False
        elif current and line.startswith("- **待办**:"):
            in_todos = True
        elif current and in_todos and line.strip().startswith("- "):
            todo = parse_todo_line(line.strip())
            if todo:
                current["todos"].append(todo)
        elif current and in_todos and not line.strip():
            in_todos = False

    if current:
        projects.append(current)
    return projects

CATEGORY_LABELS = {
    "core": "核心", "plugin": "插件", "infra": "基础设施",
    "side": "实验", "unknown": "探索",
}


def match_project(cwd, tracker_projects):
    """Match cwd to a tracker project. Returns (project_info, template_projects)."""
    cwd_normalized = cwd.replace("-", "_").lower()
    dir_name = os.path.basename(cwd)

    matched = None
    for p in tracker_projects:
        d = p["dir_name"]
        if not d:
            continue
        d_normalized = d.replace("-", "_").lower()
        if f"/{d_normalized}/" in cwd_normalized + "/":
            matched = p
            break

    if matched:
        cat = matched["category"]
        project_info = {
            "label": matched["name"],
            "category": cat,
            "category_label": CATEGORY_LABELS.get(cat, "其他"),
            "description": matched["progress"],
        }
    else:
        project_info = {
            "label": dir_name,
            "category": "unknown",
            "category_label": "临时探索",
            "description": "",
        }

    template_projects = []
    for p in tracker_projects:
        cat = p["category"]
        todo_display = []
        for t in p["todos"][:10]:
            if isinstance(t, dict):
                todo_display.append(t)
            else:
                todo_display.append({"task": t, "start_date": "", "status": "待办"})
        template_projects.append({
            "name": p["name"],
            "category": cat,
            "category_short": CATEGORY_LABELS.get(cat, "其他"),
            "status": p["status"],
            "progress": (p["progress"][:40]) if p["progress"] else "",
            "todos": todo_display,
            "is_current": p.get("dir_name", "") != "" and (
                f"/{p['dir_name'].replace('-', '_').lower()}/" in cwd_normalized + "/"
            ),
        })

    return project_info, template_projects

def load_project_memory(cwd):
    """Load project-level MEMORY.md from Claude Code's memory system."""
    sanitized = cwd.replace("/", "-").lstrip("-")
    memory_path = Path.home() / ".claude" / "projects" / sanitized / "memory" / "MEMORY.md"
    try:
        if memory_path.exists():
            return memory_path.read_text("utf-8")[:1000]
    except Exception:
        pass
    return ""

def extract_transcript(path, max_lines=50):
    """Extract recent conversation content from transcript JSONL."""
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    recent = lines[-max_lines:]
    parts = []
    for line in recent:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        msg = entry.get("message", {})
        role = msg.get("role", entry.get("type", ""))
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        parts.append(f"[{role}]: {text[:300]}")
                elif block.get("type") == "tool_use":
                    tool = block.get("name", "")
                    desc = block.get("input", {}).get("description", "")
                    file_path = block.get("input", {}).get("file_path", "")
                    info = desc or file_path or ""
                    parts.append(f"[{role} tool]: {tool} {info}")
        elif isinstance(content, str) and content.strip():
            parts.append(f"[{role}]: {content[:300]}")

    result = "\n".join(parts)
    if len(result) > 6000:
        result = result[-6000:]
    return result

def run_claude_p(prompt, model="claude-haiku-4-5-20251001", timeout=60):
    """Call claude -p and extract text from stream-json output.
    The plain result field is empty with extended thinking models,
    so we parse the streaming messages to get actual text content."""
    env = os.environ.copy()
    env["CLAUDE_HOOK_NOTIFY_RUNNING"] = "1"

    result = subprocess.run(
        ["claude", "-p", prompt, "--model", model,
         "--output-format", "stream-json", "--verbose"],
        capture_output=True, text=True, timeout=timeout, env=env,
        cwd="/tmp", stdin=subprocess.DEVNULL,
    )

    text_parts = []
    for line in result.stdout.strip().splitlines():
        try:
            data = json.loads(line)
            if data.get("type") == "assistant":
                for block in data.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
        except Exception:
            pass

    return "\n".join(text_parts)


def generate_summary(transcript_text, project_info, project_memory, model="claude-haiku-4-5-20251001"):
    """Call claude -p to generate task summary. Returns (title, summary, status)."""
    context_parts = []
    if project_info.get("description"):
        context_parts.append(f"项目简介: {project_info['description']}")
    if project_memory:
        context_parts.append(f"项目记忆:\n{project_memory}")
    context = "\n".join(context_parts)

    prompt = (
        f"你是一个任务通知助手。请根据以下信息生成邮件通知内容。\n"
        f"\n"
        f"项目: {project_info.get('label', 'Unknown')}（{project_info.get('category_label', '')}）\n"
        f"{context}\n"
        f"\n"
        f"会话记录:\n"
        f"{transcript_text}\n"
        f"\n"
        f"请严格按以下格式输出，不要加 markdown 代码块和其他任何内容：\n"
        f"\n"
        f"TITLE: 10字以内的任务标题\n"
        f"STATUS: 已完成 或 进行中 或 等待用户输入\n"
        f"SUMMARY:\n"
        f"- 要点1\n"
        f"- 要点2\n"
        f"- 要点3\n"
    )

    try:
        output = run_claude_p(prompt, model)
        if not output.strip():
            return "任务完成", "摘要生成失败: 模型返回为空", "未知"

        output = re.sub(r"^```\w*\n?", "", output)
        output = re.sub(r"\n?```$", "", output)
        output = output.strip()

        title = "任务完成"
        status = "已完成"
        summary_lines = []
        for line in output.splitlines():
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("STATUS:"):
                status = line.replace("STATUS:", "").strip()
            elif line.startswith("SUMMARY:"):
                continue
            else:
                summary_lines.append(line)
        summary = "\n".join(summary_lines).strip()
        return title, summary or output, status

    except subprocess.TimeoutExpired:
        return "任务完成", "摘要生成超时", "未知"
    except Exception as e:
        return "任务完成", f"摘要生成失败: {e}", "未知"

def send_email(to, subject, html_body):
    """Send HTML email via msmtp."""
    email_content = (
        f"Subject: {subject}\n"
        f"MIME-Version: 1.0\n"
        f"Content-Type: text/html; charset=utf-8\n"
        f"\n"
        f"{html_body}"
    )
    subprocess.run(
        ["msmtp", to],
        input=email_content.encode("utf-8"),
        timeout=15,
    )

def find_today_transcripts():
    """Find all transcript JSONL files modified today."""
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        return []

    today = datetime.now().date()
    transcripts = []

    for jsonl in claude_projects.rglob("*.jsonl"):
        # Skip non-transcript files
        if jsonl.parent.name == "memory":
            continue
        mtime = datetime.fromtimestamp(jsonl.stat().st_mtime).date()
        if mtime == today:
            # Extract project path from the directory name
            project_dir = jsonl.parent.name  # e.g. -home-lwt-Work-market-realtime
            cwd = "/" + project_dir.replace("-", "/")
            transcripts.append({
                "path": str(jsonl),
                "project_dir": project_dir,
                "cwd": cwd,
            })

    return transcripts
