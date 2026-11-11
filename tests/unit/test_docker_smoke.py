"""Regression checks for the isolated Docker smoke workflow."""

import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "docker_smoke.py"


def test_waited_smoke_up_targets_only_the_web_service() -> None:
    tree = ast.parse(SCRIPT.read_text())
    waited_up_calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "compose":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != "up":
            continue
        if any(isinstance(arg, ast.Constant) and arg.value == "--wait" for arg in node.args[1:]):
            waited_up_calls.append(node)

    assert waited_up_calls, "the smoke test should wait for Compose startup"
    assert all(
        any(isinstance(arg, ast.Constant) and arg.value == "web" for arg in call.args[1:])
        for call in waited_up_calls
    ), "Compose --wait must target web, not the worker with no healthcheck"
