import json
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


def test_cli_starts_preflight_then_polling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from software_factory.__main__ import main

    config = Mock()
    runner = Mock()
    monkeypatch.setattr("sys.argv", ["software_factory", "--config", str(tmp_path / "factory.toml")])
    monkeypatch.setattr("software_factory.__main__.load_config", Mock(return_value=config))
    runtime = Mock(image_id="sha256:resolved", docker_host="unix:///var/run/docker.sock")
    preflight = Mock(return_value=runtime)
    monkeypatch.setattr("software_factory.__main__.preflight", preflight)
    constructor = Mock(return_value=runner)
    monkeypatch.setattr("software_factory.__main__.Runner", constructor)
    assert main() == 0
    preflight.assert_called_once_with(config)
    constructor.assert_called_once_with(config, runtime)
    runner.run.assert_called_once()


def test_cli_operator_stop_is_not_startup_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from software_factory.__main__ import main

    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr("sys.argv", ["software_factory", "--config", "factory.toml"])
    monkeypatch.setattr("software_factory.__main__.load_config", Mock(side_effect=KeyboardInterrupt()))
    assert main() == 130
    assert signal.getsignal(signal.SIGTERM) == previous


def test_startup_filesystem_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    from software_factory.__main__ import main

    monkeypatch.setattr("sys.argv", ["software_factory", "--config", "factory.toml"])
    monkeypatch.setattr("software_factory.__main__.load_config", Mock(side_effect=OSError("private-detail")))
    assert main() == 1
    assert "Cannot initialize local factory files" in caplog.text
    assert "private-detail" not in caplog.text


def test_cli_startup_factory_error_is_nonzero_and_safe(monkeypatch, caplog) -> None:
    from software_factory.__main__ import main
    from software_factory.process import FactoryError

    monkeypatch.setattr("sys.argv", ["software_factory", "--config", "factory.toml"])
    monkeypatch.setattr(
        "software_factory.__main__.load_config", Mock(side_effect=FactoryError("invalid configuration"))
    )
    assert main() == 1
    assert "invalid configuration" in caplog.text


def test_sigterm_becomes_cleanup_capable_interruption() -> None:
    from software_factory.__main__ import stop

    with pytest.raises(KeyboardInterrupt):
        stop(signal.SIGTERM, None)


def test_cli_default_logs_info_and_interruption_as_json_stderr(tmp_path: Path) -> None:
    config = tmp_path / "factory.toml"
    config.write_text('repository = "owner/repo"\nmodel = "chosen"\nagent_image = "agent:local"\n')
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from unittest.mock import patch; "
            "from software_factory.__main__ import main; "
            "from software_factory.runner import AgentRuntime; "
            "runtime = AgentRuntime('sha256:resolved', 'unix:///local.sock'); "
            "startup = patch('software_factory.__main__.preflight', return_value=runtime); startup.start(); "
            "poll = patch('software_factory.runner.Runner.poll_once', side_effect=KeyboardInterrupt); poll.start(); "
            "raise SystemExit(main())",
            "--config",
            str(config),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 130
    assert result.stdout == ""
    records = [json.loads(line) for line in result.stderr.splitlines()]
    polling = next(record for record in records if record["event"] == "runner_polling")
    assert polling["level"] == "INFO" and polling["repository"] == "owner/repo"
    assert records[-1]["event"] == "runner_interrupted"
    assert records[-1]["repository"] == "owner/repo"
    assert all({"timestamp", "level", "event", "message"} <= record.keys() for record in records)


def test_cli_startup_failure_is_json_without_raw_input(tmp_path: Path) -> None:
    config = tmp_path / "factory.toml"
    config.write_text("private-invalid-input")
    result = subprocess.run(
        [sys.executable, "-m", "software_factory", "--config", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    record = json.loads(result.stderr)
    assert record["event"] == "runner_failed" and record["level"] == "ERROR"
    assert "Cannot read configuration" in record["message"]
    assert "repository" not in record and "issue" not in record
    assert "private-invalid-input" not in result.stderr


@pytest.mark.parametrize("selected", ["agent:local", "other-agent:local"])
def test_cli_validates_selected_agent_before_preflight(tmp_path: Path, monkeypatch, caplog, selected: str) -> None:
    from software_factory.__main__ import main

    config = tmp_path / "factory.toml"
    config.write_text('repository="owner/repo"\nmodel="chosen"\nagent_image="agent:local"\n')
    monkeypatch.setattr("sys.argv", ["software_factory", "--config", str(config)])
    monkeypatch.setenv("AGENT_IMAGE", selected)
    startup = Mock(return_value=Mock())
    runner = Mock()
    monkeypatch.setattr("software_factory.__main__.preflight", startup)
    monkeypatch.setattr("software_factory.__main__.Runner", Mock(return_value=runner))
    assert main() == (0 if selected == "agent:local" else 1)
    if selected == "agent:local":
        startup.assert_called_once()
        runner.run.assert_called_once()
    else:
        startup.assert_not_called()
        runner.run.assert_not_called()
        assert "agent_image must match the selected AGENT_IMAGE" in caplog.text
