"""Standalone Platform Examiner probe for R2.3-006 iteration.

Runs the semantic query interface directly (no Codex child) to inspect what the
model would see, and optionally drives a real child with the current prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "backend")


SCOPE = {
    "project_id": "7fc146d8-c76f-417b-9314-854544f269fc",
    "ontology_id": "fd762f52-2f5e-4bc0-902a-5583135ab64d",
    "graph_set_id": "277fd804-e485-5156-b7a7-ca6a1081f950",
}


def _admin_key() -> str:
    from app.core.config import Settings
    from app.repositories.postgres import create_session_factory
    from app.security.auth import create_api_key

    session_factory = create_session_factory(Settings(_env_file=Path("backend") / ".env"))
    with session_factory() as session:
        _, key = create_api_key(session, name="r23006-standalone-probe", project_id=None, scopes=["admin"])
        return key


def query(key: str, text: str, *, depth: int = 1, limit: int = 10, context_limit: int = 10) -> dict:
    body = {
        "project_id": SCOPE["project_id"],
        "scope_mode": "ontologies",
        "ontology_ids": [SCOPE["ontology_id"]],
        "query": text,
        "depth": depth,
        "limit": limit,
        "context_limit": context_limit,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8001/api/semantic/context:query",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def tokens_of(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False)) // 4


def summarize(value: dict) -> str:
    out = [f"status={value.get('result_status')} truncated={value.get('truncated')}"]
    out.append(f"primary={len(value.get('primary_matches', []))} related={len(value.get('related_context', []))}")
    out.append(f"~{tokens_of(value)} tokens")
    for m in value.get("primary_matches", [])[:5]:
        out.append(f"  match: {m.get('kind')} {m.get('label')} d={m.get('distance')} score={m.get('match', {}).get('score')}")
    for w in value.get("warnings", [])[:3]:
        out.append(f"  warn: {w.get('code')}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="B 消费 C 的哪个已发布版本或输出，历史 quality_score 与当前 quality_rating 的业务连续性？")
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--context-limit", type=int, default=10)
    args = parser.parse_args()

    key = _admin_key()
    result = query(key, args.query, depth=args.depth, limit=args.limit, context_limit=args.context_limit)
    print(summarize(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
