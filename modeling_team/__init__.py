"""Repository-local deterministic runner for a frozen ontology modeling team."""

__all__ = ["TeamConfigurationError", "TeamRunner", "load_team_configuration"]


def __getattr__(name: str):
    """Keep public exports without loading the legacy Runner for mechanical imports."""
    if name == "TeamRunner":
        from .runner import TeamRunner

        value = TeamRunner
    elif name in {"TeamConfigurationError", "load_team_configuration"}:
        from . import contracts

        value = getattr(contracts, name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value
