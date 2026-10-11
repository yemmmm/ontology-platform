"""R2.3-009 start21: examiner children must not hand-build protocol mechanics.

Both examiner kinds died on sink rejections the child could never repair:

* Platform: the locator ``page`` chain had to be transcribed by hand from the
  proxy responses.  The proxy now derives each page deterministically at call
  time (exact request cursors plus the platform's own ``truncated`` /
  ``next_*_cursor`` markers) and the sink stamps it onto the delivered locator
  exactly like the digests.
* Source: the formal child's projected ``input.json`` names the approved
  sources by path/digest only while its instructions forbid reading staged
  files, so the bytes its report must quote were unreachable.  The formal
  first turn now carries ``SOURCE_TEXT_JSON`` built from the staged,
  digest-verified bytes (the lean seam), and a formal Source child without
  staged bytes fails closed at start.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.acceptance_runtime import (
    ScopedReadProxy,
    _proxy_page_for_call,
    _validate_platform_report_receipts,
    ExaminerRuntimeBlocked,
)


def _proxy(*, forward) -> ScopedReadProxy:
    import tempfile
    import threading

    root = Path(tempfile.mkdtemp(prefix="r23009-proxy-test-"))
    self = ScopedReadProxy.__new__(ScopedReadProxy)
    self.socket_path = root / "proxy.sock"
    self.token = "token"
    self._read_key = "key"
    self.project_id = "project-one"
    self.ontology_id = "ontology-one"
    self.ontology_id = "graph-one"
    self.ticket_digest = "a" * 64
    self.model_state_digest = "b" * 64
    self.allowed_tools = ("query_semantic_context", "get_ontology_read_model")
    self.exact_schemas = None
    self.acceptance_round_id = "round-one"
    self.child_handle_digest = "c" * 64
    self._forward = forward
    self._response_material = None
    self._lock = threading.RLock()
    self._call_receipts = []
    self.requests = []
    self.backend_calls = 0
    self.schema_rejections = 0
    self.post_revoke_denials = 0
    # ``__new__`` skips ``__init__``, so the legacy single-Ontology state the
    # constructor normally establishes must be set explicitly: this fixture is
    # a legacy proxy, not a v3 multi-Ontology one.
    self.authorized_ontologies = ()
    return self


class ProxyPageTests(unittest.TestCase):
    def test_complete_call_is_ordinal_zero_sequence_complete(self) -> None:
        page = _proxy_page_for_call(None, {}, {"matches_page": {"returned": 3}})
        self.assertEqual(
            page,
            {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        )

    def test_truncated_matches_page_carries_output_cursor(self) -> None:
        page = _proxy_page_for_call(
            None,
            {"match_cursor": "cursor-0"},
            {
                "matches_page": {
                    "returned": 20,
                    "truncated": True,
                    "next_match_cursor": "cursor-1",
                },
                "context_page": {"returned": 4, "truncated": False},
            },
        )
        self.assertEqual(page["ordinal"], 0)
        self.assertEqual(page["input_cursor"], "cursor-0")
        self.assertTrue(page["has_more"])
        self.assertFalse(page["sequence_complete"])
        self.assertEqual(page["output_cursor"], "cursor-1")

    def test_continuation_with_returned_cursor_advances_ordinal(self) -> None:
        previous = _proxy_page_for_call(
            None,
            {},
            {"matches_page": {"truncated": True, "next_match_cursor": "cursor-1"}},
        )
        page = _proxy_page_for_call(
            previous,
            {"match_cursor": "cursor-1"},
            {"matches_page": {"truncated": False, "next_match_cursor": None}},
        )
        self.assertEqual(page["ordinal"], 1)
        self.assertEqual(page["input_cursor"], "cursor-1")
        self.assertFalse(page["has_more"])
        self.assertIsNone(page["output_cursor"])
        self.assertTrue(page["sequence_complete"])

    def test_context_only_truncation_uses_context_cursor(self) -> None:
        previous = _proxy_page_for_call(
            None,
            {},
            {"context_page": {"truncated": True, "next_context_cursor": "ctx-1"}},
        )
        self.assertEqual(previous["output_cursor"], "ctx-1")
        page = _proxy_page_for_call(
            previous,
            {"context_cursor": "ctx-1"},
            {"context_page": {"truncated": False, "next_context_cursor": None}},
        )
        self.assertEqual(page["ordinal"], 1)
        self.assertEqual(page["input_cursor"], "ctx-1")

    def test_fresh_call_after_complete_call_stays_ordinal_zero(self) -> None:
        page = _proxy_page_for_call(
            {"ordinal": 0, "output_cursor": None, "has_more": False},
            {},
            {},
        )
        self.assertEqual(page["ordinal"], 0)


class ReceiptPageStampTests(unittest.TestCase):
    def test_receipts_record_pages_and_sink_stamps_bare_locators(self) -> None:
        results = [
            {
                "matches_page": {
                    "returned": 20,
                    "truncated": True,
                    "next_match_cursor": "cursor-1",
                }
            },
            {"matches_page": {"returned": 2, "truncated": False}},
        ]
        calls: list[dict] = []

        def forward(_tool, arguments, _key):
            calls.append(dict(arguments))
            return results[len(calls) - 1]

        proxy = _proxy(forward=forward)
        first = proxy.handle(
            {
                "token": "token",
                "operation": "tools/call",
                "tool": "query_semantic_context",
                "arguments": {"project_id": "project-one"},
            }
        )
        self.assertTrue(first["ok"])
        second = proxy.handle(
            {
                "token": "token",
                "operation": "tools/call",
                "tool": "query_semantic_context",
                "arguments": {"project_id": "project-one", "match_cursor": "cursor-1"},
            }
        )
        self.assertTrue(second["ok"])
        receipts = proxy.receipt_snapshot
        self.assertEqual([r.page["ordinal"] for r in receipts], [0, 1])
        self.assertTrue(receipts[0].page["has_more"])
        self.assertFalse(receipts[1].page["has_more"])
        self.assertEqual(receipts[1].page["input_cursor"], "cursor-1")

        # The start21 regression: a child that omits every digest, artifact
        # path, and page object — supplying only ref_id and tool — must have a
        # fully valid locator stamped from the receipts.
        report = {
            "evidence_refs": [
                {"ref_id": "p0", "tool": "query_semantic_context"},
                {"ref_id": "p1", "tool": "query_semantic_context"},
            ]
        }
        resource = SimpleNamespace(proxy=SimpleNamespace(receipt_snapshot=receipts))
        ids = _validate_platform_report_receipts(report, resource)
        self.assertEqual(ids, {"p0", "p1"})
        stamped0, stamped1 = report["evidence_refs"]
        self.assertEqual(stamped0["page"], receipts[0].page)
        self.assertEqual(stamped1["page"], receipts[1].page)
        self.assertEqual(stamped0["request_digest"], receipts[0].request_digest)
        self.assertEqual(stamped1["artifact_path"], receipts[1].artifact_path)

    def test_stamped_chain_still_rejects_interleaving_after_truncation(self) -> None:
        def forward(tool, _arguments, _key):
            if tool == "query_semantic_context":
                return {"matches_page": {"truncated": True, "next_match_cursor": "cursor-1"}}
            return {"value": 1}

        proxy = _proxy(forward=forward)
        proxy.handle(
            {
                "token": "token",
                "operation": "tools/call",
                "tool": "query_semantic_context",
                "arguments": {"project_id": "project-one"},
            }
        )
        proxy.handle(
            {
                "token": "token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {"project_id": "project-one"},
            }
        )
        receipts = proxy.receipt_snapshot
        report = {
            "evidence_refs": [
                {"ref_id": "p0", "tool": "query_semantic_context"},
                {"ref_id": "p1", "tool": "get_ontology_read_model"},
            ]
        }
        resource = SimpleNamespace(proxy=SimpleNamespace(receipt_snapshot=receipts))
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            _validate_platform_report_receipts(report, resource)
        self.assertEqual(
            blocked.exception.evidence, {"binding_code": "page-first-invalid", "index": 1}
        )


class FormalSourceTextTests(unittest.TestCase):
    def test_formal_source_child_without_staged_sources_fails_closed(self) -> None:
        import json
        import tempfile

        from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            private_root = base / "private-child"
            private_root.mkdir(mode=0o700)
            (private_root / "input.json").write_text("{}", encoding="utf-8")
            spec = {
                "task_id": "r2-3-009-formal-acceptance",
                "acceptance_round_id": "round-one",
                "kind": "source",
                "attempt": 0,
                "session_id": "session-one",
                "child_handle_digest": "c" * 64,
                "ticket_digest": "a" * 64,
                "input_digest": "d" * 64,
                "private_root": str(private_root),
                "private_input": str(private_root / "input.json"),
                "descriptor": {"kind": "source_examiner", "package_digest": "f" * 64},
                "timeout_seconds": 30,
            }
            adapter = CodexRuntimeAdapter.__new__(CodexRuntimeAdapter)
            adapter._coordination_enabled = True
            adapter._run_root = base
            try:
                adapter._launch_acceptance_child_impl(spec)
            except CodexRuntimeError as exc:
                self.assertIn("approved material is unavailable", str(exc))
            else:
                raise AssertionError("formal source child without staged bytes must fail closed")


if __name__ == "__main__":
    unittest.main()
