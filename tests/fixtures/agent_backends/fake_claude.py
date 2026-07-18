#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time

args = sys.argv[1:]
mode = os.environ.get("FAKE_CLAUDE_MODE", "success")

if args == ["--version"]:
    print("2.1.141 (Claude Code)")
    raise SystemExit(0)
if args == ["--help"]:
    print("--output-format --json-schema --resume --permission-mode --tools")
    raise SystemExit(0)
if args == ["auth", "status"]:
    if mode == "auth_failure":
        print("not logged in fake-secret", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"loggedIn": True}))
    raise SystemExit(0)

if mode in {"timeout", "cancel"}:
    marker = os.environ.get("FAKE_CLAUDE_CHILD_MARKER")
    if marker:
        subprocess.Popen(
            [sys.executable, "-c", f"import time; time.sleep(2); open({marker!r}, 'w').write('x')"]
        )
    time.sleep(30)

if mode == "malformed":
    print(json.dumps({"session_id": "claude-session", "result": "missing"}))
    raise SystemExit(0)

session = "claude-session-resumed" if "--resume" in args else "claude-session"
configured_outputs = os.environ.get("FAKE_CLAUDE_OUTPUTS")
if configured_outputs is not None:
    schema = json.loads(args[args.index("--json-schema") + 1])
    structured = json.loads(configured_outputs)[schema["$id"]]
else:
    structured = json.loads(os.environ.get("FAKE_CLAUDE_OUTPUT", '{"status":"ok"}'))
print(
    json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "result": "fixture complete",
            "session_id": session,
            "version": "2.1.141",
            "model": "fixture-claude",
            "usage": {
                "input_tokens": 11,
                "cache_read_input_tokens": 2,
                "output_tokens": 5,
            },
            "structured_output": structured,
        }
    )
)
