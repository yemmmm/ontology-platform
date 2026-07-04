from dataclasses import dataclass, field
import json
import subprocess
import tempfile
from pathlib import Path


class OwlReasonerUnavailable(RuntimeError):
    pass


@dataclass
class ReasonerInputDocument:
    graph_iri: str
    content: str
    format: str = "trig"


@dataclass
class OwlReasonerResult:
    consistent: bool
    classification: dict[str, object] = field(default_factory=dict)
    entailments: list[dict[str, object]] = field(default_factory=list)
    inferred_rdf: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class OwlReasonerRunner:
    def run(
        self,
        source_documents: list[ReasonerInputDocument],
        tasks: list[str],
        timeout_seconds: float,
    ) -> OwlReasonerResult:
        raise NotImplementedError


class CommandOwlReasonerRunner(OwlReasonerRunner):
    def __init__(self, command: str) -> None:
        self.command = command

    def run(
        self,
        source_documents: list[ReasonerInputDocument],
        tasks: list[str],
        timeout_seconds: float,
    ) -> OwlReasonerResult:
        if not self.command:
            raise OwlReasonerUnavailable("SEMANTIC_REASONER_COMMAND is not configured")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = {"tasks": tasks, "documents": []}
            for index, document in enumerate(source_documents):
                path = tmp_path / f"source-{index}.trig"
                path.write_text(document.content, encoding="utf-8")
                manifest["documents"].append(
                    {"graph_iri": document.graph_iri, "path": str(path), "format": document.format}
                )
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = subprocess.run(
                [self.command, str(manifest_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        if completed.returncode != 0:
            raise OwlReasonerUnavailable(completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout or "{}")
        return OwlReasonerResult(
            consistent=bool(payload.get("consistent", True)),
            classification=payload.get("classification", {}),
            entailments=payload.get("entailments", []),
            inferred_rdf=payload.get("inferred_rdf"),
            metadata=payload.get("metadata", {}),
        )
