import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from tests_support import prepared_compose

from software_factory.config import Config
from software_factory.process import FactoryError

# Preserve historical orchestration scenarios for porting, not as acceptance of the guarded US-04 runner.
pytestmark = pytest.mark.skip(reason="prepared-Compose runner removed; port these execution regressions in US-05/06/07")


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from software_factory.runner import Runner

    config = Config("owner/repo", tmp_path / "compose.yaml", "agent", "chosen")
    commands = Mock()
    commands.secrets = []
    commands.run.return_value = (
        f"tid=test;proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800};sig=test"
    )
    github = Mock()
    github.discover.return_value = [1]
    github.open_pr.return_value = None
    github.branch_exists.return_value = False
    github.snapshot.return_value = {"number": 1, "title": "task", "body": None}
    github.default_branch.return_value = "main"
    github.publish.return_value = "https://github.com/owner/repo/pull/3"
    repo = Mock()
    repo.workspace = tmp_path / "workspace"
    repo.checkout.return_value = "a" * 40
    sandbox = Mock()
    monkeypatch.setattr("software_factory.runner.Commands", Mock(return_value=commands))
    monkeypatch.setattr("software_factory.runner.GitHub", Mock(return_value=github))
    monkeypatch.setattr("software_factory.runner.Repository", Mock(return_value=repo))
    monkeypatch.setattr("software_factory.runner.Sandbox", Mock(return_value=sandbox))
    runner = Runner(config, prepared_compose(tmp_path / "placeholder"), artifacts=tmp_path / "artifacts")
    return runner, github, repo, sandbox, commands


def test_first_pass_success_obeys_claim_setup_verify_publish_order(runtime) -> None:
    runner, github, repo, sandbox, commands = runtime
    events = Mock()
    for name, obj in [("github", github), ("repo", repo), ("sandbox", sandbox)]:
        events.attach_mock(obj, name)
    runner.poll_once()
    names = [call[0] for call in events.mock_calls]
    expected = [
        "github.discover",
        "github.open_pr",
        "github.branch_exists",
        "github.remove_trigger",
        "github.comment",
        "github.snapshot",
        "github.default_branch",
        "repo.checkout",
        "sandbox.start",
        "sandbox.setup",
        "sandbox.implement",
        "sandbox.verify",
        "sandbox.stop",
        "repo.commit",
        "repo.push",
        "github.publish",
        "github.comment",
    ]
    assert names == expected
    assert sandbox.implement.call_args.args[0] == {"number": 1, "title": "task", "body": None, "base_commit": "a" * 40}
    assert github.comment.call_args.args == (1, "Succeeded: https://github.com/owner/repo/pull/3")
    assert list(runner.artifacts.iterdir()) == []
    assert len(commands.secrets) == 1


@pytest.mark.parametrize("duplicate", ["pr", "branch"])
def test_skips_remove_trigger_before_notification_without_starting_workspace(runtime, duplicate: str) -> None:
    runner, github, repo, sandbox, _ = runtime
    if duplicate == "pr":
        github.open_pr.return_value = "https://github.com/owner/repo/pull/3"
    else:
        github.branch_exists.return_value = True
    events = Mock()
    events.attach_mock(github, "github")
    runner.poll_once()
    calls = [call[0] for call in events.mock_calls]
    assert calls.index("github.remove_trigger") < calls.index("github.comment")
    repo.checkout.assert_not_called()
    sandbox.start.assert_not_called()
    assert "Skipped" in github.comment.call_args.args[1]
    assert list(runner.artifacts.iterdir()) == []


@pytest.mark.parametrize("phase", ["open_pr", "branch_exists", "remove_trigger"])
def test_preclaim_failure_never_executes_or_guesses_label_state(runtime, phase: str, caplog) -> None:
    runner, github, repo, sandbox, _ = runtime
    getattr(github, phase).side_effect = FactoryError("GitHub read or write failed")
    runner.poll_once()
    repo.checkout.assert_not_called()
    sandbox.start.assert_not_called()
    github.comment.assert_not_called()
    assert "GitHub read or write failed" in caplog.text


@pytest.mark.parametrize(
    "component,method",
    [
        ("github", "snapshot"),
        ("repo", "checkout"),
        ("sandbox", "start"),
        ("sandbox", "setup"),
        ("sandbox", "implement"),
        ("sandbox", "verify"),
        ("repo", "commit"),
        ("repo", "push"),
        ("github", "publish"),
    ],
)
def test_failures_retain_diagnostics_without_false_success(runtime, component: str, method: str, caplog) -> None:
    runner, github, repo, sandbox, commands = runtime
    obj = {"github": github, "repo": repo, "sandbox": sandbox}[component]
    getattr(obj, method).side_effect = FactoryError(f"{method} failed")
    runner.poll_once()
    assert "Failed:" in github.comment.call_args.args[1]
    assert "Succeeded" not in str(github.comment.call_args_list)
    assert len(list(runner.artifacts.iterdir())) == 1
    assert "diagnostics" in caplog.text
    if component == "sandbox":
        sandbox.stop.assert_called_once()
    if method in {"start", "setup", "implement", "verify", "commit", "push"}:
        github.publish.assert_not_called()
    if method == "verify":
        sandbox.implement.assert_called_once()


