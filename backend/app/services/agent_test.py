import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.schemas import AgentTestRequest
from app.core.config import Settings
from app.services import graph as graph_service


def _call_openai_compatible(
    settings: Settings,
    payload: AgentTestRequest,
    prompt: str,
) -> tuple[str | None, str | None]:
    model = payload.model or settings.llm_model
    api_key = settings.llm_api_key
    if not api_key or not model:
        return None, "LLM_API_KEY and LLM_MODEL are not configured; returned graph-context answer."

    base_url = (payload.base_url or settings.llm_base_url).rstrip("/")
    temperature = payload.temperature
    if temperature is None:
        temperature = settings.llm_temperature
    body = {
        "model": model,
        "temperature": temperature,
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


def run_agent_test(
    session: Session,
    driver: Driver,
    settings: Settings,
    payload: AgentTestRequest,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    search_result = graph_service.search_entities(
        session,
        driver,
        payload.ontology_id,
        payload.question,
        class_id=None,
        limit=5,
    )
    tool_calls.append(
        {
            "tool": "search_entities",
            "arguments": {"ontology_id": payload.ontology_id, "query": payload.question, "limit": 5},
            "result_count": search_result["count"],
        }
    )

    explanations = []
    for entity in search_result["results"][:3]:
        explained = graph_service.explain_entity(
            session,
            driver,
            payload.ontology_id,
            entity["id"],
            depth=1,
            limit=10,
        )
        explanations.append(explained)
        tool_calls.append(
            {
                "tool": "explain_entity",
                "arguments": {"ontology_id": payload.ontology_id, "entity_id": entity["id"]},
                "result": explained["explain_text"],
            }
        )

    graph_context = {
        "search_results": search_result["results"],
        "explanations": explanations,
    }
    context_text = json.dumps(graph_context, ensure_ascii=False, default=str, indent=2)
    prompt = f"Question:\n{payload.question}\n\nOntology graph context:\n{context_text}"

    answer, warning = _call_openai_compatible(settings, payload, prompt)
    if warning:
        warnings.append(warning)
    if answer is None:
        if search_result["results"]:
            names = ", ".join(entity["name"] for entity in search_result["results"])
            answer = (
                f"Found {search_result['count']} matching graph entity/entities for the question: "
                f"{names}. Configure LLM_API_KEY and LLM_MODEL for generated natural-language answers."
            )
        else:
            answer = (
                "No matching graph entities were found. Add entities or configure the LLM to reason "
                "over broader context."
            )

    return {
        "answer": answer,
        "tool_calls": tool_calls,
        "graph_context": graph_context,
        "prompt_preview": prompt[:4000],
        "warnings": warnings,
        "errors": errors,
    }
