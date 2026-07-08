"""Stage 4 §4.2 AgentTestService.

The service pre-fetches graph context via the ``agent-test-context`` read
model before invoking the LLM. The structured ``graph_context`` envelope is
returned alongside the LLM answer so the frontend ``AgentTestPage`` can
render each entry with an AssertionKind chip and a staleness warning.

Flow (spec §4.2):

1. Tokenize the question into 1–3 keywords (split whitespace, drop tokens
   ≤ 3 chars, lowercase).
2. For each keyword, call ``read_model_service.read_model(graph_set_id,
   "agent-test-context", q=kw, limit=15)``.
3. Union items by ``iri``, keeping the highest-priority ``assertion_kind``
   (``asserted > owl_inferred > rule_derived``).
4. Render a human-readable context block and prepend it to the LLM prompt.
5. Call the LLM and return the structured ``AgentTestResponse``.

If the LLM call fails, ``graph_context`` is still returned so the user can
see what was retrieved (spec §8).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.api.schemas import AgentTestRequest
from app.core.config import Settings
from app.services.semantic_read_model import ReadModelError, SemanticReadModelService

#: Priority ordering for union resolution. Lower index = higher priority.
#: ``asserted`` wins over inferred / rule-derived when the same entity
#: surfaces in multiple scopes.
_ASSERTION_KIND_PRIORITY: dict[str, int] = {
    "asserted": 0,
    "owl_inferred": 1,
    "rule_derived": 2,
}

#: Maximum number of question tokens to query the read model with.
_MAX_QUERY_TOKENS = 3

#: Minimum token length (lowercase, after whitespace split). Tokens shorter
#: than this are dropped — matches spec §13 CJK caveat note.
_MIN_TOKEN_LENGTH = 3


def _call_openai_compatible(
    settings: Settings,
    prompt: str,
) -> tuple[str | None, str | None]:
    model = settings.llm_model
    api_key = settings.llm_api_key
    if not api_key or not model:
        return None, "LLM_API_KEY and LLM_MODEL are not configured; cannot answer without graph context."

    base_url = settings.llm_base_url.rstrip("/")
    body = {
        "model": model,
        "temperature": settings.llm_temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer using the provided ontology graph context. "
                    "If context is insufficient, say what is missing."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return None, f"LLM request failed with HTTP {exc.code}"
    except (URLError, TimeoutError) as exc:
        return None, f"LLM request failed: {exc}"

    try:
        return data["choices"][0]["message"]["content"], None
    except (KeyError, IndexError, TypeError):
        return None, "LLM response did not match OpenAI-compatible chat completion format."


def _tokenize_question(question: str) -> list[str]:
    """Stage 4 §4.2 step 1: lowercase, split on whitespace, drop short tokens.

    The order is preserved so the first 1–3 surviving tokens (after dropping
    stopwords) carry the most salient nouns from a typical English question.
    See spec §13 for the CJK caveat — this naive tokenizer is intentionally
    English-only for Stage 4.
    """
    tokens: list[str] = []
    for raw in question.split():
        token = raw.strip().lower()
        if len(token) <= _MIN_TOKEN_LENGTH:
            continue
        if token in tokens:
            continue
        tokens.append(token)
    return tokens[:_MAX_QUERY_TOKENS]


def _assertion_priority(kind: str) -> int:
    """Lower number wins. Unknown kinds sort last."""
    return _ASSERTION_KIND_PRIORITY.get(kind, 99)


def _union_entries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stage 4 §4.2 step 3: union items by ``iri``, keeping the highest
    priority ``assertion_kind``. Order is preserved by first-seen."""
    by_iri: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        iri = item.get("iri") or item.get("id") or ""
        if not iri:
            continue
        if iri not in by_iri:
            by_iri[iri] = dict(item)
            order.append(iri)
            continue
        existing = by_iri[iri]
        if _assertion_priority(item.get("assertion_kind", "")) < _assertion_priority(
            existing.get("assertion_kind", "")
        ):
            # Keep the higher-priority assertion_kind but preserve the
            # label/class_label/scope fields from whichever row carried it.
            merged = dict(existing)
            merged["assertion_kind"] = item["assertion_kind"]
            merged["source_graph_iri"] = item.get(
                "source_graph_iri", existing.get("source_graph_iri")
            )
            merged["source_signature"] = item.get(
                "source_signature", existing.get("source_signature")
            )
            by_iri[iri] = merged
    return [by_iri[iri] for iri in order]


