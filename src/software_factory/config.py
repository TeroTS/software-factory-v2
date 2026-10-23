# Parse operator-owned TOML into validated repository and Compose inputs; reject invalid startup configuration.
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from software_factory.process import FactoryError


# Hold the four required configuration fields without credentials or command templates.
@dataclass(frozen=True)
class Config:
    repository: str
    compose_file: Path
    compose_service: str
    model: str


# Load a TOML file, resolve Compose relative to it, and raise actionable safe diagnostics on invalid input.
def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text())
    except OSError, ValueError:
        raise FactoryError("Cannot read configuration: provide a readable, valid TOML file") from None
    fields = {"repository", "compose_file", "compose_service", "model"}
    if set(data) != fields or any(not isinstance(v, str) or not v.strip() for v in data.values()):
        raise FactoryError("Configuration requires exactly repository, compose_file, compose_service, model strings")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*", data["repository"]):
        raise FactoryError("repository must be a GitHub owner/name, not a URL")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", data["compose_service"]):
        raise FactoryError("compose_service must be a Compose service name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", data["model"]):
        raise FactoryError("model must be an exact github-copilot model ID without patterns or provider prefix")
    compose_file = (path.resolve().parent / data["compose_file"]).resolve()
    if not compose_file.is_file():
        raise FactoryError("compose_file must point to a readable file")
    return Config(data["repository"], compose_file, data["compose_service"], data["model"])
