"""Explicit acceptance selection, independent of production and Delivery runtime."""

from dataclasses import replace

from ..model_routing import TeamModelProfileError, validate_runtime_model_profile


def validate_acceptance_profile(runtime, profile, *, judge=True, service_tier="unset"):
    if runtime not in {"codex", "dsh"}:
        raise TeamModelProfileError("runtime must be codex or dsh")
    if runtime == "dsh" and service_tier not in {"unset", "default"}:
        raise TeamModelProfileError("unsupported-runtime-setting: runtime=dsh field=service_tier")
    roles = ("platform-examiner", "acceptance") if judge else ("platform-examiner",)
    # Missing canonical roles cannot inherit a production or semantic-role fallback.
    missing = set(roles) - profile.bindings.keys()
    if missing:
        raise TeamModelProfileError(
            f"acceptance-model-binding-missing: {', '.join(sorted(missing))}"
        )
    validate_runtime_model_profile(
        runtime, replace(profile, bindings={r: profile.bindings[r] for r in roles})
    )


def acceptance_runtime(runtime, *, repository_root):
    if runtime == "codex":
        from .codex import CodexRuntimeAdapter

        return CodexRuntimeAdapter(repository_root=repository_root)
    if runtime == "dsh":
        from .dsh_acceptance import DshAcceptanceRuntime

        return DshAcceptanceRuntime(repository_root=repository_root)
    raise TeamModelProfileError("runtime must be codex or dsh")