@pytest.mark.parametrize("successful_repair", [1, 2, 3])
def test_repairs_use_latest_feedback_and_stop_at_first_success(runtime, successful_repair: int) -> None:
    from software_factory.sandbox import VerificationFailed

    runner, github, repo, sandbox, _ = runtime
    sandbox.verify.side_effect = [VerificationFailed(f"failure {i}") for i in range(successful_repair)] + [None]
    runner.poll_once()
    assert sandbox.verify.call_count == successful_repair + 1
    assert sandbox.implement.call_count == successful_repair + 1
    initial = sandbox.implement.call_args_list[0]
    for i, repair in enumerate(sandbox.implement.call_args_list[1:]):
        assert repair.args == initial.args
        assert repair.kwargs == {"verification_output": f"failure {i}"}
    sandbox.setup.assert_called_once()
    repo.commit.assert_called_once_with(1)
    repo.push.assert_called_once()
    github.publish.assert_called_once()
    assert "Succeeded:" in github.comment.call_args.args[1]
    assert list(runner.artifacts.iterdir()) == []


def test_three_failed_repairs_retain_artifacts_and_never_publish(runtime) -> None:
    from software_factory.sandbox import VerificationFailed

    runner, github, repo, sandbox, _ = runtime
    sandbox.verify.side_effect = VerificationFailed("private verification transcript")
    runner.poll_once()
    assert sandbox.verify.call_count == 4
    assert sandbox.implement.call_count == 4
    sandbox.stop.assert_called_once()
    repo.commit.assert_not_called()
    github.publish.assert_not_called()
    assert "3 repair attempts" in github.comment.call_args.args[1]
    assert "private verification transcript" not in str(github.comment.call_args_list)
    assert len(list(runner.artifacts.iterdir())) == 1


@pytest.mark.parametrize("phase", ["repair", "reverification"])
@pytest.mark.parametrize("failure", ["issue-run deadline expired", "provider or sandbox failed"])
def test_recovery_failure_aborts_without_another_attempt(runtime, phase: str, failure: str) -> None:
    from software_factory.sandbox import VerificationFailed

    runner, github, repo, sandbox, _ = runtime
    sandbox.verify.side_effect = [VerificationFailed("initial failure"), FactoryError(failure)]
    if phase == "repair":
        sandbox.implement.side_effect = [None, FactoryError(failure)]
    runner.poll_once()
    assert sandbox.implement.call_count == 2
    assert sandbox.verify.call_count == (1 if phase == "repair" else 2)
    sandbox.stop.assert_called_once()
    repo.commit.assert_not_called()
    github.publish.assert_not_called()
    assert failure in github.comment.call_args.args[1]
    assert len(list(runner.artifacts.iterdir())) == 1


@pytest.mark.parametrize("failure", ["no changes produced", "publication failed"])
def test_repaired_changes_still_require_publication_gates(runtime, failure: str) -> None:
    from software_factory.sandbox import VerificationFailed

    runner, github, repo, sandbox, _ = runtime
    sandbox.verify.side_effect = [VerificationFailed("initial failure"), None]
    if failure == "no changes produced":
        repo.commit.side_effect = FactoryError(failure)
    else:
        github.publish.side_effect = FactoryError(failure)
    runner.poll_once()
    assert sandbox.implement.call_count == 2
    assert sandbox.verify.call_count == 2
    assert "Failed:" in github.comment.call_args.args[1]
    assert failure in github.comment.call_args.args[1]
    assert "Succeeded" not in str(github.comment.call_args_list)
    assert len(list(runner.artifacts.iterdir())) == 1


def test_uncertain_push_is_observed_not_repeated(runtime, caplog) -> None:
    runner, github, repo, _, _ = runtime
    repo.push.side_effect = FactoryError("push failed")
    github.branch_exists.side_effect = [False, True]
    runner.poll_once()
    repo.push.assert_called_once()
    github.publish.assert_not_called()
    assert github.branch_exists.call_count == 2
    assert "remote branch exists" in github.comment.call_args.args[1]


def test_uncertain_pr_creation_reports_observed_link_without_success(runtime) -> None:
    runner, github, _, _, _ = runtime
    github.publish.side_effect = FactoryError("PR creation failed")
    github.open_pr.side_effect = [None, "https://github.com/owner/repo/pull/3"]
    runner.poll_once()
    github.publish.assert_called_once()
    assert "Failed:" in github.comment.call_args.args[1]
    assert "https://github.com/owner/repo/pull/3" in github.comment.call_args.args[1]


def test_uncertain_write_observation_failure_remains_visible(runtime, caplog) -> None:
    runner, github, repo, _, _ = runtime
    repo.push.side_effect = FactoryError("push failed")
    github.open_pr.side_effect = [None, FactoryError("read failed")]
    runner.poll_once()
    assert "remote publication state could not be checked" in caplog.text
    assert "Failed:" in github.comment.call_args.args[1]


