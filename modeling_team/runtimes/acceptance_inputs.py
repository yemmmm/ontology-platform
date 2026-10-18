"""Shared v3 packet transport; native runtime identity stays outside the packet."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from ..acceptance_runtime import (
    CQ_ACCEPTANCE_PLATFORM_ROLE,
    _unfreeze_packet,
    _packet_canonical,
)


def _v3_judge_lossless_transport(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Encode repeated complete result bodies once, without changing the packet."""
    projected = _unfreeze_packet(payload)
    registry: dict[str, Any] = {}
    for entries in projected.get("platform_read_responses", {}).values():
        for entry in entries:
            body = entry.pop("result")
            digest = hashlib.sha256(_packet_canonical(body)).hexdigest()
            registry[digest] = body
            entry["result_ref"] = digest
    return {
        "encoding": "lossless-result-body-registry",
        "packet": projected,
        "result_body_registry": registry,
    }


def _v3_acceptance_first_turn_text(packet, role_instructions: str) -> str:
    """Build the actual native input without allocating a child or reading files."""
    payload = _unfreeze_packet(packet.payload)
    platform_role = packet.role == CQ_ACCEPTANCE_PLATFORM_ROLE
    if platform_role:
        # The Platform Examiner stays blind: no answer, no evidence bundle.
        isolation = (
            "One continuous session per batch, questions in packet order, no "
            "answer text, no source directory, no evidence bundle, no other context."
        )
    else:
        isolation = (
            "One independent judging session per batch, questions in packet order; "
            "this packet carries the frozen answer points, approved evidence "
            "or its frozen references, and the Examiner reports, and no platform read is "
            "available to you."
        )
    first_turn_text = (
        "R3.0-011 v3 hidden-batch acceptance session. Use only this serialized packet "
        "and its authorized frozen references, and submit per-question v3 reports through the acceptance MCP "
        "server. "
        + isolation
        + " PACKET_JSON="
        + _packet_canonical(payload).decode("utf-8")
        + " "
        + role_instructions
        + f" PACKET_SCHEMA={packet.schema_version} PACKET_DIGEST={packet.canonical_digest}"
    )
    if not platform_role:
        transport = _v3_judge_lossless_transport(packet.payload)
        # This is explicitly a transport JSON, not the original packet schema.
        # The native sink and private input remain bound to the full packet.
        original_input = " PACKET_JSON=" + _packet_canonical(payload).decode("utf-8")
        transport_input = (
            " Lossless transport only: TRANSPORT_JSON.packet is the original packet "
            "with each retained result replaced by result_ref. Resolve every result_ref "
            "against result_body_registry to use the complete result as that entry's result. "
            "Body digests are transport indexes only, not business IRIs or new evidence. "
            "Evidence references still use the original response_digest and artifact_path. "
            "No evidence is omitted. PACKET_DIGEST binds the expanded original canonical "
            "packet, not this transport JSON. TRANSPORT_JSON="
            + _packet_canonical(transport).decode("utf-8")
        )
        first_turn_text = first_turn_text.replace(original_input, transport_input, 1)
        if packet.source_registry is not None:
            first_turn_text += (
                " Frozen source reference contract v2: business material is a manifest only. "
                "Call examiner_report.read_frozen_evidence with run_id, batch_id, freeze_digest "
                "and reference_id from the manifest to obtain original text. Reuse same frozen "
                "source/content digest/review version already read in this session; rereads "
                "are allowed. Cite a relevant reference_id in each pass note. Manifest alone "
                "cannot support pass. No filesystem, platform or database reads are authorized."
            )
    return first_turn_text
