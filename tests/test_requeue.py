import os
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from tests_support import prepared_compose

from software_factory.config import Config
from software_factory.process import Commands, FactoryError
from software_factory.repository import Repository
from software_factory.runner import Runner
from software_factory.sandbox import Sandbox, VerificationFailed, prepare_compose


@pytest.mark.parametrize(
    "docker,first_outcome",
    [
        (False, "failure"),
        (False, "interruption"),
        (False, "exhaustion"),
        (False, "deadline"),
        (False, "publication"),
        pytest.param(True, "failure", marks=pytest.mark.docker),
        pytest.param(True, "interruption", marks=pytest.mark.docker),
    ],
)
def test_operator_requeues_into_fresh_run_without_resuming_failed_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker: bool, first_outcome: str
) -> None:
    if docker and os.environ.get("FACTORY_DOCKER_TESTS") != "1":
        pytest.skip("set FACTORY_DOCKER_TESTS=1 for real Docker tests")
    origin = tmp_path / "origin"
    scripts = origin / "scripts"
    scripts.mkdir(parents=True)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(origin), *args], text=True, stderr=subprocess.DEVNULL).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@localhost")
    for name, body in [
        ("setup", "touch prepared"),
        ("verify", "echo 'implementation missing' >&2; test -f prepared && test -f implemented"),
    ]:
        script = scripts / name
        script.write_text("#!/bin/sh\nset -eu\n" + body + "\n")
        script.chmod(0o755)
    (origin / "baseline").write_text("original\n")
    git("add", ".")
    git("commit", "-m", "original baseline")

    state = {"queued": True, "title": "original title", "body": "original body", "pr": None}
    github = Mock()
    github.discover.side_effect = lambda: [1] if state["queued"] else []
    github.remove_trigger.side_effect = lambda number: state.update(queued=False)
    github.open_pr.side_effect = lambda number: state["pr"]
    github.branch_exists.side_effect = lambda number: bool(git("branch", "--list", "factory/issue-1"))
    github.snapshot.side_effect = lambda number: {"number": number, "title": state["title"], "body": state["body"]}
    github.default_branch.return_value = "main"

    def publish(*args):
        if first_outcome == "publication" and len(runs) == 1:
            raise FactoryError("PR creation failed")
        state["pr"] = "https://github.com/owner/repo/pull/2"
        return state["pr"]

    github.publish.side_effect = publish
    runs = []
    sandboxes = []

    class LocalRepository(Repository):
        def checkout(self, url, branch):
            runs.append(self)
            self.starting_deadline = self.commands.deadline
            return super().checkout(str(origin), branch)

        def push(self, url, number):
            super().push(str(origin), number)

    class AuthenticatedCommands(Commands):
        def run(self, args, phase, **kwargs):
            if phase == "Copilot authentication":
                return f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}"
            return super().run(args, phase, **kwargs)

    class ScriptedSandbox(Sandbox):
        def __init__(self, *args):
            super().__init__(*args)
            self.snapshots = []
            self.feedback = []
            sandboxes.append(self)

        def start(self):
            if docker:
                super().start()

        def setup(self):
            if docker:
                super().setup()

        def implement(self, snapshot, *args, verification_output=None):
            self.snapshots.append(snapshot.copy())
            self.feedback.append(verification_output)
            workspace = runs[-1].workspace
            if len(runs) == 1:
                (workspace / "private-failed-work").write_text("do not resume or erase\n")
                self.commands.run(["printf", "retained diagnostic\n"], "test diagnostic")
                if first_outcome == "interruption":
                    raise KeyboardInterrupt
                if first_outcome == "failure":
                    raise FactoryError("provider unavailable")
                if first_outcome == "deadline":
                    self.commands.deadline = time.monotonic() - 1
                    self.commands.run(["true"], "expired implementation")
            else:
                assert not (workspace / "private-failed-work").exists()
                assert (workspace / "baseline").read_text() == "updated default branch\n"
            if (len(runs) == 2 and len(self.feedback) == 4) or first_outcome == "publication":
                if docker:
                    self.commands.run(self.base + ["exec", "-T", self.service, "touch", "implemented"], "test agent")
                else:
                    (workspace / "implemented").touch()

        def verify(self):
            if docker:
                super().verify()
            elif not (runs[-1].workspace / "implemented").exists():
                raise VerificationFailed("implementation missing")

        def stop(self):
            if docker:
                super().stop()

    monkeypatch.setattr("software_factory.runner.GitHub", Mock(return_value=github))
    monkeypatch.setattr("software_factory.runner.Repository", LocalRepository)
    monkeypatch.setattr("software_factory.runner.Commands", AuthenticatedCommands)
    monkeypatch.setattr("software_factory.runner.Sandbox", ScriptedSandbox)
    config = Config("owner/repo", tmp_path / "compose.yaml", "agent", "chosen")
    prepared = prepare_compose(prepared_compose(tmp_path), "agent", tmp_path)
    artifacts = tmp_path / "artifacts"
    runner = Runner(config, prepared, artifacts)
    started = time.monotonic()
    if first_outcome == "interruption":
        with pytest.raises(KeyboardInterrupt):
            runner.poll_once()
    else:
        runner.poll_once()
    assert not state["queued"]
    assert state["pr"] is None
    assert github.comment.call_args.args[1].startswith("Failed:")
    previous = runs[0]
    retained = {
        path: path.read_bytes() for path in [previous.directory / "run.log", previous.workspace / "private-failed-work"]
    }
    comments = github.comment.call_count

    # A new runner sees the same diagnostics and GitHub state, but has no permission to resume.
    runner = Runner(config, prepared, artifacts)
    runner.poll_once()
    assert len(runs) == 1
    assert github.comment.call_count == comments
    state.update(title="edited title", body="edited body")
    (origin / "baseline").write_text("updated default branch\n")
    git("add", ".")
    git("commit", "-m", "updated default branch")
    current_base = git("rev-parse", "main")

    if first_outcome == "publication":
        state["queued"] = True
        runner.poll_once()
        assert not state["queued"]
        assert "delete remote factory/issue-1" in github.comment.call_args.args[1]
        assert len(runs) == 1
        comments = github.comment.call_count
        runner.poll_once()
        assert github.comment.call_count == comments
        # Only the operator removes the orphan branch; deletion alone does not requeue.
        git("branch", "-D", "factory/issue-1")
        runner.poll_once()
        assert len(runs) == 1

    state["queued"] = True
    runner.poll_once()
    assert len(runs) == 2
    current = runs[1]
    assert current.workspace != previous.workspace
    assert started + 900 <= previous.starting_deadline < current.starting_deadline <= time.monotonic() + 900
    expected = {"number": 1, "title": "edited title", "body": "edited body", "base_commit": current_base}
    assert all(snapshot == expected for snapshot in sandboxes[1].snapshots)
    assert sandboxes[0].snapshots[0]["title"] == "original title"
    assert sandboxes[1].feedback[0] is None
    assert len(sandboxes[1].feedback) == (1 if first_outcome == "publication" else 4)
    assert all("implementation missing" in output for output in sandboxes[1].feedback[1:])
    assert "Succeeded:" in github.comment.call_args.args[1]
    assert not state["queued"]
    assert git("rev-parse", "factory/issue-1~1") == current_base
    assert not current.directory.exists()
    assert list(artifacts.iterdir()) == [previous.directory]
    assert all(path.read_bytes() == content for path, content in retained.items())
    if docker:
        for sandbox in sandboxes:
            ids = subprocess.check_output(
                ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={sandbox.project}"], text=True
            )
            assert ids.strip() == ""
