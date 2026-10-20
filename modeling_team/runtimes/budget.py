"""Small runtime-side adapter for the Host-private task budget.

The budget implementation owns persistence and policy.  Runtime code only needs
three things at this boundary: resolve the Host binding, register the runtime
member and numeric sources, and ask permission immediately before a model
request.  Keeping this adapter lazy preserves the historical runtime mode when
no budget binding exists and keeps the budget directory out of native mounts.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_BUDGET_OPERATIONS = {"read", "supervise", "production", "evaluation", "repair"}
_EVALUATION_ROLES = {
    "acceptance",
    "consumer",
    "cq",
    "examiner",
    "judge",
    "platform-examiner",
    "source-examiner",
}


def resolve_budget(root: Path, explicit: Any | None = None) -> Any | None:
    """Resolve a bound budget without making the runtime depend on its storage.

    ``task_budget`` is imported lazily so unbound focused runtime fixtures keep
    the normal ``budget_for(root) is None`` path.  Errors from the current
    budget core are allowed to surface instead of being mistaken for an
    unbudgeted run.
    """

    if explicit is not None:
        return explicit
    from ..task_budget import budget_for
    return budget_for(Path(root))


def binding_projection(binding: Any) -> dict[str, Any]:
    """Return the non-secret model binding accepted by the budget API."""

    if binding is None:
        return {}
    as_dict = getattr(binding, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
        projected = dict(value) if isinstance(value, Mapping) else {}
    elif isinstance(binding, Mapping):
        projected = dict(binding)
    else:
        projected = {}
        for name in ("provider_id", "provider", "model", "requested_model", "requested_effort", "effective_effort", "key_ref"):
            value = getattr(binding, name, None)
            if value is not None:
                projected[name] = value
    provider = projected.get("provider") or projected.get("provider_id") or projected.get("model_provider")
    model = projected.get("actual_model") or projected.get("model") or projected.get("requested_model")
    if provider is not None:
        projected.setdefault("provider", provider)
    if model is not None:
        projected.setdefault("actual_model", model)
        projected.setdefault("requested_model", model)
    return projected


def valid_key_ref(value: Any) -> str | None:
    """Keep only a non-secret credential binding alias from a Host contract."""

    return value if isinstance(value, str) and value else None


def binding_with_key_ref(binding: Any, key_ref: Any = None) -> dict[str, Any]:
    """Project a model binding and attach an already-validated credential alias."""

    projected = binding_projection(binding)
    alias = valid_key_ref(key_ref)
    if alias is not None:
        projected["key_ref"] = alias
    return projected


def budget_operation(
    binding: Any = None,
    *,
    runtime: str | None = None,
    default: str | None = None,
) -> str:
    """Project a runtime request onto the TaskBudget operation vocabulary."""

    projected = binding_projection(binding)
    declared = projected.get("operation") or projected.get("budget_operation")
    if declared in _BUDGET_OPERATIONS:
        return declared
    role = str(projected.get("role") or projected.get("semantic_role") or "").lower()
    if role == "delivery" or runtime in {"delivery", "dsh_delivery"}:
        return "supervise"
    if role in _EVALUATION_ROLES or role.endswith("-examiner"):
        return "evaluation"
    if default in _BUDGET_OPERATIONS:
        return default
    return "production"


def normalize_control_epoch(value: Any) -> int:
    """Accept the wire integer form (and a decimal compatibility form)."""

    if isinstance(value, bool):
        raise ValueError("control epoch must be a non-negative integer")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    raise ValueError("control epoch must be a non-negative integer")


def source_identity(owner_id: str, path: Path, kind: str) -> str:
    """Build a stable, opaque source id from the Host path and source kind."""

    digest = hashlib.sha256(f"{Path(path).resolve()}\0{kind}".encode()).hexdigest()[:24]
    return f"{owner_id}:{kind}:{digest}"


def shared_source_identity(path: Path, kind: str) -> str:
    """Build one stable source id for a file shared by several members."""

    return source_identity("shared", path, kind)


def ensure_source_file(path: Path) -> None:
    """Create an owned empty receipt file once, without repairing deletion."""

    source_path = Path(path).resolve()
    source_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(source_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


@dataclass
class RuntimeBudget:
    """Runtime-local view of one bound TaskBudget."""

    root: Path
    owner_id: str
    budget: Any | None = None
    binding: Any | None = None
    runtime: str | None = None
    operation: str = "production"

    def bind(self, **metadata: Any) -> None:
        if self.budget is None:
            return
        self.budget.bind_owner(
            self.owner_id,
            runtime=self.runtime,
            **{key: value for key, value in metadata.items() if value is not None},
        )

    def register_source(
        self,
        path: Path,
        kind: str,
        *,
        source_id: str | None = None,
        **metadata: Any,
    ) -> None:
        if self.budget is None:
            return
        source_path = Path(path).resolve()
        if source_id is None:
            source_id = (
                shared_source_identity(source_path, kind)
                if metadata.get("shared")
                else source_identity(self.owner_id, source_path, kind)
            )
        current = self.budget.show("host")
        if source_id not in (current.get("sources") or {}):
            # Register a live empty append-only source before the first model
            # request.  A later missing file remains observable as a source
            # error because re-registration does not recreate it.
            ensure_source_file(source_path)
        self.budget.register_source(
            source_id,
            str(source_path),
            kind,
            # A shared append-only source contains rows from several native
            # members.  Its rows carry their own provider/model/session
            # identity; a member binding here would make every other row look
            # conflicting after the next member registers the same file.
            binding={} if metadata.get("shared") else binding_projection(self.binding),
            owner_id=self.owner_id,
            runtime=self.runtime,
            **{key: value for key, value in metadata.items() if value is not None},
        )

    def require(self, operation: str, *, control_id: str | None = None) -> Any:
        """Require budget availability immediately before one real request.

        ``BudgetError`` is intentionally preserved.  The outer Runner/Delivery
        boundary can classify it as a recoverable budget pause without turning a
        normal exhausted budget into runtime cleanup failure.
        """

        if self.budget is None:
            return None
        # A control turn is a bounded host instruction.  It is deliberately
        # outside the normal role operation allow-list; the core uses the
        # control id to apply its limited-control policy.
        requested_operation = None if operation == "control" else self.operation or operation
        selector = binding_projection(self.binding) or None
        return self.budget.require_available(
            operation=requested_operation,
            binding=selector,
            control_id=control_id,
        )

    def control_receipt(self, epoch: Any) -> dict[str, Any] | None:
        """Read this member's durable control receipt for restart recovery."""

        if self.budget is None:
            return None
        try:
            current_epoch = normalize_control_epoch(epoch)
            state = self.budget.show("host")
        except Exception:
            return None
        owner = (state.get("owners") or {}).get(self.owner_id, {})
        receipt = (owner.get("control") or {}).get(str(current_epoch))
        return dict(receipt) if isinstance(receipt, Mapping) else None

    def record_control(self, epoch: Any, status: str, **metadata: Any) -> None:
        if self.budget is None:
            return
        self.budget.record_control(
            self.owner_id,
            normalize_control_epoch(epoch),
            status,
            runtime=self.runtime,
            **{key: value for key, value in metadata.items() if value is not None},
        )


def runtime_budget(
    root: Path,
    owner_id: str,
    *,
    binding: Any | None = None,
    runtime: str | None = None,
    explicit: Any | None = None,
    operation: str | None = None,
    **metadata: Any,
) -> RuntimeBudget:
    """Construct and bind one runtime member to the Host budget, if present."""

    operation_binding = binding_projection(binding)
    if metadata.get("role") and "role" not in operation_binding:
        operation_binding["role"] = metadata["role"]
    value = RuntimeBudget(
        Path(root).resolve(),
        owner_id,
        resolve_budget(Path(root), explicit),
        operation_binding,
        runtime,
        budget_operation(operation_binding, runtime=runtime, default=operation),
    )
    value.bind(**metadata)
    return value


__all__ = [
    "RuntimeBudget",
    "budget_operation",
    "binding_projection",
    "binding_with_key_ref",
    "normalize_control_epoch",
    "resolve_budget",
    "runtime_budget",
    "valid_key_ref",
    "ensure_source_file",
    "shared_source_identity",
    "source_identity",
]
