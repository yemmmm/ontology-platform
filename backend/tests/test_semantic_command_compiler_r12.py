"""Focused compiler regressions for the M4 Round-12 Turtle serialization repair."""

from __future__ import annotations

import re

from app.core.config import Settings
from app.services import semantic_command_compiler as compiler
from app.services.semantic_command_compiler import compile_command


def _settings() -> Settings:
    return Settings(
        semantic_base_iri="http://op.local/ns/",
        semantic_graph_iri_prefix="http://op.local/graph/",
    )


def test_datatype_iri_normalizes_only_recognized_bare_xsd_names() -> None:
    assert compiler._datatype_iri("string") == "http://www.w3.org/2001/XMLSchema#string"
    assert compiler._datatype_iri("xsd:string") == "http://www.w3.org/2001/XMLSchema#string"
    absolute = "https://example.test/custom-datatype"
    assert compiler._datatype_iri(absolute) == absolute
    assert compiler._datatype_iri("customDatatype") == "customDatatype"
