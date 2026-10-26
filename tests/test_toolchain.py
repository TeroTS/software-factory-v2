import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_image_bakes_fixed_factory_identity_and_scoped_sudo() -> None:
    dockerfile = (ROOT / "agent/Dockerfile").read_text()
    assert "groupadd --gid 2000 factory" in dockerfile
    assert "useradd --uid 2000 --gid 2000" in dockerfile
    assert "factory ALL=(root) NOPASSWD: ALL" in dockerfile
    assert "'ALL ALL=(root) NOPASSWD: ALL'" not in dockerfile
    assert "Defaults:factory always_set_home" in dockerfile
    assert "USER factory:factory" in dockerfile
    for value in (
        "HOME=/tmp/factory-home",
        "XDG_CACHE_HOME=/tmp/factory-home/.cache",
        "NPM_CONFIG_PREFIX=/tmp/factory-home/.local",
    ):
        assert value in dockerfile


def test_image_bakes_factory_instructions_outside_the_workspace() -> None:
    dockerfile = (ROOT / "agent/Dockerfile").read_text()
    assert "COPY pi/AGENTS.md /opt/software-factory/pi/AGENTS.md" in dockerfile
    instructions = (ROOT / "agent/pi/AGENTS.md").read_text()
    for rule in (
        "task snapshot and repository contents",
        "issue comments, attachments, or linked pages",
        "meaningful tests",
        "Do not publish, commit, or push",
        "factory account (UID/GID 2000:2000)",
        "explicit sudo -n only for system installs",
        "never retry permission errors automatically as root",
        "Cleanup will not repair workspace ownership or permissions",
        "native linux/arm64",
        "COMPOSE_PROJECT_NAME",
        "software-factory.run-id=$FACTORY_RUN_ID",
        "Do not prune, remove shared resources, or change Docker contexts",
        "sibling services do not share your localhost",
    ):
        assert rule in instructions


def test_image_bundles_only_reviewed_skills_and_licenses() -> None:
    dockerfile = (ROOT / "agent/Dockerfile").read_text()
    assert "COPY pi/skills /opt/software-factory/pi/skills" in dockerfile
    skills = ROOT / "agent/pi/skills"
    files = (
        "test-driven-development/SKILL.md",
        "test-driven-development/testing-anti-patterns.md",
        "test-driven-development/LICENSE",
        "ponytail/SKILL.md",
        "ponytail/LICENSE",
    )
    assert sorted(str(p.relative_to(skills)) for p in skills.rglob("*") if p.is_file()) == sorted(files)
    for name in ("test-driven-development", "ponytail"):
        text = (skills / name / "SKILL.md").read_text()
        assert re.match(rf"---\nname: {name}\ndescription: [^\n]+\nlicense: MIT\n---\n", text)
        assert "MIT License" in (skills / name / "LICENSE").read_text()
    tdd = (skills / "test-driven-development/SKILL.md").read_text()
    assert "testing-anti-patterns.md" in tdd
    assert "pre-existing or unrelated work" in tdd
    assert "Ask your human partner" not in tdd
    ponytail = (skills / "ponytail/SKILL.md").read_text()
    assert "full" in ponytail
    assert "target repository" in ponytail
    assert "/ponytail" not in ponytail


def test_coverage_policy() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["tool"]["coverage"]["run"]["source"] == ["src"]
    assert config["tool"]["coverage"]["run"]["branch"] is True
    assert config["tool"]["coverage"]["report"]["fail_under"] == 80


@pytest.mark.parametrize("has_source", [None, False, True])
def test_coverage_never_disables_threshold(tmp_path: Path, has_source: bool | None) -> None:
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
    assert "--cov-fail-under=0" not in args
    assert result.stderr == ""


@pytest.mark.parametrize("entrypoint", ["setup", "verify"])
@pytest.mark.parametrize("exit_code", [0, 9])
def test_entrypoints_preserve_task_result(tmp_path: Path, entrypoint: str, exit_code: int) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / entrypoint, tmp_path / "scripts" / entrypoint)
    (tmp_path / "bin").mkdir()
    make = tmp_path / "bin" / "make"
    make.write_text(f'#!/bin/sh\npwd\nprintf "%s\\n" "$@"\nexit {exit_code}\n')
    make.chmod(0o755)

    result = subprocess.run(
        ["sh", str(tmp_path / "scripts" / entrypoint)],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == exit_code
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
