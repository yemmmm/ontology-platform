"""P0: inspect the real SDK/runtime without starting a model turn.

The child process has no network, host home, repository, or credentials. This
establishes a reproducible candidate environment, not a V1--V8 acceptance result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml
from codex_cli_bin import bundled_codex_path
from openai_codex import CodexConfig
from openai_codex.client import CodexClient
from openai_codex.generated.v2_all import (
    ConfigReadResponse,
    ExperimentalFeatureListResponse,
    ListMcpServerStatusResponse,
    SkillsListResponse,
)

# Reuse the existing Delivery boundary's per-capability approach. There is no
# top-level default_tools_enabled switch. Actual outbound tools still need V2.
DISABLED_FEATURES = (
    "shell_tool",
    "sleep_tool",
    "view_image",
    "goals",
    "multi_agent",
    "multi_agent_v2",
    "apps",
    "plugins",
    "browser_use",
    "computer_use",
    "image_generation",
    "memories",
    "hooks",
    "skill_search",
    "tool_suggest",
)


@dataclass(frozen=True)
class ModelBinding:
    provider: str
    model: str
    effort: str

    @classmethod
    def from_profile(cls, path: Path, role: str) -> ModelBinding:
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
        selected = profile["roles"][role]
        values = [selected[key] for key in ("model_provider", "model", "model_reasoning_effort")]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("provider, model and effort must be explicit nonempty strings")
        return cls(*values)


def candidate_config(binding: ModelBinding) -> str:
    """Use a deliberately unreachable route; preflight cannot perform inference."""
    quote = json.dumps
    lines = [
        f"model = {quote(binding.model)}",
        f"model_provider = {quote(binding.provider)}",
        f"model_reasoning_effort = {quote(binding.effort)}",
        'approval_policy = "never"',
        'sandbox_mode = "read-only"',
        'web_search = "disabled"',
        "project_doc_max_bytes = 0",
        "[features]",
        *(f"{name} = false" for name in DISABLED_FEATURES),
        "[tools.experimental_request_user_input]",
        "enabled = false",
        "[tools.update_plan]",
        "enabled = false",
        f"[model_providers.{quote(binding.provider)}]",
        f"name = {quote(binding.provider)}",
        'base_url = "http://127.0.0.1:9/v1"',
        'wire_api = "responses"',
        "requires_openai_auth = false",
        'remote_compaction = "unsupported"',
    ]
    return "\n".join(lines) + "\n"


def namespace_command(home: Path, work: Path) -> list[str]:
    """The existing Linux isolation layout, with network also off for preflight.

    No import from modeling_team: its __init__ eagerly loads the old Runner.
    SDK transport and parsing remain owned by the SDK, outside this namespace.
    """
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise RuntimeError("P0 preflight requires bubblewrap for host-input isolation")
    command = [
        bwrap,
        "--die-with-parent",
        "--unshare-pid",
        "--unshare-net",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--clearenv",
        "--setenv",
        "PATH",
        "/agent/bin:/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/agent/home",
        "--setenv",
        "CODEX_HOME",
        "/agent/home",
    ]
    for source in (
        "/usr",
        "/bin",
        "/lib",
        "/lib64",
        "/etc/ld.so.cache",
        "/etc/ssl/certs",
    ):
        if Path(source).exists():
            command.extend(("--ro-bind", source, source))
    command.extend(
        (
            "--ro-bind",
            str(bundled_codex_path().parent),
            "/agent/bin",
            "--bind",
            str(home.resolve()),
            "/agent/home",
            "--bind",
            str(work.resolve()),
            "/agent/work",
            "--chdir",
            "/agent/work",
            "--",
        )
    )
    return command


def inspect_runtime(output_dir: Path, binding: ModelBinding) -> dict[str, Any]:
    """Create a fresh evidence directory and only use non-inference RPCs."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    home, work = output_dir / "codex-home", output_dir / "work"
    home.mkdir(mode=0o700)
    work.mkdir(mode=0o700)
    config_text = candidate_config(binding)
    (home / "config.toml").write_text(config_text, encoding="utf-8")
    command = namespace_command(home, work)
    cli_version = subprocess.run(
        [*command, "/agent/bin/codex", "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()
    config = CodexConfig(
        launch_args_override=(*command, "/agent/bin/codex", "app-server", "--listen", "stdio://"),
        cwd=str(work),
        client_name="ontoweave_v5_preflight",
        experimental_api=False,
    )
    with CodexClient(config) as client:
        initialized = client.initialize()
        effective = client.request(
            "config/read",
            {"cwd": "/agent/work", "includeLayers": True},
            response_model=ConfigReadResponse,
        )
        thread = client.thread_start(
            {
                "cwd": "/agent/work",
                "model": binding.model,
                "modelProvider": binding.provider,
                "baseInstructions": "",
                "developerInstructions": "P0 configuration inspection. Do not start inference.",
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "ephemeral": True,
            }
        )
        features = client.request(
            "experimentalFeature/list",
            {"threadId": thread.thread.id, "limit": 100},
            response_model=ExperimentalFeatureListResponse,
        )
        while features.next_cursor is not None:
            page = client.request(
                "experimentalFeature/list",
                {"threadId": thread.thread.id, "limit": 100, "cursor": features.next_cursor},
                response_model=ExperimentalFeatureListResponse,
            )
            features.data.extend(page.data)
            features.next_cursor = page.next_cursor
        skills = client.request(
            "skills/list",
            {"cwds": ["/agent/work"], "forceReload": True},
            response_model=SkillsListResponse,
        )
        mcp = client.request(
            "mcpServerStatus/list",
            {"limit": 100},
            response_model=ListMcpServerStatusResponse,
        )
    with bundled_codex_path().open("rb") as runtime_binary:
        runtime_sha256 = hashlib.file_digest(runtime_binary, "sha256").hexdigest()
    evidence = {
        "schema": "ontoweave-v5-preflight/v1",
        "scope": "non-inference SDK/runtime inspection; V1--V8 remain unverified",
        "python": sys.version.split()[0],
        "sdk": version("openai-codex"),
        "runtime_package": version("openai-codex-cli-bin"),
        "runtime_binary": str(bundled_codex_path()),
        "runtime_sha256": runtime_sha256,
        "cli_version": cli_version,
        "requested_binding": asdict(binding),
        "config_sha256": hashlib.sha256(config_text.encode()).hexdigest(),
        "network": "disabled by OS namespace",
        "rpc_methods": [
            "initialize",
            "config/read",
            "thread/start",
            "experimentalFeature/list",
            "skills/list",
            "mcpServerStatus/list",
        ],
        "initialize": initialized.model_dump(mode="json", by_alias=True),
        "config": effective.model_dump(mode="json", by_alias=True),
        "thread": thread.model_dump(mode="json", by_alias=True),
        "features": features.model_dump(mode="json", by_alias=True),
        "skills": skills.model_dump(mode="json", by_alias=True),
        "mcp": mcp.model_dump(mode="json", by_alias=True),
    }
    (output_dir / "preflight.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-profile", type=Path, required=True)
    parser.add_argument("--role", default="modeling")
    args = parser.parse_args()
    binding = ModelBinding.from_profile(args.model_profile, args.role)
    result = inspect_runtime(args.output_dir, binding)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "scope",
                    "python",
                    "sdk",
                    "runtime_package",
                    "cli_version",
                    "requested_binding",
                    "network",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
