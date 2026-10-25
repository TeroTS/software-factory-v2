import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from software_factory.config import Config
from software_factory.process import FactoryError
from software_factory.runner import AgentRuntime, Runner
from software_factory.sandbox import PI_FLAGS, VerificationFailed


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    config = Config("owner/repo", "chosen", "agent:local", artifacts)
    commands = Mock()
    commands.secrets = []
    commands.run.return_value = f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}"
    github = Mock()
    github.discover.return_value = [1]
    github.open_pr.return_value = None
    github.branch_exists.return_value = False
    github.snapshot.return_value = {"number": 1, "title": "task", "body": None}
    github.default_branch.return_value = "main"
    github.publish.return_value = "https://github.com/owner/repo/pull/3"
    repo = Mock()
    repo.checkout.return_value = "a" * 40
    sandbox = Mock()

    def command_factory(**kwargs):
        commands.deadline = kwargs.get("deadline")
        return commands

    monkeypatch.setattr("software_factory.runner.Commands", command_factory)
    monkeypatch.setattr("software_factory.runner.GitHub", Mock(return_value=github))
    monkeypatch.setattr("software_factory.runner.Repository", Mock(return_value=repo), raising=False)
    monkeypatch.setattr("software_factory.runner.Sandbox", Mock(return_value=sandbox), raising=False)
    runner = Runner(config, AgentRuntime("sha256:" + "a" * 64, "unix:///local.sock"))
    return runner, github, repo, sandbox, commands


