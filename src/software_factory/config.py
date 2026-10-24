# Parse operator-owned TOML into shared-image startup inputs; reject legacy or invalid configuration.
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from software_factory.process import FactoryError


# Hold the four required configuration fields without credentials or command templates.
@dataclass(frozen=True)
class Config:
    repository: str
    model: str
    agent_image: str
    artifacts_dir: Path


# Load four TOML strings, resolve artifacts against the TOML directory, and report safe migration/input errors.
def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text())
    except OSError, ValueError:
        raise FactoryError("Cannot read configuration: provide a readable, valid TOML file") from None
    if {"compose_file", "compose_service"} & set(data):
        raise FactoryError(
            "Legacy Compose configuration is unsupported: build/select the shared agent_image "
            "and supply artifacts_dir; remove compose_file and compose_service"
        )
    fields = {"repository", "model", "agent_image", "artifacts_dir"}
    if set(data) != fields or any(not isinstance(v, str) or not v.strip() for v in data.values()):
        raise FactoryError("Configuration requires exactly repository, model, agent_image, artifacts_dir strings")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*", data["repository"]):
        raise FactoryError("repository must be a GitHub owner/name, not a URL")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", data["model"]):
        raise FactoryError("model must be an exact github-copilot model ID without patterns or provider prefix")
    image = data["agent_image"]
    # Docker's local image inspection is authoritative for reference grammar; reject unsafe argument shapes here.
    if image.startswith("-") or "://" in image or any(char.isspace() or ord(char) < 32 for char in image):
        raise FactoryError("agent_image must be a local Docker image reference, not a URL or command option")
    try:
        artifacts_dir = (path.resolve().parent / data["artifacts_dir"]).resolve()
    except OSError, ValueError:
        raise FactoryError("artifacts_dir must be a valid directory path") from None
    return Config(data["repository"], data["model"], data["agent_image"], artifacts_dir)
