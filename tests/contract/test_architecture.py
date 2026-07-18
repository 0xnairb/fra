import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "src" / "fra"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_has_no_outward_or_third_party_imports() -> None:
    forbidden_prefixes = (
        "fra.application",
        "fra.ports",
        "fra.adapters",
        "fra.factories",
        "fra.cli",
        "fra.config",
        "httpx",
        "pydantic",
        "typer",
        "yaml",
    )

    for path in (ROOT / "domain").glob("*.py"):
        for module in imported_modules(path):
            assert not module.startswith(forbidden_prefixes), f"{path}: forbidden import {module}"


def test_application_does_not_import_cli_or_adapters() -> None:
    for path in (ROOT / "application").rglob("*.py"):
        for module in imported_modules(path):
            assert not module.startswith(("fra.cli", "fra.adapters", "fra.factories")), (
                f"{path}: forbidden import {module}"
            )


def test_ports_depend_only_on_domain_and_standard_library() -> None:
    allowed_project_prefixes = ("fra.domain", "fra.ports")
    for path in (ROOT / "ports").glob("*.py"):
        for module in imported_modules(path):
            if module.startswith("fra."):
                assert module.startswith(allowed_project_prefixes), (
                    f"{path}: forbidden import {module}"
                )
