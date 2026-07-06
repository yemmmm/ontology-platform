import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.api.schemas import AgentTestRequest
from app.core.config import Settings


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


def run_agent_test(
    session: Session,  # noqa: ARG001 - kept for API compatibility
    driver: Any,  # noqa: ARG001 - kept for API compatibility
    settings: Settings,
    payload: AgentTestRequest,
    embedding_client: Any,  # noqa: ARG001 - kept for API compatibility
) -> dict[str, Any]:
    """Run the agent test.

    Stage 3 B2 hard-cut: the legacy graph service (entity search/explain) was
    deleted along with the legacy metadata stack. Until a semantic-stack
    replacement ships, this returns a no-graph-context answer so the endpoint
    stays reachable for the frontend ``AgentTestPage``.
    """
    warnings: list[str] = [
        "Graph context unavailable: legacy entity search was removed in Stage 3 B2."
    ]
    errors: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    prompt = (
        f"Question:\n{payload.question}\n\n"
        "(No ontology graph context is available in this build.)"
    )

    answer, warning = _call_openai_compatible(settings, prompt)
    if warning:
        warnings.append(warning)
    if answer is None:
        answer = (
            "Agent test is unavailable in this build: the legacy entity graph "
            "was removed and no semantic replacement is wired yet."
        )

    return {
        "answer": answer,
        "tool_calls": tool_calls,
        "graph_context": {},
        "prompt_preview": prompt[:4000],
        "warnings": warnings,
        "errors": errors,
    }
