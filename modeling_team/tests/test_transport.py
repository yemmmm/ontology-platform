from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modeling_team.transport_mcp import RoutingError, TeamTransportBroker, mcp_response


class TransportTests(unittest.TestCase):
    def test_exact_unicode_multiline_delivery_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(Path(directory), {("modeling", "protocol")})
            text = "补充事实\nexact: Δ"
            self.assertEqual(broker.send("modeling", "protocol", text).text, text)
            self.assertEqual(broker.drain()[0].text, text)

    def test_unauthorized_and_duplicate_terminal_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(Path(directory), set())
            with self.assertRaises(RoutingError):
                broker.send("modeling", "protocol", "x")
            broker.report("modeling", "completed", "done")
            with self.assertRaises(RoutingError):
                broker.report("modeling", "blocked", "again")

    def test_tools_list_has_complete_mcp_input_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(Path(directory), set())
            response = mcp_response({"method": "tools/list"}, broker=broker, agent_id="modeling")
        tools = {item["name"]: item for item in response["tools"]}
        self.assertEqual(set(tools), {"send_team_message", "report_task_result"})
        self.assertEqual(
            tools["send_team_message"]["inputSchema"]["required"],
            ["recipient_id", "text"],
        )
        self.assertEqual(
            tools["report_task_result"]["inputSchema"]["required"], ["status", "summary"]
        )
