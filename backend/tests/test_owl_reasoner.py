from pathlib import Path

from app.services.owl_reasoner import CommandOwlReasonerRunner, ReasonerInputDocument


def test_dev_owl_reasoner_command_satisfies_runner_contract() -> None:
    command = Path(__file__).parents[1] / "scripts" / "dev_owl_reasoner.py"
    runner = CommandOwlReasonerRunner(str(command))

    result = runner.run(
        [
            ReasonerInputDocument(
                graph_iri="http://ontology-platform.local/semantic/graph/test",
                content="@prefix ex: <http://example.test/> . ex:a a ex:Thing .",
            )
        ],
        tasks=["consistency", "classification"],
        timeout_seconds=5,
    )

    assert result.consistent is True
    assert result.classification["mode"] == "development_stub"
    assert result.classification["source_graph_count"] == 1
    assert result.entailments == []
    assert result.metadata["engine_name"] == "development_stub"
