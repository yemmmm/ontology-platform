#!/usr/bin/env python3
"""Offline acceptance for the R2.1-001 M1 Workflow-as-Tool scenario."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pyshacl import validate
from rdflib import Graph, Namespace, RDF
from rdflib.namespace import OWL, RDFS
from owlrl import DeductiveClosure, RDFS_Semantics


PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[2]
IMPACT = Namespace("https://example.org/ontology/dify-workflow-impact-m1#")
PUBLISHED = Namespace("https://example.org/ontology/dify-workflow-impact-m1/fixture/published#")
DRAFT = Namespace("https://example.org/ontology/dify-workflow-impact-m1/fixture/draft#")


def graph_for(fixture: str) -> Graph:
    """Return a fresh graph so fixtures cannot leak state into one another."""
    graph = Graph()
    graph.parse(PACKAGE / "ontology.ttl", format="turtle")
    graph.parse(PACKAGE / "fixtures" / fixture, format="turtle")
    return graph


def query_text(name: str) -> str:
    return (PACKAGE / "queries" / name).read_text(encoding="utf-8")


class ScenarioAcceptanceTest(unittest.TestCase):
    def test_source_pack_hashes_are_offline_verifiable(self) -> None:
        manifest = json.loads((PACKAGE / "source-pack" / "manifest.json").read_text())
        self.assertEqual(
            manifest["source"]["commit"], "5396c1a1afbea0dee3d089abfabdf6dac91d30d5"
        )
        self.assertEqual(manifest["source"]["license"], "CC-BY-4.0")
        for entry in manifest["entries"]:
            path = PACKAGE / "source-pack" / entry["snapshot_path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
        prior = ROOT / "docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a"
        for entry in manifest["reused_existing_snapshot_entries"]:
            path = prior / entry["snapshot_path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])

    def test_all_rdf_artifacts_parse(self) -> None:
        for path in [
            PACKAGE / "ontology.ttl", PACKAGE / "shapes.ttl", *sorted((PACKAGE / "fixtures").glob("*.ttl"))
        ]:
            graph = Graph()
            graph.parse(path, format="turtle")
            self.assertGreater(len(graph), 0, path)

    def _validate(self, fixture: str) -> tuple[bool, str]:
        conforms, report, text = validate(
            data_graph=graph_for(fixture),
            shacl_graph=Graph().parse(PACKAGE / "shapes.ttl", format="turtle"),
            inference="none",
            abort_on_first=False,
            meta_shacl=False,
        )
        self.assertIsNotNone(report)
        return bool(conforms), str(text)

    def test_published_fixture_conforms_to_shacl(self) -> None:
        conforms, report = self._validate("published-deletion.ttl")
        self.assertTrue(conforms, report)

    def test_draft_fixture_conforms_to_shacl(self) -> None:
        conforms, report = self._validate("draft-deletion.ttl")
        self.assertTrue(conforms, report)

    def test_explicit_gap_fixture_is_conformant_and_keeps_unknown_visible(self) -> None:
        conforms, report = self._validate("explicit-gap.ttl")
        self.assertTrue(conforms, report)
        graph = graph_for("explicit-gap.ttl")
        gaps = list(graph.subjects(IMPACT.completeness, None))
        self.assertTrue(any(graph.value(gap, IMPACT.unknownDetail) for gap in gaps))

    def test_invalid_fixture_is_rejected_by_shacl(self) -> None:
        conforms, report = self._validate("invalid-invocation.ttl")
        self.assertFalse(conforms)
        self.assertIn("invokesTool", report)

    def test_limited_reasoner_produces_only_supported_rdfs_entailment(self) -> None:
        asserted_graph = graph_for("published-deletion.ttl")
        self.assertNotIn(
            (PUBLISHED["b-if-use"], IMPACT.referencesVariable, PUBLISHED["b-approved-content"]),
            asserted_graph,
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "tasks": ["rdfs-subproperty-check"],
                        "documents": [
                            {"path": str(PACKAGE / "ontology.ttl"), "format": "turtle"},
                            {"path": str(PACKAGE / "fixtures/published-deletion.ttl"), "format": "turtle"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "backend/scripts/dev_owl_reasoner.py"), str(manifest_path)],
                check=True,
                text=True,
                capture_output=True,
            )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["consistent"])
        expected = {
            "kind": "rdfs_subproperty_assertion",
            "subject": str(PUBLISHED["b-if-use"]),
            "predicate": str(IMPACT.referencesVariable),
            "object": str(PUBLISHED["b-approved-content"]),
            "rule": "rdfs:subPropertyOf",
        }
        self.assertTrue(any(expected.items() <= item.items() for item in payload["entailments"]))

    def test_standard_rdfs_keeps_variable_use_distinct_from_variable(self) -> None:
        closure = graph_for("published-deletion.ttl")
        DeductiveClosure(RDFS_Semantics).expand(closure)
        self.assertIn(
            (PUBLISHED["b-if-use"], IMPACT.referencesVariable, PUBLISHED["b-approved-content"]),
            closure,
        )
        self.assertIn((PUBLISHED["b-if-use"], RDF.type, IMPACT.VariableUse), closure)
        self.assertNotIn((PUBLISHED["b-if-use"], RDF.type, IMPACT.Variable), closure)

    def test_published_query_requires_exact_c_to_b_to_a_data_use_context(self) -> None:
        graph = graph_for("published-deletion.ttl")
        callers = {str(row.callerWorkflow) for row in graph.query(query_text("published-deletion.rq"))}
        self.assertEqual(callers, {str(PUBLISHED.b), str(PUBLISHED.a)})
        rows = list(graph.query(query_text("published-context.rq")))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(str(row.bInvocation), str(PUBLISHED["b-c-invocation"]))
        self.assertEqual(str(row.aInvocation), str(PUBLISHED["a-b-invocation"]))
        self.assertEqual(str(row.cBeforeVersion), str(PUBLISHED["c-v1"]))
        self.assertEqual(str(row.cVersion), str(PUBLISHED["c-v2"]))
        self.assertEqual(str(row.cInput), str(PUBLISHED["c-content"]))
        self.assertEqual(str(row.bCallSiteId), "b-v1.node.tool-c")
        self.assertEqual(str(row.aCallSiteId), "a-v1.node.tool-b")
        self.assertTrue(str(row.bCallSiteLocation))
        self.assertTrue(str(row.aCallSiteLocation))
        components = set(row)
        for component in components:
            if not str(component).startswith("http"):
                continue
            statuses = list(graph.objects(component, IMPACT.completeness))
            self.assertTrue(statuses, f"missing completeness for {component}")
            self.assertTrue({str(status) for status in statuses} <= {"complete", "explicit-gap"})

    def test_published_context_fails_for_each_removed_or_swapped_critical_link(self) -> None:
        graph = graph_for("published-deletion.ttl")
        critical_links = [
            (PUBLISHED["b-content-binding"], IMPACT.bindingSource, PUBLISHED["b-content-source"]),
            (PUBLISHED["b-content-binding"], IMPACT.bindingTarget, PUBLISHED["c-content"]),
            (PUBLISHED["b-quality-binding"], IMPACT.bindingSource, PUBLISHED["c-quality-score"]),
            (PUBLISHED["b-quality-binding"], IMPACT.bindingTarget, PUBLISHED["b-quality-score"]),
            (PUBLISHED["b-if-use"], IMPACT.usesVariable, PUBLISHED["b-quality-score"]),
            (PUBLISHED["b-if-use"], IMPACT.producesVariable, PUBLISHED["b-approved-content"]),
            (PUBLISHED["a-approved-binding"], IMPACT.bindingSource, PUBLISHED["b-approved-content"]),
            (PUBLISHED["a-approved-binding"], IMPACT.bindingTarget, PUBLISHED["a-publish-content"]),
            (PUBLISHED["a-publish-use"], IMPACT.usesVariable, PUBLISHED["a-publish-content"]),
        ]
        for subject, predicate, obj in critical_links:
            with self.subTest(subject=subject, predicate=predicate, obj=obj):
                mutated = Graph()
                for triple in graph:
                    mutated.add(triple)
                mutated.remove((subject, predicate, obj))
                mutated.add((subject, predicate, PUBLISHED["swapped-unrelated-variable"]))
                self.assertEqual(list(mutated.query(query_text("published-context.rq"))), [])

    def test_published_versions_have_direct_base_type_for_data_only_shacl(self) -> None:
        graph = graph_for("published-deletion.ttl")
        published_versions = set(graph.subjects(RDF.type, IMPACT.PublishedWorkflowVersion))
        self.assertTrue(published_versions)
        for version in published_versions:
            self.assertIn((version, RDF.type, IMPACT.WorkflowVersion), graph)

    def test_published_fixture_resources_are_visualizable_named_individuals(self) -> None:
        graph = graph_for("published-deletion.ttl")
        expected_resources = {
            PUBLISHED.c,
            PUBLISHED["c-v2"],
            PUBLISHED["published-delete-quality"],
            PUBLISHED.b,
            PUBLISHED["b-v1"],
            PUBLISHED["b-c-invocation"],
            PUBLISHED["b-if-use"],
            PUBLISHED["b-approved-content"],
            PUBLISHED.a,
            PUBLISHED["a-v1"],
            PUBLISHED["a-b-invocation"],
            PUBLISHED["a-publish-use"],
        }
        for resource in expected_resources:
            with self.subTest(resource=resource):
                self.assertIn((resource, RDF.type, OWL.NamedIndividual), graph)
                self.assertIsNotNone(graph.value(resource, RDFS.label))

    def test_draft_query_returns_draft_only_and_not_active_latest_path(self) -> None:
        graph = graph_for("draft-deletion.ttl")
        rows = list(graph.query(query_text("draft-only.rq")))
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0].draftVersion), str(DRAFT["c-draft"]))
        self.assertEqual(str(rows[0].activeLatestVersion), str(DRAFT["c-v1"]))
        self.assertNotIn((DRAFT.c, IMPACT.activeLatestVersion, DRAFT["c-draft"]), graph)


if __name__ == "__main__":
    unittest.main(verbosity=2)
