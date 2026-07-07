"""Placeholder for the AgentTestService.run_agent_test happy path.

The agent-test service refactor lands in Phase B (Task B2). Phase A only
needs this file to exist so Task B2 can replace the skip with real coverage.
"""
import pytest


@pytest.mark.skip(reason="AgentTestService refactor lands in Phase B (Task B2)")
def test_run_agent_test_graph_context_placeholder():
    """Will assert that AgentTestResponse.graph_context.entries is populated
    from the agent-test-context read model once Task B2 lands."""
    raise NotImplementedError
