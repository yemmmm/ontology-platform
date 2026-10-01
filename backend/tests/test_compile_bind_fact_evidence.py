"""The suspended fact-evidence compiler commands stay unavailable."""

import pytest

from app.core.config import Settings
from app.services.semantic_command_compiler import UnsupportedCommandKind, compile_command


@pytest.mark.parametrize("command_kind", ["bind_fact_evidence", "unbind_fact_evidence"])
def test_fact_evidence_commands_are_not_compilable(command_kind):
    with pytest.raises(UnsupportedCommandKind):
        compile_command(command_kind, {}, Settings())
