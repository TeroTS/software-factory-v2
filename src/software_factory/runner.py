# Validate shared-image startup and poll read-only until Docker-enabled issue execution lands in US-05.
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from software_factory.config import Config
from software_factory.github import GitHub
from software_factory.process import Commands, FactoryError
from software_factory.sandbox import PI_FLAGS, copilot_endpoint

LOGGER = logging.getLogger("software_factory")

# Check execution/tool availability without mounts, credentials, network access, or target repository commands.
RUNTIME_CHECK = """set -eu
 test "$(id -u)" = 0
 test "$(uname -m)" = aarch64
 for tool in pi node npm docker python uv bash git make cc c++ curl tar unzip; do command -v "$tool" >/dev/null; done
 node -e 'const [a,b] = process.versions.node.split(".").map(Number);
   if(a < 22 || (a === 22 && b < 19)) process.exit(1)'
 pi --version
 docker compose version
 python --version
 uv --version
 test -s /etc/ssl/certs/ca-certificates.crt
"""


# Retain the immutable image identity and resolved local engine endpoint for this runner session.
@dataclass(frozen=True)
class AgentRuntime:
    image_id: str
    docker_host: str


# Resolve Docker's explicit-context/host precedence and reject nonlocal endpoints without exposing their contents.
def local_docker_environment(commands: Commands) -> dict[str, str]:
    keys = {"PATH", "HOME", "USER", "TMPDIR", "DOCKER_CONFIG", "DOCKER_CONTEXT"}
    env = {key: value for key, value in os.environ.items() if key in keys}
    endpoint = os.environ.get("DOCKER_HOST") if not env.get("DOCKER_CONTEXT") else None
    if endpoint is None:
        try:
            contexts = json.loads(commands.run(["docker", "context", "inspect"], "Docker context", env=env))
            endpoint = contexts[0]["Endpoints"]["docker"]["Host"]
        except ValueError, TypeError, KeyError, IndexError:
            raise FactoryError("Docker context: cannot resolve a local unix socket endpoint") from None
    if not isinstance(endpoint, str) or not endpoint.startswith("unix:///") or len(endpoint) <= len("unix:///"):
        raise FactoryError(
            "Docker requires a local engine using an absolute unix socket endpoint; remote engines are unsupported"
        )
    env.pop("DOCKER_CONTEXT", None)
    env["DOCKER_HOST"] = endpoint
    return env


# Validate artifacts, host prerequisites, native local image, and actual tool execution before read-only polling.
def preflight(config: Config) -> AgentRuntime:
    try:
        config.artifacts_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryFile(dir=config.artifacts_dir) as probe:
            probe.write(b"factory startup\n")
            probe.flush()
    except OSError:
        raise FactoryError(
            "artifacts_dir must be a readable/writable directory; check its path and permissions"
        ) from None
    for tool in ("git", "gh", "docker", "pi"):
        if shutil.which(tool) is None:
            raise FactoryError(f"required tool unavailable: {tool}")
    commands = Commands()
    env = local_docker_environment(commands)
    try:
        engine = json.loads(commands.run(["docker", "info", "--format", "{{json .}}"], "Docker readiness", env=env))
        if engine["OSType"] != "linux" or engine["Architecture"] not in {"arm64", "aarch64"}:
            raise ValueError
    except ValueError, TypeError, KeyError:
        raise FactoryError("Docker requires a native linux/arm64 local engine; emulation is unsupported") from None
    commands.run(["gh", "auth", "status", "--hostname", "github.com"], "GitHub authentication", private=True)
    with tempfile.TemporaryDirectory(prefix=".startup-auth-", dir=config.artifacts_dir) as directory:
        bearer = commands.run(
            [
                "pi",
                "auth",
                "print-bearer-token",
                "--provider",
                "github-copilot",
                "--min-expiry",
                "20m",
                *PI_FLAGS,
                "--no-context-files",
                "--offline",
            ],
            "Copilot authentication",
            cwd=Path(directory),
            private=True,
        ).strip()
        copilot_endpoint(bearer)
    try:
        images = json.loads(commands.run(["docker", "image", "inspect", config.agent_image], "agent image", env=env))
        image = images[0]
        image_id = image["Id"]
        if (
            len(images) != 1
            or image["Os"] != "linux"
            or image["Architecture"] != "arm64"
            or not isinstance(image_id, str)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id)
        ):
            raise ValueError
    except FactoryError, ValueError, TypeError, KeyError, IndexError:
        raise FactoryError(
            "agent_image must be a compatible local linux/arm64 image; build it first, then restart"
        ) from None
    name = "factory-startup-" + uuid.uuid4().hex
    failed = False
    try:
        commands.run(
            [
                "docker",
                "run",
                "--name",
                name,
                "--pull=never",
                "--platform",
                "linux/arm64",
                "--network",
                "none",
                "--entrypoint",
                "sh",
                image_id,
                "-ec",
                RUNTIME_CHECK,
            ],
            "agent runtime",
            env=env,
        )
    except FactoryError:
        failed = True
        raise FactoryError(
            "agent runtime check failed: rebuild the shared image with root and the documented native tools"
        ) from None
    except KeyboardInterrupt:
        failed = True
        raise
    finally:
        # A terminated Docker client can leave daemon-managed work; always remove this uniquely named probe.
        try:
            Commands().run(["docker", "rm", "--force", "--volumes", name], "startup cleanup", env=env)
        except FactoryError:
            LOGGER.error("Cannot remove startup probe %s; inspect this container on the local engine", name)
            if not failed:
                raise
    return AgentRuntime(image_id, env["DOCKER_HOST"])


# Keep one serial poller with no recovery state; the operator prevents simultaneous runners for this repository.
class Runner:
    # Accept validated startup state without preparing any issue workspace or exposing a legacy backend.
    def __init__(self, config: Config, runtime: AgentRuntime) -> None:
        self.config = config
        self.runtime = runtime
        self.artifacts = config.artifacts_dir

    # Poll every 30 seconds, reporting discovery errors and propagating interruption to the terminal entrypoint.
    def run(self) -> None:
        LOGGER.warning("Polling %s every 30 seconds; issue execution disabled until US-05", self.config.repository)
        while True:
            try:
                self.poll_once()
            except FactoryError as error:
                LOGGER.error("Polling failed: %s", error)
            time.sleep(30)

    # Discover issues serially without consuming their triggers or interpreting retained artifacts as work.
    def poll_once(self) -> None:
        github = GitHub(self.config.repository, Commands())
        for number in github.discover():
            self.process_issue(number)

    # Leave all issue/remote/artifact state unchanged until US-05 replaces this operator-approved temporary guard.
    def process_issue(self, number: int) -> None:
        LOGGER.warning("Issue #%s not claimed: Docker-enabled issue execution is unavailable until US-05", number)
