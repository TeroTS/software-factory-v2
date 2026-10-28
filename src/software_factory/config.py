# Parse operator-owned TOML into shared-image startup inputs; reject legacy or invalid configuration.
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from software_factory.process import FactoryError


# Hold three operator fields and the retained artifacts location without credentials or command templates.
@dataclass(frozen=True)
class Config:
    repository: str
    model: str
    agent_image: str
    artifacts_dir: Path = Path("/home/factory/artifacts")


# Load exactly three TOML strings without filesystem changes; reject removed fields with migration guidance.
def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text())
    except OSError, ValueError:
        raise FactoryError("Cannot read configuration: provide a readable, valid TOML file") from None
    if {"compose_file", "compose_service"} & set(data):
        raise FactoryError(
            "Legacy Compose configuration is unsupported: build/select the shared agent_image "
            "and remove compose_file and compose_service"
        )
    if "artifacts_dir" in data:
        raise FactoryError(
            "Remove artifacts_dir from TOML; artifacts now use /home/factory/artifacts. "
            "Previous diagnostics stay in their original location; inspect them separately"
        )
    fields = {"repository", "model", "agent_image"}
    if set(data) != fields or any(not isinstance(v, str) or not v.strip() for v in data.values()):
        raise FactoryError("Configuration requires exactly repository, model, agent_image strings")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*", data["repository"]):
        raise FactoryError("repository must be a GitHub owner/name, not a URL")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", data["model"]):
        raise FactoryError("model must be an exact github-copilot model ID without patterns or provider prefix")
    image = data["agent_image"]
    # Docker's local image inspection is authoritative for reference grammar; reject unsafe argument shapes here.
    if image.startswith("-") or "://" in image or any(char.isspace() or ord(char) < 32 for char in image):
        raise FactoryError("agent_image must be a local Docker image reference, not a URL or command option")
    return Config(data["repository"], data["model"], data["agent_image"])
