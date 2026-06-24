from types import SimpleNamespace

import pytest

from app.mcp.tools.documents import _chunk_page
from app.mcp.tools.proposals import _parse_proposal_json


def test_parse_proposal_json_accepts_an_object() -> None:
    assert _parse_proposal_json('{"proposal_type":"entity","payload":{"items":[]}}') == {
        "proposal_type": "entity",
        "payload": {"items": []},
    }


@pytest.mark.parametrize("value", ["not-json", "[]", '"text"'])
def test_parse_proposal_json_rejects_invalid_envelopes(value: str) -> None:
    with pytest.raises(ValueError, match="proposal_json"):
        _parse_proposal_json(value)


def test_chunk_page_preserves_exact_evidence_fields() -> None:
    rows = [
        SimpleNamespace(
            id="chunk-1",
            document_id="document-1",
            sequence=0,
            parse_revision=2,
            page_number=None,
            char_start=10,
            char_end=21,
            text="hello\nworld",
            content_hash="a" * 64,
        )
    ]

    result = _chunk_page(rows, "document-1", offset=0, limit=20)

    assert result == {
        "document_id": "document-1",
        "offset": 0,
        "limit": 20,
        "total": 1,
        "chunks": [
            {
                "id": "chunk-1",
                "document_id": "document-1",
                "sequence": 0,
                "parse_revision": 2,
                "page_number": None,
                "char_start": 10,
                "char_end": 21,
                "text": "hello\nworld",
                "content_hash": "a" * 64,
            }
        ],
    }


@pytest.mark.parametrize("offset,limit", [(-1, 20), (0, 0), (0, 101)])
def test_chunk_page_rejects_invalid_bounds(offset: int, limit: int) -> None:
    with pytest.raises(ValueError):
        _chunk_page([], "document-1", offset=offset, limit=limit)
