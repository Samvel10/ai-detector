#!/usr/bin/env python3
"""UserPromptSubmit hook: if the prompt contains the keyword 'memory', inject
a system reminder telling Claude to re-read the project memory files first.
"""
import json
import sys

KEYWORD = "memory"
REMINDER = (
    "The user mentioned the trigger keyword 'memory'. Before answering anything else, "
    "read these three files in order and treat their contents as authoritative project context: "
    "/home/samo/vidioAnalize/.memory/PROJECT_MEMORY.md, "
    "/home/samo/vidioAnalize/.memory/QA_LOG.md, "
    "/home/samo/vidioAnalize/.memory/CHANGELOG.md. "
    "Acknowledge briefly that you have re-loaded memory, then address the user's request."
)


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    prompt = (data.get("prompt") or "").lower()
    if KEYWORD in prompt:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": REMINDER,
            }
        }
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
