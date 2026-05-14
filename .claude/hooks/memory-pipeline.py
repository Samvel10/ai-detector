#!/usr/bin/env python3
"""Stop hook: log Q&A to .memory/, auto-commit, auto-push to origin/Samo.

Reads JSON on stdin (Claude Code hook input with transcript_path).
Never raises uncaught — always exits 0 so a hook failure can't loop.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(os.environ.get("CLAUDE_PROJECT_DIR") or "/home/samo/vidioAnalize")
MEM = REPO / ".memory"
QA_LOG = MEM / "QA_LOG.md"
CHANGELOG = MEM / "CHANGELOG.md"
ERR_LOG = MEM / ".hook_errors.log"
BRANCH = "Samo"
REMOTE = "origin"
MAX_TAIL_SCAN = 8000


def log_err(msg: str) -> None:
    try:
        MEM.mkdir(exist_ok=True)
        with ERR_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def run(cmd, cwd=REPO):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout, r.stderr
    except Exception as exc:
        log_err(f"cmd failed {cmd}: {exc}")
        return 1, "", str(exc)


def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
        return "\n".join(parts)
    return ""


def parse_transcript(path: Path):
    """Return (last_user_text, last_assistant_text) or (None, None)."""
    last_user = None
    last_asst = None
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                msg = rec.get("message") or {}
                role = msg.get("role") or rec.get("type")
                content = msg.get("content")
                if content is None:
                    content = rec.get("content")
                text = extract_text(content).strip()
                if not text:
                    continue
                if role == "user":
                    if text.startswith("<") and text.endswith(">"):
                        continue
                    if text.startswith("Caveat:") or "<local-command" in text[:200]:
                        continue
                    last_user = text
                elif role == "assistant":
                    last_asst = text
    except Exception as exc:
        log_err(f"transcript parse failed: {exc}")
    return last_user, last_asst


def append_qa(user_text: str, asst_text: str) -> bool:
    """Append to QA_LOG. Returns True if appended, False if duplicate or error."""
    existing = QA_LOG.read_text(encoding="utf-8") if QA_LOG.exists() else "# Q&A Log\n"
    sig_head = f"### Question\n\n{user_text[:200]}"
    if sig_head in existing[-MAX_TAIL_SCAN:]:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    blocks = []
    if f"## {today}" not in existing:
        blocks.append(f"\n## {today}\n")
    blocks.append(f"\n### Question\n\n{user_text}\n\n### Answer\n\n{asst_text}\n\n---\n")
    try:
        with QA_LOG.open("a", encoding="utf-8") as fh:
            fh.write("".join(blocks))
        return True
    except Exception as exc:
        log_err(f"QA_LOG append failed: {exc}")
        return False


def commit_and_push() -> None:
    rc, branch_out, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_out.strip()
    if branch != BRANCH:
        log_err(f"refusing push: current branch {branch!r} != {BRANCH!r}")
        return

    rc, status, _ = run(["git", "status", "--porcelain"])
    status = status.strip()
    if not status:
        return

    blocked = []
    code_changes = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if path == ".env" or path.endswith("/.env") or path.startswith("storage/"):
            blocked.append(path)
        if not (path.startswith(".memory/") or path.startswith(".claude/")):
            code_changes.append(path)
    if blocked:
        log_err(f"refusing commit: blocked paths in status: {blocked}")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    if code_changes:
        try:
            entry_lines = [f"\n## {today}\n", "- auto-commit from memory pipeline:\n"]
            for p in code_changes[:10]:
                entry_lines.append(f"  - `{p}`\n")
            if len(code_changes) > 10:
                entry_lines.append(f"  - ...and {len(code_changes) - 10} more\n")
            with CHANGELOG.open("a", encoding="utf-8") as fh:
                fh.write("".join(entry_lines))
        except Exception as exc:
            log_err(f"CHANGELOG append failed: {exc}")

    summary = f"chore(memory): auto-log {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    body_lines = [summary]
    if code_changes:
        body_lines.append("")
        body_lines.append("Files changed (non-memory):")
        for p in code_changes[:15]:
            body_lines.append(f"  - {p}")
        if len(code_changes) > 15:
            body_lines.append(f"  ...and {len(code_changes) - 15} more")
    body_lines.append("")
    body_lines.append("Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>")
    commit_msg = "\n".join(body_lines)

    run(["git", "add", "-A"])
    rc, _, err = run(["git", "commit", "-m", commit_msg])
    if rc != 0:
        log_err(f"commit failed: {err.strip()}")
        return
    rc, _, err = run(["git", "push", REMOTE, BRANCH])
    if rc != 0:
        log_err(f"push failed: {err.strip()}")


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception as exc:
        log_err(f"stdin read failed: {exc}")
        return 0
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        log_err(f"stdin not json: {exc}; raw={raw[:200]!r}")
        return 0

    transcript = data.get("transcript_path")
    if not transcript:
        return 0
    tpath = Path(transcript)
    if not tpath.exists():
        log_err(f"transcript missing: {transcript}")
        return 0

    user_text, asst_text = parse_transcript(tpath)
    if not (user_text and asst_text):
        return 0

    appended = append_qa(user_text, asst_text)
    if appended:
        commit_and_push()
    else:
        commit_and_push()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log_err(f"unhandled: {exc}")
        sys.exit(0)
