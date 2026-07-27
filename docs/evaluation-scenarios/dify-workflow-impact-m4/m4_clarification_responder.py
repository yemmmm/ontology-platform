#!/usr/bin/env python3
"""Fail-closed, host-owned clarification responder for the isolated M4 Agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from m4_transport import strip_one_final_line_ending

MAX_REQUEST_BYTES: Final = 16 * 1024
ID_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
REQUEST_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{0,63}\.json$")
RESPONSE_STATUSES: Final = {"answered", "uncertain", "not_eligible"}


class PolicyError(ValueError):
    """A request or host path violates the fail-closed M4 protocol."""


@dataclass(frozen=True)
class HiddenDecision:
    """Host-only semantic recognizer and answer; never staged for the Agent."""

    required_terms: frozenset[str]
    answer: str | None = None
    uncertain_reason: str | None = None


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise PolicyError("duplicate JSON key")
        value[key] = item
    return value


def secure_regular_read(path: Path, limit: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as error:
        raise PolicyError("request is not a no-follow readable file") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PolicyError("request is not one regular unlinked-safe file")
        if info.st_size > limit:
            raise PolicyError("request exceeds byte limit")
        raw = os.read(descriptor, limit + 1)
        if len(raw) > limit:
            raise PolicyError("request exceeds byte limit")
        return raw
    finally:
        os.close(descriptor)


def exclusive_write(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_response_atomically(directory: Path, filename: str, content: bytes) -> None:
    target = directory / filename
    if target.exists() or target.is_symlink():
        raise PolicyError("host response path already exists")
    temporary = directory / f".{filename}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    exclusive_write(temporary, content)
    try:
        os.link(temporary, target, follow_symlinks=False)
    except FileExistsError as error:
        raise PolicyError("host response path was created concurrently") from error
    finally:
        temporary.unlink(missing_ok=True)
    os.chmod(target, 0o400)


def parse_request(raw: bytes, filename: str) -> tuple[dict[str, object], bytes]:
    if not REQUEST_NAME_RE.fullmatch(filename):
        raise PolicyError("request filename is not strict ID.json")
    try:
        stripped = strip_one_final_line_ending(raw)
        request = json.loads(stripped.decode("utf-8"), object_pairs_hook=reject_duplicate_pairs)
        canonical = canonical_json(request)
        ascii_canonical = json.dumps(
            request, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
    except (UnicodeDecodeError, UnicodeEncodeError, json.JSONDecodeError) as error:
        raise PolicyError("request is not strict UTF-8 JSON") from error
    if not isinstance(request, dict) or set(request) != {"id", "affected_terms", "question", "business_impact"}:
        raise PolicyError("request keys do not match clarification contract")
    request_id = request["id"]
    terms = request["affected_terms"]
    question = request["question"]
    impact = request["business_impact"]
    if not isinstance(request_id, str) or not ID_RE.fullmatch(request_id) or filename != f"{request_id}.json":
        raise PolicyError("request ID does not match strict filename")
    if (
        not isinstance(terms, list)
        or not 1 <= len(terms) <= 6
        or any(not isinstance(term, str) or not term.strip() or len(term) > 120 for term in terms)
    ):
        raise PolicyError("affected_terms must be one to six non-empty strings")
    if not isinstance(question, str) or not question.strip() or len(question) > 1200:
        raise PolicyError("question must be a non-empty bounded string")
    if not isinstance(impact, str) or not impact.strip() or len(impact) > 1200:
        raise PolicyError("business_impact must be a non-empty bounded string")
    if stripped not in {canonical, ascii_canonical}:
        raise PolicyError("request is not canonical JSON")
    return request, canonical


def default_hidden_contract(variant: str) -> tuple[HiddenDecision, ...]:
    """Return host-only answers for a baseline or independent withheld variant."""
    if variant not in {"baseline", "pinned-non-successor"}:
        raise ValueError("variant must be baseline or pinned-non-successor")
    lifecycle = (
        "B invokes C through C's Latest published Version."
        if variant == "baseline"
        else "B is pinned to C published Version 1, whose output contract is quality_score:number."
    )
    identity = (
        "quality_rating:number is the documented successor of quality_score:number."
        if variant == "baseline"
        else (
            "quality_rating:number is a distinct new-contract addition; quality_score:number is removed "
            "and no continuity is confirmed."
        )
    )
    return (
        HiddenDecision(frozenset({"b", "c", "version", "invocation"}), answer=lifecycle),
        HiddenDecision(frozenset({"quality_rating", "quality_score", "contract"}), answer=identity),
        HiddenDecision(
            frozenset({"score", "missing", "fallback"}),
            uncertain_reason="The business owner cannot confirm missing-score handling.",
        ),
    )


def hidden_contract_json(variant: str) -> bytes:
    """Serialize the host-owned contract for a single launcher run."""
    return canonical_json(
        {
            "decisions": [
                {
                    "required_terms": sorted(decision.required_terms),
                    **({"answer": decision.answer} if decision.answer is not None else {}),
                    **(
                        {"uncertain_reason": decision.uncertain_reason}
                        if decision.uncertain_reason is not None
                        else {}
                    ),
                }
                for decision in default_hidden_contract(variant)
            ]
        }
    )


def decision_fingerprint(decision: HiddenDecision) -> str:
    """Host-only opaque identity for one visible-input ambiguity."""
    return sha256_bytes(canonical_json({"required_terms": sorted(decision.required_terms)}))


def load_hidden_contract(path: Path) -> tuple[HiddenDecision, ...]:
    """Read a strict host-only contract; it is never supplied to the Agent namespace."""
    try:
        value = json.loads(secure_regular_read(path, MAX_REQUEST_BYTES).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyError("hidden contract is not strict UTF-8 JSON") from error
    if not isinstance(value, dict) or set(value) != {"decisions"} or not isinstance(value["decisions"], list):
        raise PolicyError("hidden contract shape is invalid")
    decisions: list[HiddenDecision] = []
    for item in value["decisions"]:
        if not isinstance(item, dict) or set(item) not in ({"required_terms", "answer"}, {"required_terms", "uncertain_reason"}):
            raise PolicyError("hidden contract decision shape is invalid")
        terms = item["required_terms"]
        if not isinstance(terms, list) or not terms or any(not isinstance(term, str) for term in terms):
            raise PolicyError("hidden contract terms are invalid")
        answer = item.get("answer")
        reason = item.get("uncertain_reason")
        if answer is not None and not isinstance(answer, str):
            raise PolicyError("hidden contract answer is invalid")
        if reason is not None and not isinstance(reason, str):
            raise PolicyError("hidden contract reason is invalid")
        decisions.append(HiddenDecision(frozenset(terms), answer=answer, uncertain_reason=reason))
    return tuple(decisions)


class ClarificationResponder:
    """Owns host answers and emits only one safe matching response at a time."""

    def __init__(
        self,
        *,
        requests: Path,
        responses: Path,
        audit_path: Path,
        hidden_contract: tuple[HiddenDecision, ...],
    ) -> None:
        self.requests = requests
        self.responses = responses
        self.audit_path = audit_path
        self.hidden_contract = hidden_contract
        self.handled_ids: set[str] = set()
        self.completed_files: dict[str, tuple[int, int, int]] = {}
        self.rejected_names: set[str] = set()
        for directory in (requests, responses):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = os.lstat(directory)
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise PolicyError("clarification directory is unsafe")
        self.audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def audit(self, **entry: object) -> None:
        # Deliberately exclude hidden contract keys and answer text, even from host audit summaries.
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": utc_now(), **entry}, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _meaning_tokens(request: dict[str, object]) -> set[str]:
        values = [*request["affected_terms"], request["question"], request["business_impact"]]
        return set(re.findall(r"[a-z0-9_]+", " ".join(str(value).lower() for value in values)))

    def _decision_for(self, request: dict[str, object]) -> HiddenDecision | None:
        tokens = self._meaning_tokens(request)
        # The hidden contract retains canonical terms, but eligibility is based on the ordinary
        # business meaning expressed across terms, question and impact—not a prescribed sentence.
        lifecycle = (
            {"b", "c"} <= tokens
            and bool(tokens & {"follow", "follows", "invoke", "invokes", "invocation", "target", "targets"})
            and bool(tokens & {"latest", "earlier", "previous", "published", "release", "version", "pin", "pinned"})
        )
        identity = bool(tokens & {"quality_rating", "rating"}) and bool(
            tokens & {"quality_score", "score"}
        ) and bool(tokens & {"successor", "separate", "continuity", "change", "replacement"})
        missing_score = bool(tokens & {"score", "scoring", "rating"}) and bool(
            tokens & {"missing", "unavailable", "absent", "fallback", "when", "if"}
        )
        matches = [
            decision
            for decision, recognized in zip(self.hidden_contract, (lifecycle, identity, missing_score), strict=True)
            if recognized
        ]
        return matches[0] if len(matches) == 1 else None

    def _response_for(self, request: dict[str, object]) -> bytes:
        decision = self._decision_for(request)
        request_id = str(request["id"])
        if decision is None:
            return canonical_json(
                {"id": request_id, "reason": "The request does not reach an answerable visible-input gap.", "status": "not_eligible"}
            )
        if decision.answer is not None:
            return canonical_json({"answer": decision.answer, "id": request_id, "status": "answered"})
        return canonical_json({"id": request_id, "reason": decision.uncertain_reason, "status": "uncertain"})

    def process_once(self) -> int:
        entries = []
        with os.scandir(self.requests) as scanned:
            for entry in scanned:
                if entry.name.startswith(".") or entry.name in self.rejected_names:
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if self.completed_files.get(entry.name) == (info.st_dev, info.st_ino, info.st_ctime_ns):
                    continue
                entries.append(entry)
        if len(entries) > 1:
            for entry in entries:
                self.rejected_names.add(entry.name)
                self.audit(policy="rejected", filename=entry.name, reason="simultaneous_open_questions")
            return 0
        if not entries:
            return 0
        entry = entries[0]
        try:
            if not entry.is_file(follow_symlinks=False) or entry.is_symlink():
                raise PolicyError("request is not a regular non-symlink file")
            info = entry.stat(follow_symlinks=False)
            file_identity = (info.st_dev, info.st_ino, info.st_ctime_ns)
            if self.completed_files.get(entry.name) == file_identity:
                return 0
            raw = secure_regular_read(Path(entry.path), MAX_REQUEST_BYTES)
            request, canonical = parse_request(raw, entry.name)
            request_id = str(request["id"])
            if request_id in self.handled_ids:
                raise PolicyError("duplicate request ID")
            response_path = self.responses / entry.name
            if response_path.exists() or response_path.is_symlink():
                raise PolicyError("host response path was precreated or tampered")
            response = self._response_for(request)
            write_response_atomically(self.responses, entry.name, response)
            self.handled_ids.add(request_id)
            self.completed_files[entry.name] = file_identity
            response_value = json.loads(response.decode("utf-8"))
            decision = self._decision_for(request)
            self.audit(
                policy="responded",
                filename=entry.name,
                request_id=request_id,
                raw_request_sha256=sha256_bytes(raw),
                canonical_request_sha256=sha256_bytes(canonical),
                response_sha256=sha256_bytes(response),
                status=response_value["status"],
                **(
                    {"decision_fingerprint": decision_fingerprint(decision)}
                    if decision is not None
                    else {}
                ),
            )
            return 1
        except PolicyError as error:
            self.rejected_names.add(entry.name)
            self.audit(policy="rejected", filename=entry.name, reason=str(error))
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    contract_source = parser.add_mutually_exclusive_group(required=True)
    contract_source.add_argument("--variant", choices=("baseline", "pinned-non-successor"))
    contract_source.add_argument("--contract", type=Path)
    args = parser.parse_args()
    responder = ClarificationResponder(
        requests=args.requests,
        responses=args.responses,
        audit_path=args.audit,
        hidden_contract=load_hidden_contract(args.contract)
        if args.contract is not None
        else default_hidden_contract(args.variant),
    )
    if args.poll_seconds <= 0:
        raise PolicyError("poll seconds must be positive")
    if args.watch:
        while True:
            responder.process_once()
            time.sleep(args.poll_seconds)
    else:
        responder.process_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
