from pathlib import Path
from unittest.mock import Mock, call

import pytest
import test_e2e

from software_factory.config import Config

URL = "https://github.com/TeroTS/factory-smoke-test/pull/8"
QUEUED = {"state": "open", "labels": [{"name": "agent:implement"}]}
CLAIMED = {"state": "open", "labels": []}


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = Config("TeroTS/factory-smoke-test", tmp_path / "compose.yaml", "agent", "model")
    github = Mock()
    github.discover.return_value = []
    github.open_pr.side_effect = [None, URL]
    github.branch_exists.return_value = False
    commands = Mock()
    commands.run.return_value = ""
    runner = Mock()
    sleep = Mock()
    monkeypatch.setenv("FACTORY_E2E_APPROVED", "1")
    monkeypatch.setenv("FACTORY_E2E_CONFIG", str(tmp_path / "operator.toml"))
    monkeypatch.setenv("FACTORY_E2E_ISSUE", "7")
    monkeypatch.setattr(test_e2e, "load_config", Mock(return_value=config))
    monkeypatch.setattr(test_e2e, "preflight", Mock(return_value={}))
    monkeypatch.setattr(test_e2e, "Commands", Mock(return_value=commands))
    monkeypatch.setattr(test_e2e, "GitHub", Mock(return_value=github))
    monkeypatch.setattr(test_e2e, "Runner", Mock(return_value=runner))
    monkeypatch.setattr(test_e2e.time, "sleep", sleep)
    return github, runner, sleep


@pytest.mark.parametrize("already_queued", [True, False])
def test_discovery_delay_polls_without_reapplying_trigger(harness, already_queued: bool) -> None:
    github, runner, sleep = harness
    responses = [QUEUED] if already_queued else [CLAIMED, []]
    github.api.side_effect = responses + [
        QUEUED,
        CLAIMED,
        {"draft": True, "body": "Closes #7"},
        [[{"body": f"Succeeded: {URL}"}]],
    ]
    github.discover.side_effect = [[7] if already_queued else [], [], [7], []]

    test_e2e.test_operator_submits_issue_and_observes_linked_validated_draft_pr()

    assert runner.poll_once.call_count == 2
    assert sleep.call_args_list == [call(0), call(30)]
    writes = [request for request in github.api.call_args_list if request.kwargs.get("method") == "POST"]
    assert len(writes) == (0 if already_queued else 1)
    if writes:
        assert writes[0] == call("issues/7/labels", method="POST", payload={"labels": ["agent:implement"]})


def test_claimed_failure_does_not_retry_or_requeue(harness) -> None:
    github, runner, sleep = harness
    github.api.side_effect = [QUEUED, CLAIMED]
    github.open_pr.side_effect = [None, None]

    with pytest.raises(AssertionError, match="do not blindly rerun"):
        test_e2e.test_operator_submits_issue_and_observes_linked_validated_draft_pr()

    runner.poll_once.assert_called_once()
    assert sleep.call_args_list == [call(0)]
    assert all(request.kwargs.get("method") != "POST" for request in github.api.call_args_list)


def test_discovery_wait_is_bounded_without_trigger_reapplication(harness) -> None:
    github, runner, sleep = harness
    github.api.side_effect = [QUEUED, QUEUED, QUEUED, QUEUED]
    github.open_pr.side_effect = [None, None]

    with pytest.raises(AssertionError, match="do not blindly rerun"):
        test_e2e.test_operator_submits_issue_and_observes_linked_validated_draft_pr()

    assert runner.poll_once.call_count == 3
    assert sleep.call_args_list == [call(0), call(30), call(30)]
    assert all(request.kwargs.get("method") != "POST" for request in github.api.call_args_list)


def test_another_queued_issue_prevents_polling(harness) -> None:
    github, runner, _ = harness
    github.api.return_value = QUEUED
    github.discover.side_effect = [[], [99]]

    with pytest.raises(AssertionError, match="another issue was queued"):
        test_e2e.test_operator_submits_issue_and_observes_linked_validated_draft_pr()

    runner.poll_once.assert_not_called()