def _entry_to_response(entry: dict[str, Any]) -> dict[str, Any]:
    """Project a read-model item into the §7.2 response entry shape."""
    assertion_kind = entry.get("assertion_kind") or "asserted"
    if assertion_kind not in {"asserted", "owl_inferred", "rule_derived"}:
        assertion_kind = "asserted"
    staleness = entry.get("staleness") or {}
    return {
        "iri": entry.get("iri") or entry.get("id") or "",
        "label": entry.get("label"),
        "class_label": entry.get("class_label"),
        "assertion_kind": assertion_kind,
        "source_graph_iri": entry.get("source_graph_iri") or "",
        "source_signature": entry.get("source_signature"),
        "is_stale": bool(staleness.get("is_stale", False)) if isinstance(staleness, dict) else False,
    }


def _render_prompt_block(entries: list[dict[str, Any]]) -> str:
    """Render the graph context as a human-readable block for the LLM."""
    if not entries:
        return "(No ontology graph context was retrieved for this question.)"
    lines = ["Graph context (from the active graph set):"]
    for idx, entry in enumerate(entries, start=1):
        label = entry.get("label") or entry["iri"]
        class_label = entry.get("class_label") or "unknown class"
        kind = entry.get("assertion_kind", "asserted")
        lines.append(
            f"{idx}. {label} ({class_label}) — {kind} in {entry['source_graph_iri']}"
        )
    return "\n".join(lines)


def run_agent_test(
    session: Session,  # noqa: ARG001 - kept for API signature compatibility
    driver: Any,  # noqa: ARG001 - deprecated, kept for API signature compatibility
    settings: Settings,
    payload: AgentTestRequest,
    embedding_client: Any,  # noqa: ARG001 - kept for API signature compatibility
    read_model_service: SemanticReadModelService,
) -> dict[str, Any]:
    """Stage 4 §4.2 agent-test run.

    Pre-fetches graph context via the ``agent-test-context`` read model,
    renders it into the LLM prompt, calls the LLM, and returns the structured
    ``graph_context`` envelope. LLM failures do not block returning the
    retrieved context (spec §8).
    """
    warnings: list[str] = []
    errors: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    tokens = _tokenize_question(payload.question)
    unioned: list[dict[str, Any]] = []
    retrieval_warnings: list[dict[str, str]] = []
    for token in tokens:
        try:
            envelope = read_model_service.read_model(
                graph_set_id=payload.graph_set_id,
                model_name="agent-test-context",
                q=token,
                limit=15,
            )
        except ReadModelError as exc:
            warnings.append(
                f"agent-test-context retrieval failed for token {token!r}: {exc}"
            )
            continue
        items = envelope.get("items") or []
        retrieval_warnings.extend(envelope.get("warnings") or [])
        unioned = _union_entries(unioned + items)

    if not unioned:
        warnings.append("No graph context matched the question.")
    if retrieval_warnings:
        # Surface a single condensed warning so the response payload stays
        # readable; the full warnings list is preserved in the read-model
        # envelope already returned to the user via the scope field.
        codes = sorted({w.get("code", "unknown") for w in retrieval_warnings})
        warnings.append(f"Read model returned {len(retrieval_warnings)} warning(s): {', '.join(codes)}")

    response_entries = [_entry_to_response(e) for e in unioned]
    context_block = _render_prompt_block(unioned)
    prompt = f"Question:\n{payload.question}\n\n{context_block}"

    answer, llm_warning = _call_openai_compatible(settings, prompt)
    if llm_warning:
        warnings.append(llm_warning)
    if answer is None:
        answer = ""
        errors.append("LLM call failed; see warnings for details.")

    graph_context = {
        "entries": response_entries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "graph_set_id": payload.graph_set_id,
            "ontology_id": payload.ontology_id,
        },
    }

    return {
        "answer": answer,
        "tool_calls": tool_calls,
        "graph_context": graph_context,
        "prompt_preview": prompt[:4000],
        "warnings": warnings,
        "errors": errors,
    }
