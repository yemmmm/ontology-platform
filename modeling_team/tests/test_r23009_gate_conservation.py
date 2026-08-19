"""R2.3-009 static conservation tests (kill-path whitelist / C-class no-raise).

These tests source-scan the implementation modules so any regression that
re-introduces a validator kill path or a blocking retrieval-quality scan fails
loudly, forcing the developer to register and classify the new site explicitly.
"""

from __future__ import annotations

import ast
from pathlib import Path

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


def _literal_call_sites(source: str, callee_name: str) -> list[tuple[str, str]]:
    """Return the literal (classification, reason) pairs of every call site."""

    tree = ast.parse(source)
    sites: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (
            isinstance(function, ast.Attribute)
            and function.attr == callee_name
            and isinstance(function.value, ast.Name)
            and function.value.id == "self"
        ):
            continue
        args = node.args
        if (
            len(args) >= 2
            and all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in args[:2])
        ):
            sites.append((args[0].value, args[1].value))
        else:
            sites.append(("<non-literal>", "<non-literal>"))
    return sites


def test_formal_failure_latch_call_sites_match_the_whitelist_registry() -> None:
    """I/S/T3 conservation: no latch call site may exist outside the registry."""

    source = (Path(runner.__file__).resolve()).read_text(encoding="utf-8")
    sites = _literal_call_sites(source, "_latch_formal_candidate_failure")
    pairs = {f"{classification}:{reason}" for classification, reason in sites}
    whitelist = set(runner.TeamRunner._FORMAL_FAILURE_LATCH_WHITELIST)
    # The definition itself passes its arguments dynamically; every call site
    # must be literal and registered.
    assert pairs, "the latch must keep at least the T3 whitelist entry"
    unregistered = pairs - whitelist
    assert not unregistered, f"unregistered latch call sites: {sorted(unregistered)}"
    stale = whitelist - pairs
    assert not stale, f"whitelist entries without call sites: {sorted(stale)}"


def test_whitelisted_latch_reasons_are_prefixed_by_class() -> None:
    """Every non-T3 whitelist entry must carry its S/I attribution prefix."""

    whitelist = runner.TeamRunner._FORMAL_FAILURE_LATCH_WHITELIST
    for entry in whitelist:
        classification, reason = entry.split(":", 1)
        if entry == "collaboration/routing:run-fallback-timeout":
            continue
        if classification == "runtime/infrastructure":
            continue
        assert reason.startswith("internal-invariant:"), entry
