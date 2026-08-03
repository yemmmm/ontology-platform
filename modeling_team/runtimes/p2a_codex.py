"""P2a-only Codex adapter overlay without changing the normal Adapter surface."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

from ..contracts import digest_file
from ..p2a_batch_plan import (
    P2ABatchPlanError,
    P2A_TASK_ID,
    materialize_overlay_contract,
    validate_overlay_contract,
)
from ..proof_v2 import V2_PROOF_FIELDS
from .codex import CodexRuntimeAdapter, CodexRuntimeError


OVERLAY_CONTRACT_RELATIVE = Path("modeling_team/references/p2a-overlay-contract.json")
OVERLAY_SERVER_NAME = "p2a_protocol_overlay"
OVERLAY_TOOL_ORDER = (
    "build_p2a_batch_plan",
    "verify_p2a_dry_run_evidence_projection",
)
OVERLAY_TOOLS = frozenset(OVERLAY_TOOL_ORDER)
NATIVE_VERIFIER_MAX_CALLS = 3
_OVERLAY_ELICITATION_PARAM_KEYS = frozenset(
    {
        "_meta",
        "message",
        "mode",
        "requestedSchema",
        "serverName",
        "threadId",
        "turnId",
    }
)
_PROOF_V2_TOP_LEVEL_TYPES = {
    "mode": str,
    "initial_modeling_context": dict,
    "final_modeling_context": dict,
    "workspace_context": dict,
    "batch_inventory": dict,
    "batch_details": list,
    "entities_read": dict,
    "statements_read": dict,
    "candidate_required_assertions": dict,
    "term_bindings": list,
    "materialized_quads": list,
    "materialized_digest": str,
    "evidence_bindings": list,
    "statement_lineage": (dict, list),
    "pagination": dict,
}


class P2ACodexRuntimeAdapter(CodexRuntimeAdapter):
    """Add one immutable MCP server only for the exact P2a production task."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._overlay_paths: dict[str, tuple[Path, Path, Path]] = {}
        self._overlay_contracts: dict[str, dict[str, Any]] = {}
        self._overlay_fds: dict[str, tuple[int, ...]] = {}
        self._overlay_preflight_agents: set[str] = set()

    @staticmethod
    def _require_p2a_identity(run: Any, agent: Any) -> str:
        task = getattr(getattr(run, "configuration", None), "task", None)
        run_id = getattr(run, "run_id", None)
        if (
            getattr(task, "task_id", None) != P2A_TASK_ID
            or getattr(task, "schema_version", None) != 2
            or agent.package.role != "protocol"
            or not isinstance(run_id, str)
            or not run_id
        ):
            raise CodexRuntimeError("P2a overlay task/run/role identity is invalid")
        return run_id

    def _stage_protocol_retrieval_mcp(self, run: Any, agent: Any) -> None:
        super()._stage_protocol_retrieval_mcp(run, agent)
        run_id = self._require_p2a_identity(run, agent)
        template_path = self.root / OVERLAY_CONTRACT_RELATIVE
        try:
            template_metadata = os.lstat(template_path)
            template = json.loads(template_path.read_text(encoding="utf-8"))
            validate_overlay_contract(
                template,
                expected_run_id="$P2A_RUNTIME_RUN_ID",
            )
        except (OSError, json.JSONDecodeError, P2ABatchPlanError, TypeError) as exc:
            raise CodexRuntimeError("P2a overlay template is invalid") from exc
        if stat.S_ISLNK(template_metadata.st_mode) or not stat.S_ISREG(
            template_metadata.st_mode
        ):
            raise CodexRuntimeError("P2a overlay template metadata is invalid")
        assets = run.root / "runtime-assets" / "p2a-overlay"
        try:
            assets.mkdir(parents=True, mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise CodexRuntimeError("P2a overlay assets already exist") from exc
        os.chmod(assets, 0o700)
        staged_by_mount: dict[str, Path] = {}
        for spec in template["assets"]:
            source = self.root / spec["source_path"]
            if spec["mount_path"] == "/opt/proof_v2.py":
                if agent.proof_v2_path is None or digest_file(source) != spec["sha256"]:
                    raise CodexRuntimeError("P2a overlay proof_v2 asset drifts")
                continue
            try:
                metadata = os.lstat(source)
            except OSError as exc:
                raise CodexRuntimeError("P2a overlay source asset is unavailable") from exc
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or digest_file(source) != spec["sha256"]
                or spec["mode"] != "0444"
            ):
                raise CodexRuntimeError("P2a overlay source asset drifts")
            target = assets / Path(spec["mount_path"]).name
            self._write_immutable(target, source.read_bytes(), 0o444)
            staged_by_mount[spec["mount_path"]] = target
        materialized = materialize_overlay_contract(template, run_id)
        contract_path = assets / "p2a-overlay-contract.json"
        self._write_immutable(
            contract_path,
            json.dumps(
                materialized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            0o444,
        )
        try:
            paths = (
                staged_by_mount["/opt/p2a_batch_plan.py"],
                staged_by_mount["/opt/p2a_protocol_overlay_mcp.py"],
                contract_path,
            )
        except KeyError as exc:
            raise CodexRuntimeError("P2a overlay staged asset set drifts") from exc
        self._overlay_paths[agent.agent_id] = paths
        self._overlay_contracts[agent.agent_id] = materialized

    @staticmethod
    def _write_immutable(path: Path, payload: bytes, mode: int) -> None:
        descriptor = -1
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode,
            )
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
            os.fchmod(descriptor, mode)
        except OSError as exc:
            raise CodexRuntimeError("P2a overlay immutable asset write failed") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _write_config(self, run: Any, agent: Any) -> None:
        run_id = self._require_p2a_identity(run, agent)
        super()._write_config(run, agent)
        contract = self._overlay_contracts.get(agent.agent_id)
        if contract is None or contract.get("run_id") != run_id:
            raise CodexRuntimeError("P2a overlay materialized contract is unavailable")
        config = agent.home / "config.toml"
        lines = [
            "[mcp_servers.p2a_protocol_overlay]",
            'command = "/usr/bin/python3"',
            'args = ["/opt/p2a_protocol_overlay_mcp.py"]',
            "required = true",
            "[mcp_servers.p2a_protocol_overlay.env]",
            f'P2A_RUNTIME_RUN_ID = {json.dumps(run_id)}',
            f'P2A_RUNTIME_TASK_ID = {json.dumps(P2A_TASK_ID)}',
            "P2A_OVERLAY_CONTRACT_DIGEST = "
            + json.dumps(contract["contract_digest"]),
        ]
        config.write_text(
            config.read_text(encoding="utf-8") + "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        os.chmod(config, 0o600)

    def namespace_command(self, agent: Any) -> list[str]:
        command = super().namespace_command(agent)
        paths = self._overlay_paths.get(agent.agent_id)
        if paths is None:
            raise CodexRuntimeError("P2a overlay paths are unavailable")
        descriptors = self._open_overlay_assets(agent, paths)
        agent.retrieval_asset_fds = agent.retrieval_asset_fds + descriptors
        insertion = command.index("--chdir")
        command[insertion:insertion] = [
            "--dir",
            "/opt",
            "--ro-bind",
            f"/proc/self/fd/{descriptors[0]}",
            "/opt/p2a_batch_plan.py",
            "--ro-bind",
            f"/proc/self/fd/{descriptors[1]}",
            "/opt/p2a_protocol_overlay_mcp.py",
            "--ro-bind",
            f"/proc/self/fd/{descriptors[2]}",
            "/opt/p2a-overlay-contract.json",
        ]
        return command

    def _open_overlay_assets(
        self,
        agent: Any,
        paths: tuple[Path, Path, Path],
    ) -> tuple[int, ...]:
        retained = self._overlay_fds.get(agent.agent_id)
        if retained:
            return retained
        if self._run_root is None:
            raise CodexRuntimeError("P2a overlay run root is unavailable")
        expected_root = self._run_root / "runtime-assets" / "p2a-overlay"
        if self.agents.get(agent.agent_id) is not agent or any(
            path.parent != expected_root for path in paths
        ):
            raise CodexRuntimeError("P2a overlay Agent/path identity is invalid")
        descriptors: list[int] = []
        try:
            for path in paths:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o444
                    or metadata.st_uid != os.getuid()
                ):
                    os.close(descriptor)
                    raise CodexRuntimeError("P2a overlay asset metadata is invalid")
                os.lseek(descriptor, 0, os.SEEK_SET)
                descriptors.append(descriptor)
            retained = tuple(descriptors)
            self._overlay_fds[agent.agent_id] = retained
            return retained
        except Exception:
            for descriptor in descriptors:
                os.close(descriptor)
            raise

    def _start_process(self, agent: Any) -> subprocess.Popen[str]:
        try:
            command = self.namespace_command(agent)
            descriptors = agent.retrieval_asset_fds
            return self.process_factory(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
                pass_fds=descriptors,
            )
        finally:
            self._close_retrieval_asset_fds(agent)

    def _require_expected_mcp_servers(self, agent: Any) -> None:
        """Retain the normal exact three-server contract and add one exact overlay."""
        self._overlay_preflight_agents.discard(agent.agent_id)
        normal_expected = {
            "team_transport": {"send_team_message", "report_task_result"},
            "ontology_platform": set(agent.platform_tools),
            "protocol_mechanics": {
                "build_candidate_receipt",
                "verify_scoped_retrieval_fallback",
                "write_candidate_item_evidence_map",
            },
        }
        overlay_expected = {OVERLAY_SERVER_NAME: OVERLAY_TOOLS}
        expected = {**normal_expected, **overlay_expected}
        deadline = time.monotonic() + 25
        observed: dict[str, set[str]] = {}
        while time.monotonic() < deadline:
            result = self._rpc(agent, "mcpServerStatus/list", {"detail": "full"})
            data = result.get("data", []) if isinstance(result, dict) else []
            servers = {
                str(item.get("name")): item
                for item in data
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            observed = {
                name: self._mcp_tool_names(item.get("tools", []))
                for name, item in servers.items()
            }
            normal_observed = {
                name: tools for name, tools in observed.items() if name in normal_expected
            }
            overlay_observed = {
                name: tools for name, tools in observed.items() if name in overlay_expected
            }
            if (
                normal_observed == normal_expected
                and overlay_observed == overlay_expected
                and set(observed) == set(expected)
            ):
                self._overlay_preflight_agents.add(agent.agent_id)
                return
            time.sleep(0.25)
        actual = {name: sorted(tools) for name, tools in observed.items()}
        raise CodexRuntimeError(
            f"P2a MCP preflight failed for {agent.agent_id}: "
            f"expected {sorted(expected)}, got {actual}"
        )

    def _notification(self, agent: Any, value: dict[str, Any]) -> None:
        """Accept only the exact Host-generated approval for the frozen P2a overlay."""
        if self._record_failed_native_verifier(agent, value):
            return
        params = value.get("params")
        if self._native_verifier_elicitation_is_exact(agent, value, params):
            native_call_count = getattr(agent, "p2a_native_call_count", 0)
            if isinstance(native_call_count, bool) or not isinstance(native_call_count, int):
                native_call_count = NATIVE_VERIFIER_MAX_CALLS
            accepted = native_call_count < NATIVE_VERIFIER_MAX_CALLS
            if accepted:
                native_call_count += 1
                agent.p2a_native_call_count = native_call_count
            action = "accept" if accepted else "decline"
            self._append_runtime_evidence(
                "mcp-elicitations",
                {
                    "agent_id": agent.agent_id,
                    "server_name": "protocol_mechanics",
                    "mode": "form",
                    "schema_keys": sorted(params["requestedSchema"]),
                    "action": action,
                },
            )
            self._append_runtime_evidence(
                "native-verifier-attempt-events",
                {
                    "event": "native_verifier_approval",
                    "native_call_count": native_call_count,
                    "action": action,
                    "created_at_ns": time.time_ns(),
                },
            )
            self._respond_server_request(
                agent,
                value["id"],
                {"action": action, "content": {}},
            )
            return
        tool_name = self._overlay_elicitation_tool(agent, value, params)
        if tool_name is None:
            super()._notification(agent, value)
            return
        schema = params["requestedSchema"]
        self._append_runtime_evidence(
            "app-server-events",
            {
                "agent_id": agent.agent_id,
                "method": value["method"],
                "has_request_id": True,
                "param_keys": sorted(params),
            },
        )
        self._append_runtime_evidence(
            "mcp-elicitations",
            {
                "agent_id": agent.agent_id,
                "server_name": OVERLAY_SERVER_NAME,
                "mode": "form",
                "schema_keys": sorted(schema),
                "action": "accept",
            },
        )
        self._respond_server_request(
            agent,
            value["id"],
            {"action": "accept", "content": {}},
        )

    def _native_verifier_elicitation_is_exact(
        self,
        agent: Any,
        value: dict[str, Any],
        params: Any,
    ) -> bool:
        if (
            value.get("method") != "mcpServer/elicitation/request"
            or "id" not in value
            or not isinstance(params, dict)
            or set(params) != _OVERLAY_ELICITATION_PARAM_KEYS
            or params.get("serverName") != "protocol_mechanics"
            or params.get("mode") != "form"
            or params.get("requestedSchema") != {"type": "object", "properties": {}}
            or params.get("threadId") != agent.thread_id
            or not isinstance(agent.active_turn_id, str)
            or not agent.active_turn_id
            or params.get("turnId") != agent.active_turn_id
            or params.get("message")
            != 'Allow the protocol_mechanics MCP server to run tool '
            '"verify_scoped_retrieval_fallback"?'
        ):
            return False
        meta = params.get("_meta")
        return (
            isinstance(meta, dict)
            and meta.get("codex_approval_kind") == "mcp_tool_call"
            and meta.get("tool_name", "verify_scoped_retrieval_fallback")
            == "verify_scoped_retrieval_fallback"
            and self._overlay_context_is_valid(agent)
        )

    def _record_failed_native_verifier(
        self,
        agent: Any,
        value: dict[str, Any],
    ) -> bool:
        """Retain only safe failure classification for the exact P2a native verifier."""
        if value.get("method") != "item/completed":
            return False
        params = value.get("params")
        item = params.get("item") if isinstance(params, dict) else None
        if (
            not isinstance(item, dict)
            or item.get("type") != "mcpToolCall"
            or item.get("server") != "protocol_mechanics"
            or item.get("tool") != "verify_scoped_retrieval_fallback"
            or item.get("status") != "failed"
            or not self._overlay_context_is_valid(agent)
        ):
            return False
        item_id = item.get("id")
        completed_ids = getattr(agent, "completed_mcp_item_ids", None)
        if not isinstance(item_id, str) or not item_id or not isinstance(completed_ids, set):
            return False
        if item_id in completed_ids:
            return True
        completed_ids.add(item_id)
        arguments = item.get("arguments")
        top_level_exact = isinstance(arguments, dict) and set(arguments) == V2_PROOF_FIELDS
        types_valid = top_level_exact and all(
            isinstance(arguments[name], expected)
            for name, expected in _PROOF_V2_TOP_LEVEL_TYPES.items()
        )
        mode_create = isinstance(arguments, dict) and arguments.get("mode") == "create"
        error = item.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        if not isinstance(message, str):
            message = ""
        message_code = re.search(r"Mcp error:\s*(-\d{5})(?!\d)", message)
        if isinstance(code, int) and not isinstance(code, bool):
            error_code = code
        elif message_code is not None:
            error_code = int(message_code.group(1))
        else:
            error_code = -1
        failure_layer = {
            -32602: "argument_contract",
            -32010: "proof_validation",
        }.get(error_code, "transport")
        self._append_runtime_evidence(
            "app-server-events",
            {
                "agent_id": agent.agent_id,
                "method": value["method"],
                "has_request_id": "id" in value,
                "param_keys": sorted(params),
            },
        )
        self._append_runtime_evidence(
            "native-verifier-events",
            {
                "error_code": error_code,
                "failure_layer": failure_layer,
                "error_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
                "top_level_exact": top_level_exact,
                "types_valid": types_valid,
                "mode_create": mode_create,
            },
        )
        return True

    def _overlay_elicitation_tool(
        self,
        agent: Any,
        value: dict[str, Any],
        params: Any,
    ) -> str | None:
        if (
            value.get("method") != "mcpServer/elicitation/request"
            or "id" not in value
            or not isinstance(params, dict)
            or set(params) != _OVERLAY_ELICITATION_PARAM_KEYS
            or params.get("serverName") != OVERLAY_SERVER_NAME
            or params.get("mode") != "form"
            or params.get("requestedSchema") != {"type": "object", "properties": {}}
            or params.get("threadId") != agent.thread_id
            or not isinstance(agent.active_turn_id, str)
            or not agent.active_turn_id
            or params.get("turnId") != agent.active_turn_id
        ):
            return None
        meta = params.get("_meta")
        if not isinstance(meta, dict) or meta.get("codex_approval_kind") != "mcp_tool_call":
            return None
        message = params.get("message")
        tool_name = next(
            (
                name
                for name in OVERLAY_TOOL_ORDER
                if message
                == f'Allow the {OVERLAY_SERVER_NAME} MCP server to run tool "{name}"?'
            ),
            None,
        )
        if tool_name is None or meta.get("tool_name", tool_name) != tool_name:
            return None
        return tool_name if self._overlay_context_is_valid(agent) else None

    def _overlay_context_is_valid(self, agent: Any) -> bool:
        run_id = self._run_id
        paths = self._overlay_paths.get(agent.agent_id)
        stored_contract = self._overlay_contracts.get(agent.agent_id)
        if (
            not isinstance(run_id, str)
            or not run_id
            or self._run_root is None
            or self.agents.get(agent.agent_id) is not agent
            or agent.package.role != "protocol"
            or agent.schema_version != 2
            or agent.agent_id not in self._overlay_preflight_agents
            or paths is None
            or stored_contract is None
        ):
            return False
        contract_path = paths[-1]
        expected_path = (
            self._run_root
            / "runtime-assets"
            / "p2a-overlay"
            / "p2a-overlay-contract.json"
        )
        try:
            metadata = os.lstat(contract_path)
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            validate_overlay_contract(
                contract,
                expected_run_id=run_id,
                expected_task_id=P2A_TASK_ID,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, P2ABatchPlanError, TypeError):
            return False
        return (
            contract_path == expected_path
            and not stat.S_ISLNK(metadata.st_mode)
            and stat.S_ISREG(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == 0o444
            and metadata.st_uid == os.getuid()
            and contract == stored_contract
            and contract.get("server_name") == OVERLAY_SERVER_NAME
            and contract.get("tools") == list(OVERLAY_TOOL_ORDER)
            and frozenset(contract["tools"]) == OVERLAY_TOOLS
        )

    def _close_overlay_asset_fds(self, agent_id: str) -> None:
        for descriptor in self._overlay_fds.pop(agent_id, ()):
            try:
                os.close(descriptor)
            except OSError:
                pass

    def _close_retrieval_asset_fds(self, agent: Any) -> None:
        CodexRuntimeAdapter._close_retrieval_asset_fds(agent)
        self._overlay_fds.pop(agent.agent_id, None)
