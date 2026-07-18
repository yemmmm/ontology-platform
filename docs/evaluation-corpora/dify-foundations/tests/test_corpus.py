from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


CORPUS_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "dify-foundations-2026-07-18-5396c1a"
SNAPSHOT = CORPUS_ROOT / "snapshots" / SNAPSHOT_ID
TOOL_PATH = CORPUS_ROOT / "tools" / "corpus.py"
SPEC = importlib.util.spec_from_file_location("dify_corpus", TOOL_PATH)
assert SPEC and SPEC.loader
corpus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(corpus)


class CorpusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def copy_snapshot(self) -> Path:
        destination = self.temp_root / SNAPSHOT_ID
        shutil.copytree(SNAPSHOT, destination)
        return destination

    @staticmethod
    def load_manifest(snapshot: Path) -> dict:
        return json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def write_manifest(snapshot: Path, manifest: dict) -> None:
        (snapshot / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def replace_registered_file(self, snapshot: Path, source_path: str, data: bytes) -> None:
        manifest = self.load_manifest(snapshot)
        entry = next(item for item in manifest["entries"] if item["source_path"] == source_path)
        (snapshot / entry["snapshot_path"]).write_bytes(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        self.write_manifest(snapshot, manifest)


class VerifyTests(CorpusTestCase):
    def test_committed_snapshot_verifies_repeatedly_without_mutation(self) -> None:
        before = {
            path.relative_to(SNAPSHOT): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SNAPSHOT.rglob("*")
            if path.is_file()
        }
        first = corpus.verify_snapshot(SNAPSHOT)
        second = corpus.verify_snapshot(SNAPSHOT)
        after = {
            path.relative_to(SNAPSHOT): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SNAPSHOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(SNAPSHOT_ID, first["snapshot_id"])
        self.assertEqual(first, second)
        self.assertEqual(before, after)

    def test_missing_and_extra_files_are_rejected(self) -> None:
        missing = self.copy_snapshot()
        (missing / "official/en/home.mdx").unlink()
        with self.assertRaisesRegex(corpus.CorpusError, "registered file set mismatch"):
            corpus.verify_snapshot(missing)

        extra = self.temp_root / "extra" / SNAPSHOT_ID
        shutil.copytree(SNAPSHOT, extra)
        (extra / "official/unregistered.mdx").write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(corpus.CorpusError, "registered file set mismatch"):
            corpus.verify_snapshot(extra)

    def test_hash_drift_is_rejected(self) -> None:
        snapshot = self.copy_snapshot()
        with (snapshot / "official/en/home.mdx").open("ab") as stream:
            stream.write(b"drift")
        with self.assertRaisesRegex(corpus.CorpusError, "sha256 mismatch"):
            corpus.verify_snapshot(snapshot)

    def test_duplicate_source_or_snapshot_path_is_rejected(self) -> None:
        for field in ("source_path", "snapshot_path"):
            with self.subTest(field=field):
                root = self.temp_root / field / SNAPSHOT_ID
                shutil.copytree(SNAPSHOT, root)
                manifest = self.load_manifest(root)
                manifest["entries"][1][field] = manifest["entries"][0][field]
                self.write_manifest(root, manifest)
                with self.assertRaisesRegex(
                    corpus.CorpusError, "duplicate entry path|snapshot_path"
                ):
                    corpus.verify_snapshot(root)

    def test_schema_shape_and_malformed_json_are_rejected(self) -> None:
        snapshot = self.copy_snapshot()
        manifest = self.load_manifest(snapshot)
        manifest["schema_version"] = 2
        self.write_manifest(snapshot, manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "unsupported schema_version"):
            corpus.verify_snapshot(snapshot)

        manifest["schema_version"] = 1
        manifest["unexpected"] = True
        self.write_manifest(snapshot, manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "unknown=\['unexpected'\]"):
            corpus.verify_snapshot(snapshot)

        (snapshot / "manifest.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(corpus.CorpusError, "invalid manifest"):
            corpus.verify_snapshot(snapshot)

    def test_non_official_sources_and_page_hosts_are_rejected(self) -> None:
        for mutation in ("repository", "page"):
            with self.subTest(mutation=mutation):
                root = self.temp_root / mutation / SNAPSHOT_ID
                shutil.copytree(SNAPSHOT, root)
                manifest = self.load_manifest(root)
                if mutation == "repository":
                    manifest["source"]["repository"] = "https://example.com/dify-docs"
                else:
                    manifest["entries"][2]["official_page_url"] = "https://example.com/copied"
                self.write_manifest(root, manifest)
                with self.assertRaisesRegex(corpus.CorpusError, "official"):
                    corpus.verify_snapshot(root)

    def test_github_page_url_requires_official_repo_fixed_commit_and_source_path(self) -> None:
        corpus.verify_snapshot(SNAPSHOT)
        commit = self.load_manifest(SNAPSHOT)["source"]["commit"]
        invalid_urls = (
            f"https://github.com/attacker/dify-docs/blob/{commit}/LICENSE",
            "https://github.com/langgenius/dify-docs/blob/" + "0" * 40 + "/LICENSE",
            f"https://github.com/langgenius/dify-docs/blob/{commit}/docs.json",
            f"https://github.com/langgenius/dify-docs/blob/{commit}/LICENSE?plain=1",
        )
        for index, url in enumerate(invalid_urls):
            with self.subTest(url=url):
                root = self.temp_root / f"github-{index}" / SNAPSHOT_ID
                shutil.copytree(SNAPSHOT, root)
                manifest = self.load_manifest(root)
                license_entry = next(
                    item for item in manifest["entries"] if item["source_path"] == "LICENSE"
                )
                license_entry["official_page_url"] = url
                self.write_manifest(root, manifest)
                with self.assertRaisesRegex(corpus.CorpusError, "GitHub official_page_url"):
                    corpus.verify_snapshot(root)

    def test_previous_snapshot_must_exist_and_match_identity_and_corpus(self) -> None:
        previous_id = "dify-foundations-2026-07-17-1234567"

        dangling = self.temp_root / "dangling" / SNAPSHOT_ID
        shutil.copytree(SNAPSHOT, dangling)
        manifest = self.load_manifest(dangling)
        manifest["previous_snapshot"] = previous_id
        self.write_manifest(dangling, manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "previous_snapshot directory not found"):
            corpus.verify_snapshot(dangling)

        valid = self.temp_root / "valid" / SNAPSHOT_ID
        shutil.copytree(SNAPSHOT, valid)
        manifest = self.load_manifest(valid)
        manifest["previous_snapshot"] = previous_id
        self.write_manifest(valid, manifest)
        previous_dir = valid.parent / previous_id
        previous_dir.mkdir()
        previous_manifest = self.load_manifest(SNAPSHOT)
        previous_manifest["snapshot_id"] = previous_id
        previous_manifest["previous_snapshot"] = None
        self.write_manifest(previous_dir, previous_manifest)
        corpus.verify_snapshot(valid)

        for index, (field, value, message) in enumerate(
            (
                ("snapshot_id", "dify-foundations-2026-07-16-7654321", "identity mismatch"),
                ("corpus_id", "spoofed-corpus", "corpus mismatch"),
            )
        ):
            with self.subTest(field=field):
                root = self.temp_root / f"mismatch-{index}" / SNAPSHOT_ID
                shutil.copytree(SNAPSHOT, root)
                current = self.load_manifest(root)
                current["previous_snapshot"] = previous_id
                self.write_manifest(root, current)
                previous = root.parent / previous_id
                previous.mkdir()
                previous_value = self.load_manifest(SNAPSHOT)
                previous_value["snapshot_id"] = previous_id
                previous_value["previous_snapshot"] = None
                previous_value[field] = value
                self.write_manifest(previous, previous_value)
                with self.assertRaisesRegex(corpus.CorpusError, message):
                    corpus.verify_snapshot(root)

    def test_previous_snapshot_rejects_self_reference_unsafe_id_and_cycle(self) -> None:
        self_reference = self.copy_snapshot()
        manifest = self.load_manifest(self_reference)
        manifest["previous_snapshot"] = SNAPSHOT_ID
        self.write_manifest(self_reference, manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "cycle detected"):
            corpus.verify_snapshot(self_reference)

        unsafe = self.temp_root / "unsafe-previous" / SNAPSHOT_ID
        shutil.copytree(SNAPSHOT, unsafe)
        manifest = self.load_manifest(unsafe)
        manifest["previous_snapshot"] = "../escape"
        self.write_manifest(unsafe, manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "safe Dify snapshot ID"):
            corpus.verify_snapshot(unsafe)

        cycle = self.temp_root / "cycle" / SNAPSHOT_ID
        shutil.copytree(SNAPSHOT, cycle)
        previous_id = "dify-foundations-2026-07-17-1234567"
        manifest = self.load_manifest(cycle)
        manifest["previous_snapshot"] = previous_id
        self.write_manifest(cycle, manifest)
        previous = cycle.parent / previous_id
        previous.mkdir()
        previous_manifest = self.load_manifest(SNAPSHOT)
        previous_manifest["snapshot_id"] = previous_id
        previous_manifest["previous_snapshot"] = SNAPSHOT_ID
        self.write_manifest(previous, previous_manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "cycle detected"):
            corpus.verify_snapshot(cycle)

    def test_unsafe_paths_and_disallowed_content_are_rejected(self) -> None:
        cases = (
            ("source_path", "../escape.mdx", "unsafe source_path"),
            ("snapshot_path", "/tmp/escape.mdx", "unsafe snapshot_path"),
            ("source_path", "en/payload.js", "snapshot_path|disallowed"),
        )
        for index, (field, value, message) in enumerate(cases):
            with self.subTest(field=field, value=value):
                root = self.temp_root / f"path-{index}" / SNAPSHOT_ID
                shutil.copytree(SNAPSHOT, root)
                manifest = self.load_manifest(root)
                manifest["entries"][2][field] = value
                self.write_manifest(root, manifest)
                with self.assertRaisesRegex(corpus.CorpusError, message):
                    corpus.verify_snapshot(root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_is_rejected(self) -> None:
        snapshot = self.copy_snapshot()
        target = snapshot / "official/en/home.mdx"
        target.unlink()
        target.symlink_to(snapshot / "official/zh/home.mdx")
        with self.assertRaisesRegex(corpus.CorpusError, "symlink not allowed"):
            corpus.verify_snapshot(snapshot)

    def test_executable_file_is_rejected(self) -> None:
        snapshot = self.copy_snapshot()
        path = snapshot / "official/en/home.mdx"
        path.chmod(0o755)
        with self.assertRaisesRegex(corpus.CorpusError, "executable content"):
            corpus.verify_snapshot(snapshot)

    def test_translation_contract_and_topic_coverage_are_rejected_when_invalid(self) -> None:
        snapshot = self.copy_snapshot()
        manifest = self.load_manifest(snapshot)
        chinese = next(item for item in manifest["entries"] if item["language"] == "zh")
        chinese["translation_of"] = "en/not-registered.mdx"
        self.write_manifest(snapshot, manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "translation source is not registered"):
            corpus.verify_snapshot(snapshot)

        manifest = self.load_manifest(SNAPSHOT)
        manifest["entries"] = [
            item for item in manifest["entries"] if "quick-start-example" not in item["topics"]
        ]
        self.write_manifest(snapshot, manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "topic coverage mismatch"):
            corpus.verify_snapshot(snapshot, check_files=False)

    def test_secret_is_rejected_without_echoing_value_and_placeholder_is_allowed(self) -> None:
        snapshot = self.copy_snapshot()
        secret = b"Bearer " + b"A" * 32
        self.replace_registered_file(snapshot, "en/home.mdx", secret)
        with self.assertRaises(corpus.CorpusError) as context:
            corpus.verify_snapshot(snapshot)
        self.assertIn("possible Bearer token", str(context.exception))
        self.assertNotIn(secret.decode(), str(context.exception))

        placeholder = self.temp_root / "placeholder" / SNAPSHOT_ID
        shutil.copytree(SNAPSHOT, placeholder)
        self.replace_registered_file(placeholder, "en/home.mdx", b"Bearer <YOUR_API_KEY>")
        corpus.verify_snapshot(placeholder)

    def test_scope_has_official_pairs_navigation_license_and_no_excluded_paths(self) -> None:
        manifest = corpus.verify_snapshot(SNAPSHOT)
        entries = manifest["entries"]
        sources = {entry["source_path"] for entry in entries}
        english = {path for path in sources if path.startswith("en/")}
        chinese_translations = {
            entry["translation_of"] for entry in entries if entry["language"] == "zh"
        }
        self.assertEqual(english, chinese_translations)
        self.assertIn("LICENSE", sources)
        self.assertIn("docs.json", sources)
        self.assertFalse(any(path.startswith(corpus.EXCLUDED_PREFIXES) for path in sources))


class LocateAndEvidenceTests(CorpusTestCase):
    def test_locate_is_stable_and_unknown_topic_fails(self) -> None:
        first = corpus.locate_topic(SNAPSHOT, "jinja2-template")
        second = corpus.locate_topic(SNAPSHOT, "jinja2-template")
        self.assertEqual(first, second)
        self.assertEqual(4, len(first))
        self.assertTrue(any(item["source_path"].endswith("nodes/template.mdx") for item in first))
        with self.assertRaisesRegex(corpus.CorpusError, "unknown or uncovered topic"):
            corpus.locate_topic(SNAPSHOT, "not-a-topic")

    def test_confusable_concepts_and_quick_start_are_exact_snapshot_text(self) -> None:
        app_management = (
            SNAPSHOT / "official/en/cloud/use-dify/workspace/app-management.mdx"
        ).read_text(encoding="utf-8")
        template = (SNAPSHOT / "official/en/cloud/use-dify/nodes/template.mdx").read_text(
            encoding="utf-8"
        )
        quick_start = (SNAPSHOT / "official/en/quick-start.mdx").read_text(encoding="utf-8")
        self.assertIn(
            "Dify's DSL (Domain Specific Language) format lets you share apps between workspaces and teams:",
            app_management,
        )
        self.assertIn("Duplicate & Template", app_management)
        self.assertIn(
            "The Template node transforms and formats data from multiple sources into structured text using Jinja2 templating.",
            template,
        )
        self.assertIn("Multi-platform content generator", quick_start)


class DiffTests(CorpusTestCase):
    def test_diff_reports_all_categories_without_writing_inputs(self) -> None:
        old_path = SNAPSHOT / "manifest.json"
        new_path = self.temp_root / "new.json"
        new = json.loads(old_path.read_text(encoding="utf-8"))
        removed = new["entries"].pop(0)
        modified = new["entries"][0]
        modified["sha256"] = "0" * 64
        added = dict(new["entries"][1])
        added["source_path"] = "en/new-page.mdx"
        added["snapshot_path"] = "official/en/new-page.mdx"
        added["sha256"] = "1" * 64
        new["entries"].append(added)
        new_path.write_text(json.dumps(new), encoding="utf-8")
        before_old = old_path.read_bytes()
        before_new = new_path.read_bytes()
        result = corpus.diff_manifests(old_path, new_path)
        self.assertEqual([removed["source_path"]], result["removed"])
        self.assertEqual([added["source_path"]], result["added"])
        self.assertEqual([modified["source_path"]], result["modified"])
        self.assertGreater(len(result["unchanged"]), 0)
        self.assertEqual(before_old, old_path.read_bytes())
        self.assertEqual(before_new, new_path.read_bytes())

    def test_same_manifest_is_all_unchanged(self) -> None:
        result = corpus.diff_manifests(SNAPSHOT / "manifest.json", SNAPSHOT / "manifest.json")
        self.assertFalse(result["added"])
        self.assertFalse(result["removed"])
        self.assertFalse(result["modified"])
        self.assertEqual(32, len(result["unchanged"]))


class RebuildTests(CorpusTestCase):
    @staticmethod
    def local_download(url: str) -> bytes:
        parsed = urllib.parse.urlsplit(url)
        prefix = "/langgenius/dify-docs/5396c1a1afbea0dee3d089abfabdf6dac91d30d5/"
        if parsed.scheme != "https" or parsed.hostname != corpus.RAW_HOST:
            raise AssertionError(url)
        if not parsed.path.startswith(prefix):
            raise AssertionError(url)
        source_path = urllib.parse.unquote(parsed.path.removeprefix(prefix))
        return (SNAPSHOT / "official" / source_path).read_bytes()

    def test_rebuild_uses_fixed_urls_and_reproduces_all_bytes(self) -> None:
        destination = self.temp_root / SNAPSHOT_ID
        with mock.patch.object(corpus, "_download", side_effect=self.local_download) as download:
            corpus.rebuild_snapshot(SNAPSHOT, destination)
        self.assertEqual(32, download.call_count)
        committed = {
            path.relative_to(SNAPSHOT): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SNAPSHOT.rglob("*")
            if path.is_file()
        }
        rebuilt = {
            path.relative_to(destination): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in destination.rglob("*")
            if path.is_file()
        }
        self.assertEqual(committed, rebuilt)

    def test_nonempty_destination_fails_without_download(self) -> None:
        destination = self.temp_root / SNAPSHOT_ID
        destination.mkdir()
        (destination / "owned.txt").write_text("keep", encoding="utf-8")
        with mock.patch.object(corpus, "_download") as download:
            with self.assertRaisesRegex(corpus.CorpusError, "destination must be absent or empty"):
                corpus.rebuild_snapshot(SNAPSHOT, destination)
        download.assert_not_called()
        self.assertEqual("keep", (destination / "owned.txt").read_text(encoding="utf-8"))

    def test_download_failure_and_hash_mismatch_fail_closed(self) -> None:
        failed = self.temp_root / "failed" / SNAPSHOT_ID
        with mock.patch.object(
            corpus, "_download", side_effect=corpus.CorpusError("network unavailable")
        ):
            with self.assertRaisesRegex(corpus.CorpusError, "network unavailable"):
                corpus.rebuild_snapshot(SNAPSHOT, failed)
        self.assertFalse((failed / "manifest.json").exists())

        mismatch = self.temp_root / "mismatch" / SNAPSHOT_ID
        with mock.patch.object(corpus, "_download", return_value=b"wrong"):
            with self.assertRaisesRegex(corpus.CorpusError, "download hash mismatch"):
                corpus.rebuild_snapshot(SNAPSHOT, mismatch)
        self.assertFalse((mismatch / "manifest.json").exists())

    def test_raw_url_cannot_be_redirected_by_manifest_fields(self) -> None:
        manifest = corpus.verify_snapshot(SNAPSHOT)
        url = corpus._raw_url(manifest, "en/home.mdx")
        parsed = urllib.parse.urlsplit(url)
        self.assertEqual("https", parsed.scheme)
        self.assertEqual("raw.githubusercontent.com", parsed.hostname)
        self.assertIn(manifest["source"]["commit"], parsed.path)


class CliTests(CorpusTestCase):
    def test_cli_success_and_failure_codes(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(0, corpus.main(["verify", str(SNAPSHOT)]))
        self.assertIn("verified", stdout.getvalue())
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(1, corpus.main(["locate", str(SNAPSHOT), "--topic", "missing"]))
        self.assertIn("unknown or uncovered topic", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
