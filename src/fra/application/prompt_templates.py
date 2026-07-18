"""Versioned prompt template loading for research stages."""

from __future__ import annotations

import json
from importlib.resources import files


class PromptTemplateRegistry:
    VERSION = 1

    def render(
        self,
        stage: str,
        *,
        question: str,
        durable_results: dict[str, object],
        repair_error: str | None = None,
        workflow: str | None = None,
    ) -> str:
        root = files("fra.templates.prompts.v1")
        workflow_name = f"{workflow}_{stage}.txt" if workflow else None
        candidate = root.joinpath(workflow_name) if workflow_name else None
        template_path = (
            candidate
            if candidate is not None and candidate.is_file()
            else root.joinpath(f"{stage}.txt")
        )
        template = template_path.read_text(encoding="utf-8")
        rendered = template.format(
            question=question,
            durable_results=json.dumps(durable_results, sort_keys=True),
        )
        if repair_error is not None:
            return (
                "Repair the previous structured output. Return only content matching the "
                f"provided schema. Validation error: {repair_error}\n\n{rendered}"
            )
        return rendered
