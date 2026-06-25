from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SKILL = Path(__file__).parents[1]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        pass

    def _reply(self, value: object) -> None:
        body = json.dumps(value).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/api/projects/project-1/evidence-artifacts":
            if b"sample.md" not in body or b"text/markdown" not in body:
                self.send_error(400)
                return
            self._reply({"id": "document-1", "parse_status": "parsed"})
        else:
            self.send_error(404)


class ScriptIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def run_script(self, script: str, *args: str) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(SKILL / "scripts" / script), "--base-url", self.base_url, *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_upload_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "sample.md"
            document.write_text("# Trusted data", encoding="utf-8")
            result = self.run_script(
                "upload_document.py", "--project-id", "project-1", str(document)
            )
        self.assertEqual(result["parse_status"], "parsed")


if __name__ == "__main__":
    unittest.main()
