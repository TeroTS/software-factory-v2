import subprocess
import sys
from pathlib import Path

import pytest

from software_factory.config import load_config
from software_factory.process import FactoryError


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "factory.toml"
    path.write_text(
        'repository = "TeroTS/factory-smoke-test"\n'
        'model = "gpt-6.1-sol"\n'
        'agent_image = "software-factory-agent:1.0.0"\n'
        'artifacts_dir = "private/runs"\n'
    )
    return path


def test_cli_reports_bad_config_without_traceback(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "software_factory", "--config", str(tmp_path / "missing.toml")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Cannot read configuration" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("absolute", [False, True])
def test_config_resolves_artifacts_against_toml_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, absolute: bool
) -> None:
    path = config_file(tmp_path)
    if absolute:
        path.write_text(path.read_text().replace('"private/runs"', f'"{tmp_path / "elsewhere"}"'))
    monkeypatch.chdir(tmp_path.parent)
    config = load_config(path)
    assert config.repository == "TeroTS/factory-smoke-test"
    assert config.model == "gpt-6.1-sol"
    assert config.agent_image == "software-factory-agent:1.0.0"
    assert config.artifacts_dir == tmp_path / ("elsewhere" if absolute else "private/runs")
    assert not config.artifacts_dir.exists(), "parsing must not modify artifacts"


@pytest.mark.parametrize("field", ["repository", "model", "agent_image", "artifacts_dir"])
@pytest.mark.parametrize("value", [None, '""', '"  "', "42", "true", "[]", "{}"])
def test_config_requires_exactly_four_nonempty_strings(tmp_path: Path, field: str, value: str | None) -> None:
    path = config_file(tmp_path)
    lines = path.read_text().splitlines()
    path.write_text(
        "\n".join(
            line if not line.startswith(field + " =") else ("" if value is None else f"{field} = {value}")
            for line in lines
        )
    )
    with pytest.raises(FactoryError, match="requires exactly"):
        load_config(path)


@pytest.mark.parametrize(
    "old,new",
    [
        ('"TeroTS/factory-smoke-test"', '"https://github.com/a/b"'),
        ('"TeroTS/factory-smoke-test"', '"../x"'),
        ('"gpt-6.1-sol"', '"*"'),
        ('"gpt-6.1-sol"', '"github-copilot/model"'),
        ('"software-factory-agent:1.0.0"', '"--help"'),
        ('"software-factory-agent:1.0.0"', '"image with spaces"'),
        ('"software-factory-agent:1.0.0"', '"https://registry/image"'),
        ('"private/runs"', '"\\u0000"'),
    ],
)
def test_config_rejects_invalid_values(tmp_path: Path, old: str, new: str) -> None:
    path = config_file(tmp_path)
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(FactoryError):
        load_config(path)


@pytest.mark.parametrize("extra", ['extra = "no"', "[nested]\nx = 1", "[broken"])
def test_config_rejects_unknown_fields_and_malformed_toml(tmp_path: Path, extra: str) -> None:
    path = config_file(tmp_path)
    path.write_text(path.read_text() + extra)
    with pytest.raises(FactoryError):
        load_config(path)


@pytest.mark.parametrize("field", ["compose_file", "compose_service"])
def test_legacy_configuration_has_migration_guidance(tmp_path: Path, field: str) -> None:
    path = config_file(tmp_path)
    path.write_text(path.read_text() + f'{field} = "old"\n')
    with pytest.raises(FactoryError, match="agent_image.*artifacts_dir"):
        load_config(path)


@pytest.mark.parametrize(
    "image",
    [
        "localhost:5000/team/agent:v1",
        "[::1]:5000/team/agent:v1",
        "agent",
        "registry.example/team/agent@sha256:" + "a" * 64,
    ],
)
def test_local_image_references_are_accepted(tmp_path: Path, image: str) -> None:
    path = config_file(tmp_path)
    path.write_text(path.read_text().replace("software-factory-agent:1.0.0", image))
    assert load_config(path).agent_image == image
