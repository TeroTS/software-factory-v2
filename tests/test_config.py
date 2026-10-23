import subprocess
import sys
from pathlib import Path

import pytest


def test_cli_reports_bad_config_without_traceback(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "software_factory", "--config", str(tmp_path / "missing.toml")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Cannot read configuration" in result.stderr
    assert "Traceback" not in result.stderr


def config_file(tmp_path: Path, extra: str = "") -> Path:
    (tmp_path / "compose.yaml").write_text("services: {}\n")
    path = tmp_path / "factory.toml"
    path.write_text(
        'repository = "TeroTS/factory-smoke-test"\n'
        'compose_file = "compose.yaml"\n'
        'compose_service = "agent"\n'
        'model = "gpt-6.1-sol"\n' + extra
    )
    return path


def test_config_resolves_compose_relative_to_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from software_factory.config import load_config

    path = config_file(tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    config = load_config(path)
    assert config.repository == "TeroTS/factory-smoke-test"
    assert config.compose_file == tmp_path / "compose.yaml"
    assert config.compose_service == "agent"
    assert config.model == "gpt-6.1-sol"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('repository = "TeroTS/factory-smoke-test"', 'repository = "https://github.com/a/b"'),
        ('repository = "TeroTS/factory-smoke-test"', 'repository = "../x"'),
        ('model = "gpt-6.1-sol"', 'model = ""'),
        ('model = "gpt-6.1-sol"', 'model = "*"'),
        ('model = "gpt-6.1-sol"', 'model = "anthropic/sonnet"'),
        ('compose_service = "agent"', "compose_service = 1"),
        ('compose_service = "agent"', 'compose_service = "--help"'),
        ('compose_file = "compose.yaml"', 'compose_file = "missing.yaml"'),
        ('model = "gpt-6.1-sol"', ""),
        ('model = "gpt-6.1-sol"', 'model = "gpt-6.1-sol"\nextra = "no"'),
        ('model = "gpt-6.1-sol"', "[broken"),
    ],
)
def test_config_rejects_invalid_input(tmp_path: Path, old: str, new: str) -> None:
    from software_factory.config import load_config
    from software_factory.process import FactoryError

    path = config_file(tmp_path)
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(FactoryError):
        load_config(path)
