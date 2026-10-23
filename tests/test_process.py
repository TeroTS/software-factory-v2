import os
import sys
import time
from pathlib import Path

import pytest


def test_command_captures_output_and_private_log(tmp_path: Path) -> None:
    from software_factory.process import Commands

    log = tmp_path / "run.log"
    commands = Commands(time.monotonic() + 5, log)
    assert commands.run([sys.executable, "-c", "print('hello')"], "test").strip() == "hello"
    assert "hello" in log.read_text()
    assert log.stat().st_mode & 0o077 == 0


def test_secrets_never_logged_or_in_failures(tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError

    commands = Commands(time.monotonic() + 5, tmp_path / "run.log")
    commands.secrets.append("secret-value")
    with pytest.raises(FactoryError, match="test failed") as error:
        commands.run([sys.executable, "-c", "print('secret-value'); raise SystemExit(7)"], "test")
    assert "secret-value" not in str(error.value)
    assert "secret-value" not in (tmp_path / "run.log").read_text()
    assert "[REDACTED]" in (tmp_path / "run.log").read_text()
    assert commands.run([sys.executable, "-c", "print('secret-value')"], "auth", private=True).strip() == "secret-value"
    assert "secret-value" not in (tmp_path / "run.log").read_text()


def test_expired_budget_never_starts_command(tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError

    with pytest.raises(FactoryError, match="deadline"):
        Commands(time.monotonic() - 1).run(["touch", str(tmp_path / "started")], "test")
    assert not (tmp_path / "started").exists()


def test_timeout_kills_entire_process_group(tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError

    marker = tmp_path / "child-finished"
    started = time.monotonic()
    with pytest.raises(FactoryError, match="deadline"):
        Commands(time.monotonic() + 0.3).run(["sh", "-c", f"(sleep 0.8; touch {marker}) & wait"], "test")
    assert time.monotonic() - started < 0.8
    time.sleep(0.8)
    assert not marker.exists()


def test_missing_executable_is_sanitized() -> None:
    from software_factory.process import Commands, FactoryError

    with pytest.raises(FactoryError, match="tool unavailable"):
        Commands().run(["factory-command-does-not-exist"], "test")


def test_explicit_environment_and_working_directory(tmp_path: Path) -> None:
    from software_factory.process import Commands

    output = Commands().run(
        [sys.executable, "-c", "import os; print(os.getcwd()); print(os.environ.get('ONLY'))"],
        "test",
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "ONLY": "value"},
    )
    assert output.splitlines() == [str(tmp_path.resolve()), "value"]
