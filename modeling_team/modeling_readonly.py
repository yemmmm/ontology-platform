"""Runner-owned read-only surface for the formal R2.3-003 Modeling role.

This module intentionally does not reuse the Acceptance ticket contract.  The Modeling
role gets one short-lived project key and a local proxy with exactly three read tools;
the proxy is the policy boundary, while :class:`ModelingContextGate` is the candidate
publication/version boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .acceptance_runtime import McpReadForwarder


MODELING_READ_TOOLS: tuple[str, ...] = (
    "get_modeling_context",
    "get_ontology_read_model",
    "query_semantic_context",
)
MODELING_READ_MODELS = frozenset({"classes", "entities", "facts", "rules"})
_QUERY_CURSOR_FIELDS = frozenset({"match_cursor", "context_cursor"})


def _canonical_default(item: Any) -> Any:
    if hasattr(item, "__dict__"):
        return item.__dict__
    raise TypeError(f"unsupported canonical value: {type(item)!r}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_default,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class ModelingReadError(RuntimeError):
    """A Modeling read or lifecycle contract failed closed."""


class ModelingContextDrift(ModelingReadError):
    """The live context no longer matches the immutable Modeling receipt."""


@dataclass(frozen=True)
class ModelingReadCallReceipt:
    ordinal: int
    tool: str
    request_digest: str
    response_digest: str


@dataclass(frozen=True)
class ModelingProxyReceipt:
    socket_identity: str
    token_digest: str
    project_id: str
    ontology_id: str
    allowed_tools: tuple[str, ...]
    policy_digest: str


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in "\x00\r\n"):
        raise ModelingReadError(f"{field} is invalid")
    return value


def _candidate_value(text: Any) -> Mapping[str, Any] | None:
    if not isinstance(text, str):
        return None
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    if not {"candidate_kind", "candidate_revision", "scope", "constraints", "items"}.issubset(value):
        return None
    return value


class ModelingReadProxy:
    """A local AF_UNIX proxy with a strict three-tool, P/O-bound policy."""

    def __init__(
        self,
        *,
        socket_path: Path,
        token: str,
        read_key: str,
        project_id: str,
        ontology_id: str,
        forward: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        on_context: Callable[[Mapping[str, Any], ModelingReadCallReceipt], object] | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.token = _id(token, "proxy token")
        self._read_key: str | None = _id(read_key, "read key")
        self.project_id = _id(project_id, "project_id")
        self.ontology_id = _id(ontology_id, "ontology_id")
        self.allowed_tools = MODELING_READ_TOOLS
        self._forward = forward
        self._on_context = on_context
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.requests: list[dict[str, Any]] = []
        self._call_receipts: list[ModelingReadCallReceipt] = []
        self._query_binding: str | None = None
        self.post_revoke_denials = 0

    @property
    def active(self) -> bool:
        with self._lock:
            return self._read_key is not None

    @property
    def token_digest(self) -> str:
        return hashlib.sha256(self.token.encode()).hexdigest()

    @property
    def receipt(self) -> ModelingProxyReceipt:
        policy = {
            "project_id": self.project_id,
            "ontology_id": self.ontology_id,
            "allowed_tools": list(self.allowed_tools),
            "models": sorted(MODELING_READ_MODELS),
            "query_scope": {"scope_mode": "ontologies", "ontology_ids": [self.ontology_id]},
        }
        return ModelingProxyReceipt(
            socket_identity="/agent/home/modeling-read-proxy.sock",
            token_digest=self.token_digest,
            project_id=self.project_id,
            ontology_id=self.ontology_id,
            allowed_tools=self.allowed_tools,
            policy_digest=canonical_digest(policy),
        )

    @property
    def receipt_snapshot(self) -> tuple[ModelingReadCallReceipt, ...]:
        with self._lock:
            return tuple(self._call_receipts)

    def _validate_arguments(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if tool == "get_modeling_context":
            if set(arguments) != {"ontology_id"} or arguments.get("ontology_id") != self.ontology_id:
                raise ModelingReadError("get_modeling_context requires exact ontology scope")
        elif tool == "get_ontology_read_model":
            allowed = {
                "ontology_id", "model_name", "include", "allow_stale_derived", "field_set",
                "limit", "entity_iri", "class_iri", "kind", "q",
            }
            if not set(arguments).issubset(allowed):
                raise ModelingReadError("ontology read-model arguments are outside the Modeling policy")
            if arguments.get("ontology_id") != self.ontology_id:
                raise ModelingReadError("ontology read-model requires exact ontology scope")
            if arguments.get("model_name") not in MODELING_READ_MODELS:
                raise ModelingReadError("ontology read-model name is outside the Modeling policy")
            if arguments.get("include", "asserted") != "asserted":
                raise ModelingReadError("ontology read-model include is invalid")
            if "allow_stale_derived" in arguments and arguments["allow_stale_derived"] is not False:
                raise ModelingReadError("ontology read-model stale policy is invalid")
            if "field_set" in arguments and arguments["field_set"] not in {"summary", "full"}:
                raise ModelingReadError("ontology read-model field_set is invalid")
            if "limit" in arguments and (
                isinstance(arguments["limit"], bool)
                or not isinstance(arguments["limit"], int)
                or arguments["limit"] <= 0
            ):
                raise ModelingReadError("ontology read-model limit is invalid")
            for field in ("entity_iri", "class_iri", "kind", "q"):
                if field in arguments and arguments[field] is not None and (
                    not isinstance(arguments[field], str) or not arguments[field]
                ):
                    raise ModelingReadError(f"ontology read-model {field} is invalid")
        elif tool == "query_semantic_context":
            allowed = {
                "project_id", "scope_mode", "query", "queries", "ontology_ids", "resource_types",
                "assertion_types", "search_mode", "depth", "limit", "context_limit",
                "match_cursor", "context_cursor", "semantic_roles", "context_detail",
            }
            if not set(arguments).issubset(allowed):
                raise ModelingReadError("semantic query arguments are outside the Modeling policy")
            if (
                arguments.get("project_id") != self.project_id
                or arguments.get("scope_mode") != "ontologies"
                or arguments.get("ontology_ids") != [self.ontology_id]
            ):
                raise ModelingReadError("semantic query requires exact Project/Ontology scope")
            for field in ("resource_types", "assertion_types", "semantic_roles"):
                if field in arguments and arguments[field] is not None and (
                    not isinstance(arguments[field], list)
                    or (field == "semantic_roles" and not arguments[field])
                    or any(not isinstance(item, str) or not item.strip() for item in arguments[field])
                ):
                    raise ModelingReadError(f"semantic query {field} is invalid")
            for field in ("depth", "limit", "context_limit"):
                if field in arguments and (
                    isinstance(arguments[field], bool)
                    or not isinstance(arguments[field], int)
                    or arguments[field] < (1 if field == "limit" else 0)
                ):
                    raise ModelingReadError(f"semantic query {field} is invalid")
            if arguments.get("context_detail", "compact") not in {"full", "compact"}:
                raise ModelingReadError("semantic query context_detail is invalid")
            if "query" not in arguments and "queries" not in arguments:
                raise ModelingReadError("semantic query requires a non-empty query")
            if "query" in arguments and (
                not isinstance(arguments["query"], str) or not arguments["query"].strip()
            ):
                raise ModelingReadError("semantic query requires a non-empty query")
            if "queries" in arguments and (
                not isinstance(arguments["queries"], list)
                or not arguments["queries"]
                or any(not isinstance(item, str) or not item.strip() for item in arguments["queries"])
            ):
                raise ModelingReadError("semantic query requires a non-empty query list")
            binding = canonical_digest(
                {key: value for key, value in arguments.items() if key not in _QUERY_CURSOR_FIELDS}
            )
            if self._query_binding is None:
                self._query_binding = binding
            elif self._query_binding != binding:
                raise ModelingReadError("semantic query cursor scope drifted")
        else:
            raise ModelingReadError("tool is outside the Modeling read allowlist")
        return dict(arguments)

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise ModelingReadError("proxy request is invalid")
        with self._lock:
            if self._read_key is None:
                self.post_revoke_denials += 1
                return {"ok": False, "code": "read-key-revoked", "error": "read-key-revoked"}
            if request.get("token") != self.token:
                return {"ok": False, "code": "proxy-token-invalid", "error": "proxy-token-invalid"}
            if request.get("operation") == "tools/list":
                return {"ok": True, "tools": list(self.allowed_tools)}
            if request.get("operation") != "tools/call":
                return {"ok": False, "code": "proxy-operation-denied", "error": "proxy-operation-denied"}
            tool = request.get("tool")
            arguments = request.get("arguments")
            if not isinstance(tool, str) or tool not in self.allowed_tools:
                return {"ok": False, "code": "read-tool-denied", "error": "read-tool-denied"}
            if not isinstance(arguments, Mapping):
                return {"ok": False, "code": "read-arguments-invalid", "error": "read-arguments-invalid"}
            try:
                normalized = self._validate_arguments(tool, arguments)
                if tool == "get_ontology_read_model":
                    # The backend's historical default is permissive.  The Modeling
                    # proxy owns the stricter contract and therefore makes the safe
                    # value explicit before forwarding an otherwise valid call.
                    normalized["allow_stale_derived"] = False
            except ModelingReadError as exc:
                return {"ok": False, "code": "read-scope-denied", "error": str(exc)}
            request_digest = canonical_digest({"tool": tool, "arguments": normalized})
            self.requests.append({"tool": tool, "request_digest": request_digest})
            if self._forward is None:
                return {"ok": False, "code": "platform-forwarding-unconfigured", "error": "platform-forwarding-unconfigured"}
            try:
                result = dict(self._forward(tool, normalized, self._read_key))
            except Exception:
                return {"ok": False, "code": "platform-forward-failed", "error": "platform-forward-failed"}
            response_digest = canonical_digest(result)
            call_receipt = ModelingReadCallReceipt(
                ordinal=len(self._call_receipts),
                tool=tool,
                request_digest=request_digest,
                response_digest=response_digest,
            )
            self._call_receipts.append(call_receipt)
            if tool == "get_modeling_context" and self._on_context is not None:
                try:
                    self._on_context(result, call_receipt)
                except Exception:
                    return {
                        "ok": False,
                        "code": "context-gate-rejected",
                        "error": "context-gate-rejected",
                    }
            return {
                "ok": True,
                "result": result,
                "request_digest": request_digest,
                "response_digest": response_digest,
                "call_receipt_digest": canonical_digest(self._call_receipts[-1].__dict__),
            }

    def start(self) -> ModelingProxyReceipt:
        with self._lock:
            if self._server is not None:
                return self.receipt
            self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if self.socket_path.exists() or self.socket_path.is_symlink():
                raise ModelingReadError("Modeling read proxy socket already exists")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(self.socket_path))
                os.chmod(self.socket_path, 0o600)
                server.listen(8)
            except Exception:
                server.close()
                self.socket_path.unlink(missing_ok=True)
                raise
            self._server = server
            self._stop.clear()
            self._thread = threading.Thread(target=self._serve, name="modeling-read-proxy", daemon=True)
            self._thread.start()
            return self.receipt

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        server.settimeout(0.2)
        while not self._stop.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                try:
                    raw = b""
                    while b"\n" not in raw and len(raw) < 128 * 1024:
                        block = connection.recv(8192)
                        if not block:
                            break
                        raw += block
                    request = json.loads(raw.split(b"\n", 1)[0].decode()) if raw else {}
                    response = self.handle(request)
                except Exception:
                    response = {"ok": False, "code": "proxy-request-invalid", "error": "proxy-request-invalid"}
                try:
                    connection.sendall(canonical_bytes(response) + b"\n")
                except OSError:
                    pass

    def revoke(self) -> dict[str, Any]:
        with self._lock:
            self._read_key = None
            return {"status": "revoked", "post_revoke_denials": self.post_revoke_denials}

    def stop(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            server.close()
        self.socket_path.unlink(missing_ok=True)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)

    def destroy(self) -> None:
        self.revoke()
        self.stop()


@dataclass(frozen=True)
class ModelingReadKeyRecord:
    key_id: str
    project_id: str
    ontology_id: str
    run_id: str
    key_digest: str
    status: str
    revoked_at: str | None = None


class ModelingReadKeyLifecycle:
    """Minimal API-backed key lifecycle independent of Acceptance ticket state."""

    def __init__(self, scope: Any, *, repository_root: Path | None = None, forwarder_factory: Any = None) -> None:
        self.scope = scope
        self.repository_root = repository_root.resolve() if repository_root else None
        self.forwarder_factory = forwarder_factory
        self._records: dict[str, ModelingReadKeyRecord] = {}
        self._plaintext: dict[str, str] = {}
        self._forwarders: dict[str, Any] = {}
        self._evidence: dict[str, dict[str, Any]] = {}

    def create(self, *, project_id: str, ontology_id: str, run_id: str) -> ModelingReadKeyRecord:
        admin = getattr(self.scope, "admin_key", None)
        request = getattr(self.scope, "request", None)
        if not isinstance(admin, str) or not admin or not callable(request):
            raise ModelingReadError("Modeling read-key admin lifecycle is unavailable")
        if getattr(self.scope, "project_id", project_id) != project_id:
            raise ModelingReadError("Modeling read key Project scope drifted")
        user_id = getattr(self.scope, "key_user_id", None)
        if not isinstance(user_id, str) or not user_id:
            raise ModelingReadError("Modeling read key requires the Team operator user binding")
        status, value = request(
            "POST", "/api/api-keys",
            {"name": f"r2-3-003-modeling-read-{run_id}", "project_id": project_id,
             "scopes": ["read"], "user_id": user_id},
            admin,
        )
        if status != 201 or not isinstance(value, Mapping):
            raise ModelingReadError("Modeling read key creation failed")
        key_id, plaintext = value.get("id"), value.get("plaintext_key")
        if not isinstance(key_id, str) or not key_id or not isinstance(plaintext, str) or not plaintext:
            raise ModelingReadError("Modeling read key creation receipt is incomplete")
        payload = {"key_id": key_id, "project_id": project_id, "ontology_id": ontology_id, "run_id": run_id, "status": "active"}
        record = ModelingReadKeyRecord(**payload, key_digest=canonical_digest(payload))
        self._records[key_id] = record
        self._plaintext[key_id] = plaintext
        self._evidence[key_id] = {"create_status": status, "key_id": key_id, "project_id": project_id, "ontology_id": ontology_id}
        return record

    def plaintext_for(self, key_id: str) -> str:
        record = self._records.get(key_id)
        if record is None or record.status != "active" or key_id not in self._plaintext:
            raise ModelingReadError("Modeling read key is revoked or unavailable")
        return self._plaintext[key_id]

    def forwarder_for(self, key_id: str) -> Callable[[str, Mapping[str, Any], str], Mapping[str, Any]]:
        record = self._records.get(key_id)
        if record is None or record.status != "active":
            raise ModelingReadError("Modeling read key is revoked or unavailable")
        forwarder = self._forwarders.get(key_id)
        if forwarder is None:
            if self.forwarder_factory is not None:
                forwarder = self.forwarder_factory(
                    repository_root=self.repository_root,
                    read_key=self.plaintext_for(key_id),
                    expected_tools=MODELING_READ_TOOLS,
                )
            else:
                if self.repository_root is None:
                    raise ModelingReadError("Modeling forwarder repository root is unavailable")
                forwarder = McpReadForwarder(
                    repository_root=self.repository_root,
                    read_key=self.plaintext_for(key_id),
                    expected_tools=MODELING_READ_TOOLS,
                )
            starter = getattr(forwarder, "start", None)
            if callable(starter):
                starter()
            self._forwarders[key_id] = forwarder
        forward = getattr(forwarder, "forward", None)
        if not callable(forward):
            raise ModelingReadError("Modeling read forwarder is invalid")
        return forward

    def revoke(self, key_id: str) -> ModelingReadKeyRecord:
        record = self._records.get(key_id)
        if record is None:
            raise ModelingReadError("Modeling read key is unknown")
        if record.status == "revoked":
            return record
        admin, request = getattr(self.scope, "admin_key", None), getattr(self.scope, "request", None)
        plaintext = self._plaintext.get(key_id)
        if not isinstance(admin, str) or not admin or not callable(request) or not plaintext:
            raise ModelingReadError("Modeling read-key revoke inputs are unavailable")
        try:
            status, value = request("POST", f"/api/api-keys/{key_id}:revoke", None, admin)
            revoked_at = value.get("revoked_at") if isinstance(value, Mapping) else None
            self._evidence[key_id].update({"revoke_status": status, "revoked_at": revoked_at})
            if status != 200 or not isinstance(revoked_at, str) or not revoked_at:
                raise ModelingReadError("Modeling read-key revoke failed")
            read_status, readback = request("GET", f"/api/api-keys/{key_id}", None, admin)
            denied_status, _ = request("GET", f"/api/projects/{record.project_id}", None, plaintext)
            self._evidence[key_id].update({"status_readback": read_status, "post_revoke_status": denied_status})
            if read_status != 200 or not isinstance(readback, Mapping) or not readback.get("revoked_at"):
                raise ModelingReadError("Modeling read-key status readback failed")
            if denied_status not in {401, 403}:
                raise ModelingReadError("post-revoke Modeling read-key denial was not proven")
            revoked = ModelingReadKeyRecord(**{**record.__dict__, "status": "revoked", "revoked_at": revoked_at})
            self._records[key_id] = revoked
            return revoked
        finally:
            forwarder = self._forwarders.pop(key_id, None)
            if forwarder is not None:
                stopper = getattr(forwarder, "stop", None)
                if callable(stopper):
                    stopper()
            # Regardless of the remote outcome, never retain the plaintext after
            # the revoke boundary.  A failed status/denial proof is surfaced as a
            # lifecycle error and the run must fail closed rather than retrying
            # with a still-resident secret.
            self._plaintext.pop(key_id, None)

    def evidence(self, key_id: str) -> dict[str, Any]:
        return dict(self._evidence.get(key_id, {}))


@dataclass(frozen=True)
class ModelingContextReceipt:
    run_id: str
    project_id: str
    ontology_id: str
    model_revision: int
    response_digest: str
    call_receipt_digest: str
    receipt_digest: str


class ModelingContextGate:
    """Immutable Modeling-first read gate and Protocol version revalidation fence."""

    def __init__(self, *, run_id: str, project_id: str, ontology_id: str) -> None:
        self.run_id, self.project_id, self.ontology_id = map(_id, (run_id, project_id, ontology_id), ("run_id", "project_id", "ontology_id"))
        self.state = "closed"
        self.receipt: ModelingContextReceipt | None = None
        self.invalidated_receipts: list[ModelingContextReceipt] = []
        self.candidate_bindings: dict[str, dict[str, str]] = {}
        self.revalidation_receipt: dict[str, str] | None = None
        self.invalidated_reason: str | None = None

    @staticmethod
    def _context(response: Mapping[str, Any]) -> Mapping[str, Any]:
        if response.get("ok") is False:
            raise ModelingReadError("get_modeling_context returned an error")
        if "data" in response:
            value = response.get("data")
        elif isinstance(response.get("result"), Mapping):
            value = response.get("result")
        else:
            value = response
        if not isinstance(value, Mapping):
            raise ModelingReadError("get_modeling_context response is invalid")
        return value

    def _validate_context(self, response: Mapping[str, Any]) -> Mapping[str, Any]:
        value = self._context(response)
        project = value.get("project")
        ontology = value.get("ontology")
        workspace = value.get("workspace")
        counts = value.get("resource_counts")
        derived = value.get("derived_state")
        if (
            not isinstance(project, Mapping) or project.get("id") != self.project_id
            or not isinstance(ontology, Mapping) or ontology.get("id") != self.ontology_id
            or not isinstance(workspace, Mapping) or workspace.get("state") != "ready"
            or type(workspace.get("model_revision")) is not int or workspace["model_revision"] < 0
            or workspace.get("issues") != []
            or not isinstance(counts, Mapping)
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counts.values())
            or not isinstance(derived, Mapping)
            or isinstance(derived.get("stale_count"), bool)
            or not isinstance(derived.get("stale_count"), int)
            or derived.get("stale_count") < 0
            or (isinstance(value.get("recovering"), Mapping) and value["recovering"].get("active") is True)
        ):
            raise ModelingReadError("get_modeling_context is not a valid current ready context")
        return value

    def observe(self, response: Mapping[str, Any], *, call_receipt: Any) -> ModelingContextReceipt:
        value = self._validate_context(response)
        version = value["workspace"]["model_revision"]
        response_digest = canonical_digest(value)
        call_digest = canonical_digest(call_receipt)
        payload = {
            "run_id": self.run_id, "project_id": self.project_id, "ontology_id": self.ontology_id,
            "model_revision": version, "response_digest": response_digest, "call_receipt_digest": call_digest,
        }
        receipt = ModelingContextReceipt(**payload, receipt_digest=canonical_digest(payload))
        if self.receipt is not None and self.state == "closed" and self.invalidated_reason:
            self.invalidated_receipts.append(self.receipt)
            self.receipt = receipt
        elif self.receipt is not None and self.receipt != receipt:
            if self.receipt.model_revision != version:
                raise ModelingReadError("Modeling context receipt is immutable")
            # A second exact-O context read at the same workspace version is a
            # revalidation, not a replacement receipt.  Retain the original
            # immutable digest and call binding.
            self.state = "context_observed"
            self.invalidated_reason = None
            return self.receipt
        else:
            self.receipt = receipt
        self.state = "context_observed"
        self.invalidated_reason = None
        return receipt

    def assert_open(self) -> ModelingContextReceipt:
        if self.state != "context_observed" or self.receipt is None:
            raise ModelingReadError("ModelingContextGate is closed")
        return self.receipt

    def bind_candidate(self, delivery_id: str, candidate_digest: str) -> dict[str, str]:
        receipt = self.assert_open()
        delivery_id, candidate_digest = _id(delivery_id, "candidate delivery_id"), _id(candidate_digest, "candidate digest")
        existing = self.candidate_bindings.get(delivery_id)
        binding = {"delivery_id": delivery_id, "candidate_digest": candidate_digest, "context_receipt_digest": receipt.receipt_digest}
        if existing is not None and existing != binding:
            raise ModelingReadError("candidate/context binding is immutable")
        self.candidate_bindings[delivery_id] = binding
        return dict(binding)

    def revalidate(self, response: Mapping[str, Any], *, call_receipt: Any) -> dict[str, str]:
        current = self._validate_context(response)
        receipt = self.assert_open()
        version = current["workspace"]["model_revision"]
        observed_digest = canonical_digest(current)
        # Workspace version is the immutable live-state fence.  Counts and other
        # read-only context details may legitimately be enriched between calls;
        # a same-version context remains the same current-state binding.  The
        # original response digest is still retained in the receipt for audit and
        # candidate binding, but is not treated as a spurious drift signal.
        if version != receipt.model_revision:
            self.state = "closed"
            self.invalidated_reason = "model_revision_or_context_drift"
            raise ModelingContextDrift(
                f"Modeling context drifted from {receipt.model_revision} to {version}"
            )
        result = {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "ontology_id": self.ontology_id,
            "model_revision": version,
            "context_receipt_digest": receipt.receipt_digest,
            "response_digest": observed_digest,
            "call_receipt_digest": canonical_digest(call_receipt),
        }
        result["revalidation_receipt_digest"] = canonical_digest(result)
        self.revalidation_receipt = dict(result)
        return result

    def invalidate(self, reason: str) -> None:
        self.state = "closed"
        self.invalidated_reason = _id(reason, "gate invalidation reason")


__all__ = [
    "MODELING_READ_TOOLS", "MODELING_READ_MODELS", "ModelingReadError", "ModelingContextDrift",
    "ModelingReadCallReceipt", "ModelingProxyReceipt", "ModelingReadProxy", "ModelingReadKeyRecord",
    "ModelingReadKeyLifecycle", "ModelingContextReceipt", "ModelingContextGate", "canonical_bytes",
    "canonical_digest", "_candidate_value",
]
