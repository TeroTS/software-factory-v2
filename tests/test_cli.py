import signal
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