def test_first_pass_claim_setup_verify_cleanup_publish_order(runtime) -> None:
    runner, github, repo, sandbox, commands = runtime
    events = Mock()
    for name, obj in [("github", github), ("repo", repo), ("sandbox", sandbox)]:
        events.attach_mock(obj, name)
    runner.poll_once()
    assert [call[0] for call in events.mock_calls] == [
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
    assert sandbox.implement.call_args.args[0] == {"number": 1, "title": "task", "body": None, "base_commit": "a" * 40}
    assert github.comment.call_args.args == (1, "Succeeded: https://github.com/owner/repo/pull/3")
    assert list(runner.artifacts.iterdir()) == []
    assert len(commands.secrets) == 1
    auth = commands.run.call_args
    assert auth.args == (
        [
            "pi",
            "auth",
            "print-bearer-token",
            "--provider",
            "github-copilot",
            "--min-expiry",
            "20m",
            *PI_FLAGS,
            "--no-context-files",
            "--offline",
        ],
        "Copilot authentication",
    )
    assert auth.kwargs["private"] is True
    assert auth.kwargs["cwd"].parent == runner.artifacts
    assert sandbox.implement.call_args.args[1] == commands.secrets[0]


@pytest.mark.parametrize("duplicate", ["pr", "branch"])
def test_duplicate_skip_removes_trigger_before_comment_without_workspace(runtime, duplicate) -> None:
    runner, github, repo, sandbox, _ = runtime
    if duplicate == "pr":
        github.open_pr.return_value = "https://github.com/owner/repo/pull/3"
    else:
        github.branch_exists.return_value = True
    runner.poll_once()
    names = [call[0] for call in github.mock_calls]
    assert names.index("remove_trigger") < names.index("comment")
    assert "Skipped:" in github.comment.call_args.args[1]
    if duplicate == "branch":
        assert "reapply" in github.comment.call_args.args[1]
    repo.checkout.assert_not_called()
    sandbox.start.assert_not_called()
    assert list(runner.artifacts.iterdir()) == []


@pytest.mark.parametrize("phase", ["open_pr", "branch_exists", "remove_trigger"])
def test_preclaim_failure_never_executes_or_guesses_label_state(runtime, phase, caplog) -> None:
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
        ("github", "default_branch"),
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
def test_failure_retains_private_diagnostics_without_false_success(runtime, component, method, caplog) -> None:
    runner, github, repo, sandbox, _ = runtime
    getattr({"github": github, "repo": repo, "sandbox": sandbox}[component], method).side_effect = FactoryError(
        f"{method} failed"
    )
    runner.poll_once()
    assert github.comment.call_args.args[1].startswith("Failed:")
    assert "Succeeded:" not in str(github.comment.call_args_list)
    directory = next(runner.artifacts.iterdir())
    assert directory.stat().st_mode & 0o777 == 0o700
    assert "diagnostics" in caplog.text
    if component == "sandbox":
        sandbox.stop.assert_called_once()
    if method == "start":
        sandbox.setup.assert_not_called()
        sandbox.implement.assert_not_called()
        repo.commit.assert_not_called()
    if method == "setup":
        sandbox.implement.assert_not_called()


def test_verification_failure_is_not_repaired_in_first_pass_slice(runtime) -> None:
    runner, github, repo, sandbox, _ = runtime
    sandbox.verify.side_effect = VerificationFailed("private transcript")
    runner.poll_once()
    sandbox.implement.assert_called_once()
    sandbox.verify.assert_called_once()
    sandbox.stop.assert_called_once()
    repo.commit.assert_not_called()
    assert github.comment.call_args.args[1] == "Failed: verification failed"


@pytest.mark.parametrize("failure", [FactoryError("cleanup failed"), OSError("private filesystem detail")])
def test_cleanup_failure_blocks_publication_and_retains_diagnostics(runtime, failure) -> None:
    runner, github, repo, sandbox, _ = runtime
    sandbox.stop.side_effect = failure
    runner.poll_once()
    repo.commit.assert_not_called()
    github.publish.assert_not_called()
    assert github.comment.call_args.args[1].startswith("Failed:")
    assert "private filesystem detail" not in github.comment.call_args.args[1]
    assert len(list(runner.artifacts.iterdir())) == 1


@pytest.mark.parametrize("failure", [FactoryError("push failed"), OSError("private diagnostics write failed")])
def test_uncertain_push_is_observed_not_repeated(runtime, failure) -> None:
    runner, github, repo, _, _ = runtime
    repo.push.side_effect = failure
    github.branch_exists.side_effect = [False, True]
    runner.poll_once()
    repo.push.assert_called_once()
    github.publish.assert_not_called()
    assert github.branch_exists.call_count == 2
    assert "remote branch exists" in github.comment.call_args.args[1]
    assert "private diagnostics write failed" not in github.comment.call_args.args[1]


def test_cleanup_failure_preserves_original_safe_execution_error(runtime) -> None:
    runner, github, repo, sandbox, _ = runtime
    sandbox.setup.side_effect = FactoryError("setup failed")
    sandbox.stop.side_effect = FactoryError("cleanup failed")
    runner.poll_once()
    assert "setup failed" in github.comment.call_args.args[1]
    assert "run cleanup failed" in github.comment.call_args.args[1]
    repo.commit.assert_not_called()


def test_uncertain_pr_reports_observed_link_without_success(runtime) -> None:
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


def test_reporting_failure_remains_visible_locally(runtime, caplog) -> None:
    runner, github, *_ = runtime
    github.comment.side_effect = FactoryError("reporting failed")
    runner.poll_once()
    assert "reporting failed" in caplog.text
    assert "GitHub failure reporting unavailable" in caplog.text


def test_filesystem_failure_has_safe_failure_status(runtime) -> None:
    runner, github, repo, _, _ = runtime
    repo.checkout.side_effect = OSError("private filesystem detail")
    runner.poll_once()
    assert github.comment.call_args.args[1].startswith("Failed: local filesystem operation failed")
    assert "private filesystem detail" not in str(github.comment.call_args_list)


def test_invalid_run_bearer_prevents_pi_and_still_cleans(runtime) -> None:
    runner, github, repo, sandbox, commands = runtime
    commands.run.return_value = "sensitive-invalid-bearer"
    runner.poll_once()
    sandbox.implement.assert_not_called()
    sandbox.stop.assert_called_once()
    repo.commit.assert_not_called()
    assert "sensitive-invalid-bearer" not in str(github.comment.call_args_list)


def test_interruption_is_preserved_even_when_cleanup_also_fails(runtime, caplog) -> None:
    runner, github, repo, sandbox, _ = runtime
    sandbox.implement.side_effect = KeyboardInterrupt()
    sandbox.stop.side_effect = FactoryError("cleanup failed")
    with pytest.raises(KeyboardInterrupt):
        runner.poll_once()
    assert "cleanup failed" in caplog.text
    assert "operator interruption" in github.comment.call_args.args[1]
    repo.commit.assert_not_called()


def test_unexpected_execution_error_still_attempts_cleanup_before_propagating(runtime) -> None:
    runner, _, repo, sandbox, _ = runtime
    sandbox.implement.side_effect = RuntimeError("unexpected internal failure")
    with pytest.raises(RuntimeError):
        runner.poll_once()
    sandbox.stop.assert_called_once()
    repo.commit.assert_not_called()


def test_stop_cleans_retains_reports_and_propagates(runtime) -> None:
    runner, github, repo, sandbox, _ = runtime
    sandbox.implement.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        runner.poll_once()
    sandbox.stop.assert_called_once()
    repo.commit.assert_not_called()
    assert "operator interruption" in github.comment.call_args.args[1]
    assert len(list(runner.artifacts.iterdir())) == 1


def test_deadline_after_cleanup_prevents_even_starting_commit(runtime, monkeypatch) -> None:
    runner, github, repo, sandbox, _ = runtime
    clock = [100.0]
    monkeypatch.setattr("software_factory.runner.time.monotonic", lambda: clock[0])
    sandbox.stop.side_effect = lambda: clock.__setitem__(0, 1001.0)
    runner.poll_once()
    repo.commit.assert_not_called()
    assert "deadline" in github.comment.call_args.args[1]


def test_old_artifacts_and_serial_polling_are_preserved(runtime, monkeypatch) -> None:
    runner, github, _, _, _ = runtime
    old = runner.artifacts / "old-failure"
    old.mkdir()
    (old / "run.log").write_text("retained")
    github.discover.side_effect = [[1, 2], []]
    processed = []
    monkeypatch.setattr(runner, "process_issue", processed.append)
    sleeps = Mock(side_effect=[None, KeyboardInterrupt()])
    monkeypatch.setattr("software_factory.runner.time.sleep", sleeps)
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert processed == [1, 2]
    assert [call.args for call in sleeps.call_args_list] == [(30,), (30,)]
    assert (old / "run.log").read_text() == "retained"


def test_successful_workspace_removal_failure_does_not_erase_publication(runtime, monkeypatch, caplog) -> None:
    runner, github, *_ = runtime
    monkeypatch.setattr("software_factory.runner.shutil.rmtree", Mock(side_effect=OSError("disk unavailable")))
    runner.poll_once()
    assert github.comment.call_args.args[1].startswith("Succeeded:")
    assert "Could not remove successful workspace" in caplog.text
