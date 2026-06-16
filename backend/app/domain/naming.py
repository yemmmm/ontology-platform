import re


_NON_ALNUM = re.compile(r"[^0-9a-zA-Z]+")


def normalize_neo4j_relationship_type(name: str) -> str:
    normalized = _NON_ALNUM.sub("_", name).strip("_").upper()
    if not normalized:
        return "RELATION"
    if normalized[0].isdigit():
        return f"REL_{normalized}"
    return normalized


def normalize_neo4j_label(name: str) -> str:
    normalized = _NON_ALNUM.sub("_", name).strip("_")
    if not normalized:
        return "Thing"
    if normalized[0].isdigit():
        return f"Class_{normalized}"
    return normalized
