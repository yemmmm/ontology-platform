"""R2.3-009 static conservation tests (kill-path whitelist / C-class no-raise).

These tests source-scan the implementation modules so any regression that
re-introduces a validator kill path or a blocking retrieval-quality scan fails
loudly, forcing the developer to register and classify the new site explicitly.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from modeling_team import protocol_retrieval_gate
from modeling_team import runner

_REPO_ROOT = Path(runner.__file__).resolve().parent


def test_validate_response_quality_has_no_raise_branch() -> None:
    """C-class boundary: the response-quality scan must be record-only."""

    tree = ast.parse(
        (Path(protocol_retrieval_gate.__file__).resolve()).read_text(encoding="utf-8")
    )
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_validate_response_quality"
    )
    raises = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Raise)
    ]
    assert not raises, "_validate_response_quality must never raise (R2.3-009 C-class)"
