"""Host-owned immutable text packages, scoped to existing role channels."""

from __future__ import annotations

import base64
import json
import os
import stat
import uuid
from hashlib import sha256
from pathlib import Path, PurePosixPath


class MaterialError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.data = {"ok": False, "code": code, "message": message,
                     "retry": "correct the material binding or use the continuation metadata"}
        super().__init__(f"{code}: {message}")


REF_SCHEMA = {
    "type": "object", "properties": {
        "material_id": {"type": "string"}, "path": {"type": "string"},
    }, "required": ["material_id"], "additionalProperties": False,
}
HANDOFF_TOOL_SPECS = [
    {"name": "write_handoff_output", "description": "Write text in your private output directory.",
     "inputSchema": {"type": "object", "properties": {
         "relative_path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["relative_path", "content"], "additionalProperties": False}},
    {"name": "publish_handoff_material", "description": "Snapshot authorized text files for an existing recipient channel.",
     "inputSchema": {"type": "object", "properties": {
         "recipient_id": {"type": "string"}, "source_path": {"type": "string"},
         "members": {"type": "array", "items": {"type": "string"}}},
         "required": ["recipient_id", "source_path"], "additionalProperties": False}},
    {"name": "list_handoff_material", "description": "List a fixed package; follow next_cursor until list_complete.",
     "inputSchema": {"type": "object", "properties": {
         "material_id": {"type": "string"}, "cursor": {"type": ["string", "null"]},
         "max_entries": {"type": "integer", "minimum": 1, "maximum": 100}},
         "required": ["material_id"], "additionalProperties": False}},
    {"name": "read_handoff_material", "description": "Read immutable UTF-8 text; continue at next_offset until read_complete.",
     "inputSchema": {"type": "object", "properties": {
         "material_id": {"type": "string"}, "path": {"type": "string"},
         "offset": {"type": "integer", "minimum": 0},
         "max_bytes": {"type": "integer", "minimum": 1, "maximum": 16384}},
         "required": ["material_id"], "additionalProperties": False}},
]
HANDOFF_TOOL_NAMES = {item["name"] for item in HANDOFF_TOOL_SPECS}


def _relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise MaterialError("material_path_invalid", "use a relative text path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) == ".":
        raise MaterialError("material_path_invalid", "path escapes its source")
    return path


def _no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise MaterialError("material_path_invalid", "symlinks are not supported")


class HandoffMaterials:
    def __init__(self, root: Path, scope_id: str):
        self.root = Path(root)
        self.scope_id = scope_id
        self.actors: dict[str, dict] = {}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def register_actor(self, actor_id: str, sources: dict[str, Path], recipients: set[str],
                       source_recipients: dict[str, set[str]] | None = None) -> None:
        _relative(actor_id)
        if "/" in actor_id:
            raise MaterialError("material_path_invalid", "invalid actor identity")
        output = self.root.parent / "handoff-output" / actor_id
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        mapped = {str(Path(alias)): Path(path) for alias, path in sources.items()}
        mapped[str(output)] = output
        mapped["/agent/handoff-output"] = output
        self.actors[actor_id] = {"sources": mapped, "recipients": set(recipients),
                                 "source_recipients": source_recipients or {}, "output": output}

    def _actor(self, actor_id: str) -> dict:
        if actor_id not in self.actors:
            raise MaterialError("material_forbidden", "missing authorized actor binding")
        return self.actors[actor_id]

    def _source(self, actor_id: str, source_path: str, recipient_id: str) -> tuple[Path, str]:
        actor = self._actor(actor_id)
        if recipient_id not in actor["recipients"]:
            raise MaterialError("material_forbidden", "recipient channel is not authorized")
        if not isinstance(source_path, str) or ".." in PurePosixPath(source_path).parts:
            raise MaterialError("material_path_invalid", "path escapes its source")
        candidate = Path(source_path)
        for alias in sorted(actor["sources"], key=len, reverse=True):
            try:
                relative = candidate.relative_to(alias)
            except ValueError:
                continue
            allowed = actor["source_recipients"].get(alias, actor["recipients"])
            if recipient_id not in allowed:
                raise MaterialError("material_forbidden", "source has no recipient authorization")
            host = actor["sources"][alias] / relative
            _no_links(host)
            return host, alias
        raise MaterialError("material_forbidden", "source has no authorized path mapping")

    def write_output(self, actor_id: str, relative_path: str, content: str) -> dict:
        path = self._actor(actor_id)["output"] / _relative(relative_path)
        if not isinstance(content, str):
            raise MaterialError("material_media_unsupported", "output must be UTF-8 text")
        _no_links(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _no_links(path)
        with path.open("w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(path, 0o600)
        return {"source_path": "/agent/handoff-output/" + str(_relative(relative_path)),
                "bytes": len(content.encode("utf-8")), "published": False}

    def publish(self, actor_id: str, recipient_id: str, source_path: str,
                members: list[str] | None = None) -> dict:
        source, alias = self._source(actor_id, source_path, recipient_id)
        try:
            if source.is_dir():
                if members is not None and (not isinstance(members, list) or not members):
                    raise MaterialError("material_path_invalid", "members must select files")
                files = ([source / _relative(item) for item in members] if members is not None
                         else sorted(source.rglob("*")))
                selected = []
                for file in files:
                    _no_links(file)
                    if file.is_dir():
                        if members is not None:
                            raise MaterialError("material_member_missing", "select a file member")
                        continue
                    selected.append((file.relative_to(source).as_posix(), file))
                kind = "directory"
            else:
                if members is not None:
                    raise MaterialError("material_path_invalid", "members require a directory")
                selected, kind = [(source.name, source)], "file"
            contents = {}
            identities = {}
            for relative, file in selected:
                metadata = file.stat()
                if not stat.S_ISREG(metadata.st_mode):
                    raise MaterialError("material_media_unsupported", "only regular UTF-8 files are supported")
                data = file.read_bytes()
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError:
                    raise MaterialError("material_media_unsupported", "file is not UTF-8 text") from None
                identities[relative] = (file, metadata)
                contents[relative] = data
                if kind == "directory":
                    # A directory may contain roots with narrower recipient bindings.
                    self._source(actor_id, str(Path(source_path) / relative), recipient_id)
            # Detect source edits during snapshot, including changes to the full directory set.
            for relative, (file, before) in identities.items():
                after = file.stat()
                if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                        after.st_ino, after.st_size, after.st_mtime_ns) or file.read_bytes() != contents[relative]:
                    raise MaterialError("material_source_changed", "source changed during publication")
            if kind == "directory" and members is None:
                now = sorted(p.relative_to(source).as_posix() for p in source.rglob("*") if not p.is_dir())
                if now != sorted(contents):
                    raise MaterialError("material_source_changed", "directory changed during publication")
        except OSError:
            raise MaterialError("material_source_unavailable", "selected source cannot be read") from None
        material_id = "material-" + uuid.uuid4().hex
        package = self.root / material_id
        manifest = {"material_id": material_id, "kind": kind, "scope_id": self.scope_id,
                    "publisher_id": actor_id, "recipient_id": recipient_id,
                    "source_alias": alias, "source_path": source_path,
                    "entries": [{"path": relative, "digest": sha256(data).hexdigest(), "bytes": len(data)}
                                for relative, data in sorted(contents.items())]}
        raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
        package.mkdir(mode=0o700)
        for relative, data in contents.items():
            target = package / "files" / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(data)
            os.chmod(target, 0o400)
        (package / "manifest.json").write_bytes(raw)
        (package / "manifest.sha256").write_text(sha256(raw).hexdigest())
        for name in ("manifest.json", "manifest.sha256"):
            os.chmod(package / name, 0o400)
        return self.list(actor_id, material_id)

    def _manifest(self, actor_id: str, material_id: str) -> tuple[dict, str]:
        self._actor(actor_id)
        if not isinstance(material_id, str) or not material_id.startswith("material-") or "/" in material_id or ".." in material_id:
            raise MaterialError("material_forbidden", "material is unavailable for this identity")
        try:
            package = self.root / material_id
            _no_links(package / "manifest.json")
            raw = (package / "manifest.json").read_bytes()
            digest = (package / "manifest.sha256").read_text()
            manifest = json.loads(raw)
        except (OSError, ValueError):
            raise MaterialError("material_source_unavailable", "material package is unavailable") from None
        if sha256(raw).hexdigest() != digest:
            raise MaterialError("material_digest_mismatch", "manifest bytes changed")
        if (not isinstance(manifest, dict) or not {
                "scope_id", "publisher_id", "recipient_id", "source_alias", "entries", "kind"
        } <= set(manifest)):
            raise MaterialError("material_digest_mismatch", "manifest structure changed")
        binding = None
        scope_bound = manifest["scope_id"] == self.scope_id
        if not scope_bound:
            try:
                binding = json.loads((package / "restored-binding.json").read_text())
                scope_bound = (
                    isinstance(binding, dict)
                    and binding.get("scope_id") == self.scope_id
                    and binding.get("origin_scope_id") == manifest["scope_id"]
                    and binding.get("manifest_digest") == digest
                )
            except (OSError, ValueError):
                pass
        if not scope_bound or actor_id not in {manifest["publisher_id"], manifest["recipient_id"]}:
            raise MaterialError("material_forbidden", "material has no current identity binding")
        publisher = self._actor(manifest["publisher_id"])
        recipient = manifest["recipient_id"]
        source_alias = (
            binding.get("source_alias", manifest["source_alias"])
            if isinstance(binding, dict) else manifest["source_alias"]
        )
        if (recipient not in publisher["recipients"] or source_alias not in publisher["sources"]
                or recipient not in publisher["source_recipients"].get(source_alias, publisher["recipients"])):
            raise MaterialError("material_forbidden", "material source authorization was revoked")
        # A directory publication is authorized as a fixed member set.  A
        # later narrower source grant must therefore be rechecked for every
        # original member; checking only the broad root alias would let a
        # revoked member remain readable through its old manifest.
        source_path = binding.get("source_path", manifest.get("source_path")) if isinstance(binding, dict) else manifest.get("source_path")
        if not isinstance(source_path, str):
            raise MaterialError("material_forbidden", "material source binding is incomplete")
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise MaterialError("material_digest_mismatch", "material entries are invalid")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise MaterialError("material_digest_mismatch", "material entry is invalid")
            member_source = (
                source_path
                if manifest.get("kind") == "file"
                else str(Path(source_path) / entry["path"])
            )
            self._source(manifest["publisher_id"], member_source, recipient)
        return manifest, digest

    def bind_restored_material(self, material_id: str, origin_scope_id: str,
                              manifest_digest: str, *, source_alias: str | None = None,
                              source_path: str | None = None) -> None:
        """Bind one verified checkpoint package without changing its original manifest.

        Only the Host restore path calls this after artifact digest verification;
        current role/source/channel grants still apply on every subsequent read.
        """
        _relative(material_id)
        package = self.root / material_id
        _no_links(package)
        try:
            raw = (package / "manifest.json").read_bytes()
            manifest = json.loads(raw)
        except (OSError, ValueError):
            raise MaterialError("material_source_unavailable", "restored manifest is unavailable") from None
        if sha256(raw).hexdigest() != manifest_digest or manifest.get("scope_id") != origin_scope_id:
            raise MaterialError("material_binding_changed", "checkpoint material identity changed")
        publisher = self._actor(str(manifest.get("publisher_id")))
        recipient = manifest.get("recipient_id")
        if not isinstance(recipient, str) or recipient not in publisher["recipients"]:
            raise MaterialError("material_binding_changed", "restored recipient channel is not authorized")
        original_alias = manifest.get("source_alias")
        original_path = manifest.get("source_path")
        source_alias = source_alias if source_alias is not None else original_alias
        source_path = source_path if source_path is not None else original_path
        if not isinstance(source_alias, str) or not isinstance(source_path, str):
            raise MaterialError("material_binding_changed", "restored source binding is incomplete")
        # The restore caller translates a physical run-root alias/path to the
        # equivalent current run-root binding. Validate that exact mapping;
        # never infer a grant from a same-named file in an unrelated source.
        if source_alias not in publisher["sources"]:
            raise MaterialError("material_binding_changed", "restored source alias is unavailable")
        if recipient not in publisher["source_recipients"].get(source_alias, publisher["recipients"]):
            raise MaterialError("material_binding_changed", "restored source recipient grant is unavailable")
        try:
            _host, matched_alias = self._source(str(manifest.get("publisher_id")), source_path, recipient)
        except MaterialError as exc:
            raise MaterialError("material_binding_changed", "restored source path is outside current grant") from exc
        if matched_alias != source_alias:
            raise MaterialError("material_binding_changed", "restored source path does not match its alias")
        binding = {"scope_id": self.scope_id, "origin_scope_id": origin_scope_id,
                   "manifest_digest": manifest_digest, "source_alias": source_alias,
                   "source_path": source_path}
        (package / "restored-binding.json").write_text(json.dumps(binding, sort_keys=True))
        os.chmod(package / "restored-binding.json", 0o400)

    def list(self, actor_id: str, material_id: str, cursor: str | None = None,
             max_entries: int = 100) -> dict:
        manifest, digest = self._manifest(actor_id, material_id)
        if type(max_entries) is not int or not 1 <= max_entries <= 100:
            raise MaterialError("material_cursor_invalid", "max_entries must be 1..100")
        start = 0
        if cursor is not None:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if decoded[:3] != [actor_id, self.scope_id, digest] or type(decoded[3]) is not int:
                    raise ValueError()
                start = decoded[3]
                if not 0 <= start < len(manifest["entries"]):
                    raise ValueError()
            except (ValueError, TypeError, IndexError):
                raise MaterialError("material_cursor_invalid", "cursor does not bind this manifest and identity") from None
        end = min(start + max_entries, len(manifest["entries"]))
        next_cursor = (base64.urlsafe_b64encode(json.dumps([actor_id, self.scope_id, digest, end]).encode()).decode()
                       if end < len(manifest["entries"]) else None)
        return {"material_id": material_id, "kind": manifest["kind"], "manifest_digest": digest,
                "binding": {"scope_id": self.scope_id, "publisher_id": manifest["publisher_id"],
                            "recipient_id": manifest["recipient_id"]},
                "file_count": len(manifest["entries"]), "total_bytes": sum(e["bytes"] for e in manifest["entries"]),
                "entries": manifest["entries"][start:end], "list_complete": next_cursor is None,
                "next_cursor": next_cursor}

    def _bytes(self, actor_id: str, material_id: str, path: str | None) -> tuple[bytes, dict]:
        manifest, _ = self._manifest(actor_id, material_id)
        if path is None:
            if manifest["kind"] != "file":
                raise MaterialError("material_member_required", "select path from list_handoff_material")
            path = manifest["entries"][0]["path"]
        entry = next((item for item in manifest["entries"] if item["path"] == path), None)
        if entry is None:
            raise MaterialError("material_member_missing", "path is not a published member; list the material")
        target = self.root / material_id / "files" / _relative(path)
        _no_links(target)
        try:
            data = target.read_bytes()
        except OSError:
            raise MaterialError("material_source_unavailable", "snapshot member is unavailable") from None
        if sha256(data).hexdigest() != entry["digest"]:
            raise MaterialError("material_digest_mismatch", "snapshot bytes changed")
        return data, entry

    def read(self, actor_id: str, material_id: str, path: str | None = None,
             offset: int = 0, max_bytes: int = 16384) -> dict:
        data, entry = self._bytes(actor_id, material_id, path)
        if type(offset) is not int or not 0 <= offset <= len(data) or type(max_bytes) is not int or not 1 <= max_bytes <= 16384:
            raise MaterialError("material_cursor_invalid", "use a valid byte offset and max_bytes 1..16384")
        if offset < len(data) and data[offset] & 0xC0 == 0x80:
            raise MaterialError("material_cursor_invalid", "offset must be a UTF-8 boundary; use next_offset")
        end = min(offset + max_bytes, len(data))
        while end < len(data) and data[end] & 0xC0 == 0x80:
            end -= 1
        if end == offset and offset < len(data):
            end = offset + 1
            while end < len(data) and data[end] & 0xC0 == 0x80:
                end += 1
        return {"material_id": material_id, "path": entry["path"], "content": data[offset:end].decode("utf-8"),
                "content_digest": entry["digest"], "bytes": len(data), "offset": offset,
                "next_offset": end, "read_complete": end == len(data),
                "truncated": end != len(data)}

    def resolve(self, actor_id: str, ref: dict) -> str:
        if not isinstance(ref, dict) or set(ref) - {"material_id", "path"} or "material_id" not in ref:
            raise MaterialError("material_path_invalid", "ref requires material_id and optional path")
        return self._bytes(actor_id, ref["material_id"], ref.get("path"))[0].decode("utf-8")

    def authorize_ref(self, actor_id: str, recipient_id: str, ref: dict) -> None:
        if not isinstance(ref, dict) or "material_id" not in ref:
            raise MaterialError("material_path_invalid", "ref requires material_id")
        manifest, _ = self._manifest(actor_id, ref["material_id"])
        if recipient_id != manifest["recipient_id"] or manifest["publisher_id"] != actor_id:
            raise MaterialError("material_forbidden", "ref is not published for this channel")

    def relay_ref(self, publisher_id: str, recipient_id: str, ref: dict,
                  origin_store=None, origin_actor_id: str | None = None) -> dict:
        """Host relay on an existing channel, after the original source was authorized.

        This is not an Agent tool. Callers must select the original public channel;
        a host's ability to read private evidence never authorizes this relay.
        """
        origin = origin_store or self
        actor = origin_actor_id or publisher_id
        manifest, _ = origin._manifest(actor, ref["material_id"])
        directory = "relay-" + uuid.uuid4().hex
        for entry in manifest["entries"]:
            data, _ = origin._bytes(actor, ref["material_id"], entry["path"])
            self.write_output(publisher_id, directory + "/" + entry["path"], data.decode("utf-8"))
        source = "/agent/handoff-output/" + directory
        if manifest["kind"] == "file":
            source += "/" + manifest["entries"][0]["path"]
        published = self.publish(publisher_id, recipient_id, source)
        result = {"material_id": published["material_id"]}
        if ref.get("path") is not None:
            result["path"] = ref["path"]
        return result

    def call(self, actor_id: str, name: str, args: dict) -> dict:
        spec = next((item for item in HANDOFF_TOOL_SPECS if item["name"] == name), None)
        if spec is None or not isinstance(args, dict):
            raise MaterialError("material_path_invalid", "unknown material operation")
        schema = spec["inputSchema"]
        if set(args) - set(schema["properties"]) or not set(schema["required"]) <= set(args):
            raise MaterialError("material_path_invalid", "invalid material operation fields")
        operation = {"write_handoff_output": self.write_output, "publish_handoff_material": self.publish,
                     "list_handoff_material": self.list, "read_handoff_material": self.read}[name]
        return operation(actor_id, **args)
