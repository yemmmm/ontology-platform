"""Stage one author's professional body without applying or accepting its meaning."""

from __future__ import annotations

from copy import deepcopy

from jsonschema import ValidationError, validate

from .contracts import FrameworkError, digest
from .role_team import REF, result_schema


def _receipt(binding, context, reference):
    return {
        "actor_id": binding.actor,
        "generation": binding.data.get("work_generation", 0),
        **context,
        "artifact_ref": reference,
    }


def _receipt_id(binding, context, reference):
    return binding.identity + ":role-submission:" + digest([context["execution_id"], reference])


def submit_role_artifact(binding, repository, context, artifact=None, *, artifact_ref=None):
    """Validate structure now so the same native turn can correct it."""
    if (artifact is None) == (artifact_ref is None):
        raise FrameworkError("supply_artifact_or_own_reference")
    if artifact_ref is not None:
        try:
            validate(artifact_ref, REF)
        except ValidationError as error:
            raise FrameworkError(
                "role_artifact_ref_invalid",
                path=list(error.absolute_path),
                message=error.message[:600],
            ) from None
        row = repository.get(artifact_ref["object_id"], artifact_ref["revision"])
        if (
            not artifact_ref["object_id"].startswith(binding.identity + ":role-artifact:")
            or not row
            or row["kind"] != "role_artifact"
        ):
            raise FrameworkError("role_artifact_not_owned")
        artifact = repository.read_reference(artifact_ref)
    artifact = deepcopy(artifact)
    try:
        validate(
            artifact,
            result_schema(binding, context["phase"])["properties"]["artifact"]["anyOf"][0],
        )
    except ValidationError as error:
        raise FrameworkError(
            "role_artifact_invalid", path=list(error.absolute_path), message=error.message[:600]
        ) from None
    if binding.role == "modeling" and context["phase"] != "source_intake":
        from .role_candidates import normalize_model_candidate

        try:
            artifact["candidate"] = normalize_model_candidate(artifact["candidate"])
        except ImportError as error:
            raise FrameworkError(
                "candidate_validator_unavailable",
                layer="runtime/infrastructure",
                dependency=error.name,
            ) from None
    reference = repository.put_reference(
        binding.identity + ":role-artifact:" + digest(artifact), "role_artifact", artifact, 0
    )
    repository.put_reference(
        _receipt_id(binding, context, reference),
        "role_submission",
        _receipt(binding, context, reference),
        0,
    )
    return {"status": "staged", "artifact_ref": reference}


def read_submitted_artifact(binding, repository, context, reference):
    """A returned reference is usable only with this author's actual submission receipt."""
    row = repository.get(_receipt_id(binding, context, reference))
    if not row or row["kind"] != "role_submission":
        raise FrameworkError("role_submission_missing")
    if row["content"] != _receipt(binding, context, reference):
        raise FrameworkError("role_submission_basis_changed")
    return repository.read_reference(reference)
