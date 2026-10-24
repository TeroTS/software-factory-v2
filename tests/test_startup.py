import json
import time
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from software_factory.config import Config
from software_factory.process import FactoryError
from software_factory.runner import Runner, preflight

IMAGE_ID = "sha256:" + "a" * 64


@pytest.fixture
def startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = Config("owner/repo", "chosen", "agent:v1", tmp_path / "artifacts")
    commands = Mock()
    responses = {
        "Docker context": json.dumps([{"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}}]),
        "Docker readiness": json.dumps({"OSType": "linux", "Architecture": "aarch64"}),
        "agent image": json.dumps([{"Id": IMAGE_ID, "Os": "linux", "Architecture": "arm64"}]),
        "Copilot authentication": f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}",
    }
    commands.run.side_effect = lambda args, phase, **kwargs: responses.get(phase, "")
    monkeypatch.setattr("software_factory.runner.shutil.which", lambda tool: "/bin/" + tool)
    monkeypatch.setattr("software_factory.runner.Commands", Mock(return_value=commands))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    return config, commands, responses


def test_startup_resolves_local_image_and_checks_execution_without_claims(startup, monkeypatch) -> None:
    config, commands, _ = startup
    monkeypatch.setenv("GH_TOKEN", "host-secret")
    runtime = preflight(config)
    assert runtime.image_id == IMAGE_ID
    assert runtime.docker_host == "unix:///var/run/docker.sock"
    assert config.artifacts_dir.is_dir()
    calls = commands.run.call_args_list
    phases = [call.args[1] for call in calls]
    assert "GitHub authentication" in phases
    auth = next(call for call in calls if call.args[1] == "Copilot authentication")
    assert auth.kwargs["private"] is True
    assert "--no-context-files" in auth.args[0] and "--offline" in auth.args[0]
    assert "agent runtime" in phases
    assert phases[-1] == "startup cleanup"
    assert "--volumes" in calls[-1].args[0], "remove any anonymous volumes declared by the trusted probe image"
    image_call = next(call for call in calls if call.args[1] == "agent image")
    assert image_call.args[0][-1] == config.agent_image
    probe = next(call for call in calls if call.args[1] == "agent runtime")
    assert IMAGE_ID in probe.args[0]
    assert "--pull=never" in probe.args[0]
    assert "linux/arm64" in probe.args[0]
    assert not any("mount" in arg or arg == "-v" for arg in probe.args[0])
    for command in calls:
        assert "GH_TOKEN" not in command.kwargs.get("env", {})
    assert not any("pull" == arg or "build" == arg for call in calls for arg in call.args[0])


@pytest.mark.parametrize("architecture", ["arm64", "aarch64"])
def test_native_arm64_engine_aliases_are_supported(startup, architecture: str) -> None:
    _, _, responses = startup
    responses["Docker readiness"] = json.dumps({"OSType": "linux", "Architecture": architecture})
    preflight(startup[0])


@pytest.mark.parametrize("tool", ["git", "gh", "docker", "pi"])
def test_missing_tools_fail_before_engine_calls(startup, monkeypatch, tool: str) -> None:
    config, commands, _ = startup
    monkeypatch.setattr("software_factory.runner.shutil.which", lambda name: None if name == tool else "/bin/tool")
    with pytest.raises(FactoryError, match="required tool unavailable: " + tool):
        preflight(config)
    commands.run.assert_not_called()


@pytest.mark.parametrize("endpoint", ["ssh://host", "tcp://127.0.0.1:2375", "unix://relative", "", "http://host"])
def test_remote_or_invalid_docker_endpoints_fail_closed(startup, endpoint: str) -> None:
    config, commands, responses = startup
    responses["Docker context"] = json.dumps([{"Endpoints": {"docker": {"Host": endpoint}}}])
    with pytest.raises(FactoryError, match="local.*unix"):
        preflight(config)
    assert "agent runtime" not in [call.args[1] for call in commands.run.call_args_list]


def test_docker_host_override_cannot_hide_remote_engine(startup, monkeypatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote:2375")
    with pytest.raises(FactoryError, match="local.*unix"):
        preflight(startup[0])


def test_explicit_context_takes_precedence_over_docker_host(startup, monkeypatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://ignored:2375")
    monkeypatch.setenv("DOCKER_CONTEXT", "local-context")
    runtime = preflight(startup[0])
    assert runtime.docker_host == "unix:///var/run/docker.sock"
    docker_calls = [call for call in startup[1].run.call_args_list if call.args[1] == "Docker readiness"]
    assert docker_calls[0].kwargs["env"]["DOCKER_HOST"] == runtime.docker_host
    assert "DOCKER_CONTEXT" not in docker_calls[0].kwargs["env"]


@pytest.mark.parametrize(
    "phase,payload",
    [
        ("Docker context", "not-json"),
        ("Docker context", "[]"),
        ("Docker context", "{}"),
        ("Docker readiness", "null"),
        ("Docker readiness", '{"OSType":"windows","Architecture":"arm64"}'),
        ("Docker readiness", '{"OSType":"linux","Architecture":"x86_64"}'),
        ("agent image", "[]"),
        ("agent image", "null"),
        ("agent image", '[{"Id":"bad","Os":"linux","Architecture":"arm64"}]'),
        ("agent image", json.dumps([{"Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64"}])),
        ("agent image", json.dumps([{"Id": IMAGE_ID, "Os": "windows", "Architecture": "arm64"}])),
    ],
)
def test_malformed_or_incompatible_engine_and_image_fail_startup(startup, phase: str, payload: str) -> None:
    config, _, responses = startup
    responses[phase] = payload
    with pytest.raises(FactoryError):
        preflight(config)


@pytest.mark.parametrize(
    "phase",
    [
        "Docker readiness",
        "agent image",
        "GitHub authentication",
        "Copilot authentication",
        "agent runtime",
        "startup cleanup",
    ],
)
def test_boundary_failures_are_actionable_and_never_reach_polling(startup, phase: str) -> None:
    config, commands, responses = startup

    def run(args, current, **kwargs):
        if current == phase:
            raise FactoryError(current + " failed")
        return responses.get(current, "")

    commands.run.side_effect = run
    with pytest.raises(FactoryError):
        preflight(config)
    if phase == "agent runtime":
        assert commands.run.call_args.args[1] == "startup cleanup"


def test_interrupted_runtime_probe_still_attempts_cleanup(startup) -> None:
    config, commands, responses = startup

    def run(args, phase, **kwargs):
        if phase == "agent runtime":
            raise KeyboardInterrupt
        return responses.get(phase, "")

    commands.run.side_effect = run
    with pytest.raises(KeyboardInterrupt):
        preflight(config)
    assert commands.run.call_args.args[1] == "startup cleanup"


def test_interruption_is_not_hidden_by_cleanup_failure(startup, caplog) -> None:
    config, commands, responses = startup

    def run(args, phase, **kwargs):
        if phase == "agent runtime":
            raise KeyboardInterrupt
        if phase == "startup cleanup":
            raise FactoryError("cleanup failed")
        return responses.get(phase, "")

    commands.run.side_effect = run
    with pytest.raises(KeyboardInterrupt):
        preflight(config)
    assert "startup probe" in caplog.text


def test_invalid_copilot_authentication_does_not_expose_token_or_start_container(startup) -> None:
    config, commands, responses = startup
    responses["Copilot authentication"] = "sensitive-invalid-bearer"
    with pytest.raises(FactoryError) as failure:
        preflight(config)
    assert "sensitive-invalid-bearer" not in str(failure.value)
    assert "agent runtime" not in [call.args[1] for call in commands.run.call_args_list]
    assert list(config.artifacts_dir.iterdir()) == []


def test_artifact_root_file_is_rejected_without_touching_existing_contents(startup) -> None:
    config, commands, _ = startup
    config.artifacts_dir.write_text("previous diagnostics")
    with pytest.raises(FactoryError, match="artifacts_dir"):
        preflight(config)
    assert config.artifacts_dir.read_text() == "previous diagnostics"
    commands.run.assert_not_called()


def test_artifact_probe_failure_is_safe(startup, monkeypatch) -> None:
    monkeypatch.setattr("software_factory.runner.tempfile.TemporaryFile", Mock(side_effect=PermissionError("secret")))
    with pytest.raises(FactoryError, match="artifacts_dir") as failure:
        preflight(startup[0])
    assert "secret" not in str(failure.value)


def test_startup_preserves_previous_artifacts(startup) -> None:
    config, _, _ = startup
    previous = config.artifacts_dir / "issue-1-failed"
    previous.mkdir(parents=True)
    (previous / "run.log").write_text("retained private data")
    preflight(config)
    assert list(config.artifacts_dir.iterdir()) == [previous]
    assert (previous / "run.log").read_text() == "retained private data"


def test_polling_and_direct_dispatch_are_guarded_before_any_write(startup, monkeypatch, caplog) -> None:
    config, _, _ = startup
    runtime = preflight(config)
    github = Mock()
    github.discover.return_value = [1, 2]
    monkeypatch.setattr("software_factory.runner.GitHub", Mock(return_value=github))
    runner = Runner(config, runtime)
    runner.poll_once()
    runner.process_issue(3)
    assert github.mock_calls == [call.discover()]
    assert list(config.artifacts_dir.iterdir()) == []
    assert "US-05" in caplog.text
    assert "not claimed" in caplog.text
    assert runner.runtime.image_id == IMAGE_ID


def test_runner_polls_every_thirty_seconds_and_survives_discovery_errors(startup, monkeypatch, caplog) -> None:
    config, _, _ = startup
    runner = Runner(config, preflight(config))
    polls = Mock(side_effect=[FactoryError("GitHub unavailable"), None])
    monkeypatch.setattr(runner, "poll_once", polls)
    sleep = Mock(side_effect=[None, KeyboardInterrupt()])
    monkeypatch.setattr("software_factory.runner.time.sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert [call.args for call in sleep.call_args_list] == [(30,), (30,)]
    assert "GitHub unavailable" in caplog.text
    assert "execution disabled" in caplog.text
