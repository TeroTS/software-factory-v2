import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_coverage_policy() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["tool"]["coverage"]["run"]["source"] == ["src"]
    assert config["tool"]["coverage"]["run"]["branch"] is True
    assert config["tool"]["coverage"]["report"]["fail_under"] == 80


@pytest.mark.parametrize("has_source", [None, False, True])
def test_coverage_threshold_only_relaxed_without_application_source(tmp_path: Path, has_source: bool | None) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / "coverage", tmp_path / "scripts" / "coverage")
    if has_source is not None:
        (tmp_path / "src").mkdir()
    if has_source:
        (tmp_path / "src" / "example.py").write_text("value = 1\n")
    (tmp_path / "bin").mkdir()
    uv = tmp_path / "bin" / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 7\n')
    uv.chmod(0o755)

    result = subprocess.run(
        ["sh", str(tmp_path / "scripts" / "coverage")],
        env={**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    if has_source is None:
        assert result.returncode != 0
        assert result.stdout == ""
        return

    assert result.returncode == 7
    args = result.stdout.splitlines()
    assert args[:4] == ["run", "--frozen", "pytest", "--cov=src"]
    assert ("--cov-fail-under=0" in args) is not has_source
    assert ("baseline unavailable" in result.stderr) is not has_source


@pytest.mark.parametrize("entrypoint", ["setup", "verify"])
def test_entrypoints_preserve_task_failure(tmp_path: Path, entrypoint: str) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / entrypoint, tmp_path / "scripts" / entrypoint)
    (tmp_path / "bin").mkdir()
    make = tmp_path / "bin" / "make"
    make.write_text('#!/bin/sh\npwd\nprintf "%s\\n" "$@"\nexit 9\n')
    make.chmod(0o755)

    result = subprocess.run(
        ["sh", str(tmp_path / "scripts" / entrypoint)],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 9
    assert result.stdout.splitlines() == [str(tmp_path.resolve()), entrypoint]


def test_development_logging_is_warning_only_on_stderr() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import logging, logging.config; "
            "logging.config.fileConfig('logging.ini'); "
            "logging.debug('debug'); logging.info('info'); logging.warning('warning')",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == ""
    assert result.stderr == "WARNING root: warning\n"
