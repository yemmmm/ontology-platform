"""Regression coverage for the generic v4 Consumer answer contract.

These checks protect the answer-organization guidance used by the real v3
Platform Examiner.  They intentionally do not encode the exposed G-04/M-03
questions or their reference answers.
"""

from modeling_team.contracts import repository_root


def test_v3_platform_examiner_requires_object_state_and_responsibility_separation():
    root = repository_root()
    prompt = (
        root / "modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md"
    ).read_text(encoding="utf-8")

    required_fragments = (
        "State the direct conclusion first",
        "transport/API",
        "request or action result",
        "state or progress of the business object",
        "accepted response, an empty",
        "technical database/API mapping maintenance",
        "platform authorization",
        "do not infer a responsibility or a platform right from a role name",
        "generic answer contract",
    )
    for fragment in required_fragments:
        assert fragment in prompt


def test_v3_platform_examiner_contract_has_no_scenario_answer_key():
    root = repository_root()
    prompt = (
        root / "modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md"
    ).read_text(encoding="utf-8")

    for scenario_detail in (
        "close-requests",
        "status=closed",
        "integration-maintainer",
        "customerConfirmationReference",
    ):
        assert scenario_detail not in prompt
