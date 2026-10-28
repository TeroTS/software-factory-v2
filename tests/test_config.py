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


def test_config_uses_fixed_retained_artifacts_without_modifying_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = config_file(tmp_path)
    previous = tmp_path / "previous.log"
    previous.write_text("retained diagnostics")
    monkeypatch.chdir(tmp_path.parent)
    config = load_config(path)
    assert config.repository == "TeroTS/factory-smoke-test"
    assert config.model == "gpt-6.1-sol"
    assert config.agent_image == "software-factory-agent:1.0.0"
    assert config.artifacts_dir == Path("/home/factory/artifacts")
    assert previous.read_text() == "retained diagnostics"
    assert set(tmp_path.iterdir()) == {path, previous}


@pytest.mark.parametrize("field", ["repository", "model", "agent_image"])
@pytest.mark.parametrize("value", [None, '""', '"  "', "42", "true", "[]", "{}"])
def test_config_requires_exactly_three_nonempty_strings(tmp_path: Path, field: str, value: str | None) -> None:
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
        ('"software-factory-agent:1.0.0"', '"image\\u0000"'),
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
    with pytest.raises(FactoryError, match="agent_image.*remove compose_file"):
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


@pytest.mark.parametrize("value", ['"old/runs"', '"/home/factory/artifacts"', "42"])
def test_removed_artifacts_field_requires_explicit_migration(tmp_path: Path, value: str) -> None:
    path = config_file(tmp_path)
    original = path.read_text() + f"artifacts_dir = {value}\n"
    path.write_text(original)
    with pytest.raises(FactoryError, match="Remove artifacts_dir.* /home/factory/artifacts"):
        load_config(path)
    assert path.read_text() == original
