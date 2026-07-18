#!/usr/bin/env python3
"""Process fixture that exposes the Codex CLI surface used by FRA."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    mode = os.environ.get("FAKE_CODEX_MODE", "success")
    if args == ["--version"]:
        print("codex-cli 0.999.0")
        return 0
    if args == ["login", "status"]:
        if mode == "auth_failure":
            print("Not logged in: token=fake-secret", file=sys.stderr)
            return 1
        print("Logged in using ChatGPT")
        return 0
    if args == ["exec", "--help"]:
        print("--json --output-schema FILE --output-last-message FILE resume SESSION_ID")
        return 0
    if not args or args[0] != "exec":
        print("unsupported fixture invocation", file=sys.stderr)
        return 2
    if os.environ.get("FAKE_CODEX_REQUIRE_SKIP_GIT") == "1" and "--skip-git-repo-check" not in args:
        print(
            "Not inside a trusted directory and --skip-git-repo-check was not specified.",
            file=sys.stderr,
        )
        return 2

    prompt = sys.stdin.read()
    if not prompt:
        print("missing stdin prompt", file=sys.stderr)
        return 2
    if mode == "jsonl_error":
        print(json.dumps({"type": "error", "message": "fixture JSONL failure"}), flush=True)
        return 1
    session_id = "fixture-session-resumed" if "resume" in args else "fixture-session"
    print(json.dumps({"type": "thread.started", "thread_id": session_id}), flush=True)
    print(json.dumps({"type": "turn.started"}), flush=True)

    schema_path = Path(args[args.index("--output-schema") + 1])
    schema_id = json.loads(schema_path.read_text(encoding="utf-8")).get("$id")

    targeted_cancel = mode.startswith("cancel:") and mode.partition(":")[2] == schema_id
    if mode in {"timeout", "cancel"} or targeted_cancel:
        started_marker = os.environ.get("FAKE_CODEX_STARTED_MARKER")
        if started_marker:
            Path(started_marker).write_text("started", encoding="utf-8")
        marker = os.environ.get("FAKE_CODEX_CHILD_MARKER")
        if marker:
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import pathlib,time,sys; time.sleep(1); "
                    "pathlib.Path(sys.argv[1]).write_text('alive')",
                    marker,
                ]
            )
        time.sleep(30)
        return 0

    output_path = Path(args[args.index("-o") + 1])
    if mode == "malformed":
        output_path.write_text("{not-json", encoding="utf-8")
    else:
        configured_outputs = os.environ.get("FAKE_CODEX_OUTPUTS")
        configured = os.environ.get("FAKE_CODEX_OUTPUT")
        if configured_outputs is not None:
            payload = json.loads(configured_outputs)[schema_id]
        elif configured is not None:
            payload = json.loads(configured)
        else:
            payload = {
                "fra.agent.plan.v2": {
                    "objective": "Answer the question",
                    "tasks": [
                        {
                            "task_id": "task_1",
                            "description": "inspect durable inputs",
                            "depends_on": [],
                        }
                    ],
                    "data_requirements": [
                        {
                            "requirement_id": "requirement_1",
                            "description": "collect fixture evidence",
                            "data_kind": "document",
                            "subject_ids": ["fixture:document"],
                            "fields": ["content"],
                            "geography_or_market": None,
                            "resolution": None,
                            "freshness": None,
                        }
                    ],
                },
                "fra.agent.analyze.v2": {
                    "claims": [
                        {
                            "statement": "The fixture evidence is available.",
                            "materiality": "high",
                            "confidence": "high",
                            "evidence_ids": ["evidence_fixture"],
                            "calculation_ids": [],
                            "limitations": [],
                        }
                    ],
                    "scenarios": [
                        {
                            "title": "Base",
                            "description": "The fixture remains available.",
                            "evidence_ids": ["evidence_fixture"],
                            "invalidation_conditions": ["the fixture is withdrawn"],
                        }
                    ],
                    "open_questions": [],
                },
                "fra.agent.verify.v2": {"passed": True, "issues": []},
                "fra.agent.synthesize.v2": {
                    "title": "Fixture research",
                    "summary": "Done",
                    "limitations": [],
                },
            }[schema_id]
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        print(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": json.dumps(payload)},
                }
            ),
            flush=True,
        )
    print(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        ),
        flush=True,
    )
    print("diagnostic token=fake-secret", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
