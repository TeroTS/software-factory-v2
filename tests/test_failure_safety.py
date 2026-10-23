import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from software_factory.process import Commands, FactoryError


def test_timeout_retains_partial_redacted_output(tmp_path: Path) -> None:
    commands = Commands(time.monotonic() + 0.2, tmp_path / "run.log")
    commands.secrets.append("private-token")
    with pytest.raises(FactoryError, match="deadline"):
        commands.run([sys.executable, "-u", "-c", "import time; print('private-token'); time.sleep(2)"], "setup")
    assert "[REDACTED]" in (tmp_path / "run.log").read_text()
    assert "private-token" not in (tmp_path / "run.log").read_text()


def test_command_output_can_contain_invalid_utf8() -> None:
    assert "\ufffd" in Commands().run([sys.executable, "-c", "import os; os.write(1, b'\\xff')"], "setup")


def test_exit_race_does_not_hide_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    process = Mock()
    process.communicate.side_effect = [subprocess.TimeoutExpired("tool", 1), ("", "")]
    monkeypatch.setattr("software_factory.process.subprocess.Popen", Mock(return_value=process))
    monkeypatch.setattr("software_factory.process.os.killpg", Mock(side_effect=ProcessLookupError()))
    with pytest.raises(FactoryError, match="deadline"):
        Commands().run(["tool"], "setup")


def test_interruption_kills_child_and_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    process = Mock()
    process.communicate.side_effect = [KeyboardInterrupt(), ("partial", "")]
    monkeypatch.setattr("software_factory.process.subprocess.Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr("software_factory.process.os.killpg", kill)
    with pytest.raises(KeyboardInterrupt):
        Commands().run(["tool"], "setup")
    kill.assert_called_once_with(process.pid, signal.SIGKILL)