def test_cleanup_failure_prevents_publication(runtime) -> None:
    runner, github, repo, sandbox, _ = runtime
    sandbox.stop.side_effect = FactoryError("cleanup failed")
    runner.poll_once()
    github.publish.assert_not_called()
    assert "Failed:" in github.comment.call_args.args[1]
    assert sandbox.stop.call_count == 2


def test_cleanup_filesystem_failure_still_reports_and_retains(runtime) -> None:
    runner, github, _, sandbox, _ = runtime
    sandbox.stop.side_effect = OSError("cannot write diagnostics")
    runner.poll_once()
    github.publish.assert_not_called()
    assert "Failed:" in github.comment.call_args.args[1]
    assert len(list(runner.artifacts.iterdir())) == 1


def test_workspace_deletion_failure_is_visible_but_does_not_erase_publication(
    runtime, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    runner, github, *_ = runtime
    monkeypatch.setattr("software_factory.runner.shutil.rmtree", Mock(side_effect=OSError("disk unavailable")))
    runner.poll_once()
    assert "Succeeded:" in github.comment.call_args.args[1]
    assert "Could not remove successful workspace" in caplog.text
    assert len(list(runner.artifacts.iterdir())) == 1


def test_reporting_failure_is_visible_locally_and_not_success(runtime, caplog) -> None:
    runner, github, *_ = runtime
    github.comment.side_effect = FactoryError("reporting failed")
    runner.poll_once()
    assert "reporting failed" in caplog.text
    assert "GitHub failure reporting unavailable" in caplog.text


def test_operator_stop_cleans_up_retains_workspace_and_propagates(runtime) -> None:
    runner, github, _, sandbox, _ = runtime
    sandbox.implement.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        runner.poll_once()
    sandbox.stop.assert_called_once()
    github.publish.assert_not_called()
    assert "operator interruption" in github.comment.call_args.args[1]
    assert len(list(runner.artifacts.iterdir())) == 1


def test_polling_is_serial_and_does_not_resume_artifacts(runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    runner, github, _, _, _ = runtime
    old = runner.artifacts / "old-failure"
    runner.artifacts.mkdir(parents=True, exist_ok=True)
    old.mkdir()
    github.discover.side_effect = [[1, 2], []]
    processed = []
    monkeypatch.setattr(runner, "process_issue", processed.append)
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr("software_factory.runner.time.sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert processed == [1, 2]
    assert sleeps == [30, 30]
    assert old.exists()


def test_requeue_preserves_open_pr_and_consumes_trigger_once(runtime) -> None:
    from software_factory.runner import Runner

    runner, github, repo, sandbox, _ = runtime
    queued = {"value": True}
    github.discover.side_effect = lambda: [1] if queued["value"] else []
    github.remove_trigger.side_effect = lambda number: queued.update(value=False)
    sandbox.implement.side_effect = FactoryError("provider unavailable")
    runner.poll_once()
    previous = next(runner.artifacts.iterdir())
    github.open_pr.return_value = "https://github.com/owner/repo/pull/3"
    runner = Runner(runner.config, runner.prepared, runner.artifacts)
    runner.poll_once()
    assert github.comment.call_count == 2
    queued["value"] = True
    runner.poll_once()
    assert github.comment.call_args.args == (1, "Skipped: existing open PR https://github.com/owner/repo/pull/3")
    assert not queued["value"]
    runner.poll_once()
    assert github.comment.call_count == 3
    repo.checkout.assert_called_once()
    sandbox.implement.assert_called_once()
    github.publish.assert_not_called()
    assert list(runner.artifacts.iterdir()) == [previous]


def test_startup_checks_tooling_and_resolves_with_sanitized_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from software_factory.runner import preflight

    config = Config("owner/repo", tmp_path / "compose.yaml", "agent", "chosen")
    commands = Mock()
    placeholder = tmp_path / "artifacts" / ".workspace-placeholder"
    commands.run.side_effect = ["ok", "ok", "ok", json.dumps(prepared_compose(placeholder))]
    monkeypatch.setattr("software_factory.runner.shutil.which", lambda tool: "/bin/" + tool)
    monkeypatch.setattr("software_factory.runner.Commands", Mock(return_value=commands))
    monkeypatch.setenv("GH_TOKEN", "host-secret")
    data = preflight(config)
    assert data["services"]["agent"]["volumes"][0]["source"] == str(placeholder)
    assert data["services"]["agent"]["image"]
    compose_call = commands.run.call_args
    assert "GH_TOKEN" not in compose_call.kwargs["env"]
    assert compose_call.kwargs["env"]["FACTORY_WORKSPACE"] == str(placeholder)


def test_startup_fails_when_tool_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from software_factory.runner import preflight

    monkeypatch.setattr("software_factory.runner.shutil.which", lambda _: None)
    with pytest.raises(FactoryError, match="required tool"):
        preflight(Config("owner/repo", tmp_path / "compose.yaml", "agent", "model"))
