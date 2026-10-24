# Validate shared-image startup, coordinate serial first-pass issue runs, and publish only after verified cleanup.
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
from software_factory.repository import Repository
from software_factory.sandbox import PI_FLAGS, Sandbox, configure_user, copilot_endpoint

LOGGER = logging.getLogger("software_factory")

# Smoke-run baseline tools without mounts, credentials, network access, or target repository commands.
RUNTIME_CHECK = """set -eu
 test "$(id -u)" = "$(stat -c %u "$HOME")"
 test -w "$HOME"
 mkdir -p "$XDG_CACHE_HOME"
 test -w "$XDG_CACHE_HOME"
 sudo -n true
 test "$(uname -m)" = aarch64
 for tool in pi node npm docker python uv bash git make cc c++ curl tar; do "$tool" --version >/dev/null; done
 unzip -v >/dev/null
 node -e 'const [a,b] = process.versions.node.split(".").map(Number);
   if(a < 22 || (a === 22 && b < 19)) process.exit(1)'
 docker compose version
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


# Resolve a Copilot-only bearer privately from host Pi using the caller's command budget and trusted directory.
def copilot_bearer(commands: Commands, directory: Path) -> str:
    return commands.run(
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
        cwd=directory,
        private=True,
    ).strip()


# Validate artifacts, host prerequisites, native local image, and actual tool execution before polling.
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
        bearer = copilot_bearer(commands, Path(directory))
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
                "--detach",
                "--name",
                name,
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--env",
                "HOME=/tmp/factory-home",
                "--env",
                "XDG_CACHE_HOME=/tmp/factory-home/.cache",
                "--pull=never",
                "--platform",
                "linux/arm64",
                "--network",
                "none",
                "--entrypoint",
                "sleep",
                image_id,
                "infinity",
            ],
            "startup agent",
            env=env,
        )
        configure_user(name, commands, env)
        commands.run(
            ["docker", "exec", "--user", str(os.getuid()), "-i", name, "sh", "-ec", RUNTIME_CHECK],
            "agent runtime",
            env=env,
        )
    except FactoryError:
        failed = True
        raise FactoryError(
            "agent runtime check failed: rebuild the shared image with sudo and the documented native tools; "
            "check host-user execution and writable container home"
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
    # Accept immutable startup state; each labeled issue receives a fresh private workspace and execution identity.
    def __init__(self, config: Config, runtime: AgentRuntime) -> None:
        self.config = config
        self.runtime = runtime
        self.artifacts = config.artifacts_dir

    # Poll every 30 seconds, reporting discovery errors and propagating interruption to the terminal entrypoint.
    def run(self) -> None:
        LOGGER.warning(
            "Polling %s every 30 seconds; Docker-enabled first-pass execution active", self.config.repository
        )
        while True:
            try:
                self.poll_once()
            except FactoryError as error:
                LOGGER.error("Polling failed: %s", error)
            time.sleep(30)

    # Discover labeled issues serially; retained diagnostics are never interpreted as resumable work.
    def poll_once(self) -> None:
        github = GitHub(self.config.repository, Commands())
        for number in github.discover():
            self.process_issue(number)

    # Confirm duplicate/claim state, execute one first-pass run, and report failures without restoring the trigger.
    def process_issue(self, number: int) -> None:
        commands = Commands(deadline=time.monotonic() + 900)
        github = GitHub(self.config.repository, commands)
        claimed = False
        directory = None
        try:
            existing = github.open_pr(number)
            branch_exists = False if existing else github.branch_exists(number)
            github.remove_trigger(number)
            claimed = True
            if existing or branch_exists:
                message = (
                    "Skipped: existing open PR " + existing
                    if existing
                    else f"Skipped: factory/issue-{number} already exists; "
                    "clean up the remote branch and reapply agent:implement"
                )
                github.comment(number, message)
                return
            directory = Path(tempfile.mkdtemp(prefix=f"issue-{number}-", dir=self.artifacts))
            commands.log = directory / "run.log"
            github.comment(number, "Running: implementation started")
            url = self.execute(number, github, commands, directory)
            github.comment(number, "Succeeded: " + url)
        except FactoryError as error:
            self.report_failure(number, claimed, str(error), directory)
            return
        except OSError:
            self.report_failure(
                number, claimed, "local filesystem operation failed; inspect private diagnostics", directory
            )
            return
        except KeyboardInterrupt:
            self.report_failure(number, claimed, "operator interruption", directory)
            raise
        if directory is not None:
            try:
                shutil.rmtree(directory)
            except OSError:
                LOGGER.error("Could not remove successful workspace: %s", directory)

    # Run setup/Pi/verification under one deadline, stop mutators and clean resources, then publish through trusted Git.
    def execute(self, number: int, github: GitHub, commands: Commands, directory: Path) -> str:
        snapshot = github.snapshot(number)
        branch = github.default_branch()
        repository = Repository(directory, commands)
        url = f"https://github.com/{self.config.repository}.git"
        snapshot["base_commit"] = repository.checkout(url, branch)
        sandbox = Sandbox(self.runtime.image_id, self.runtime.docker_host, directory, commands)
        LOGGER.warning("Issue #%s run identity %s; private diagnostics %s", number, sandbox.project, directory)
        failure = None
        try:
            sandbox.start()
            sandbox.setup()
            bearer = copilot_bearer(commands, directory)
            commands.secrets.append(bearer)
            endpoint = copilot_endpoint(bearer)
            sandbox.implement(snapshot, bearer, endpoint, self.config.model)
            sandbox.verify()
        except BaseException as error:
            # Unexpected failures must not bypass removal of daemon-managed work either.
            failure = error
        try:
            sandbox.stop()
        except FactoryError, OSError:
            LOGGER.error("Run cleanup failed; inspect private diagnostics and run-owned resources: %s", directory)
            if not isinstance(failure, KeyboardInterrupt):
                reason = f"{failure}; " if isinstance(failure, FactoryError) else ""
                raise FactoryError(reason + "run cleanup failed; publication blocked") from None
        if failure is not None:
            raise failure
        if commands.deadline is not None and time.monotonic() >= commands.deadline:
            raise FactoryError("issue-run deadline expired")
        repository.commit(number)
        try:
            repository.push(url, number)
            return github.publish(number, snapshot["title"], branch)
        except (FactoryError, OSError) as error:
            reason = str(error) if isinstance(error, FactoryError) else "publication filesystem operation failed"
            # Observe uncertain publication once with a separate bounded read budget; never retry a write.
            observer = GitHub(self.config.repository, Commands(deadline=time.monotonic() + 30))
            try:
                existing = observer.open_pr(number)
                state = (
                    "observed PR " + existing
                    if existing
                    else (
                        "remote branch exists; operator inspection required"
                        if observer.branch_exists(number)
                        else "no remote factory branch observed"
                    )
                )
            except FactoryError, OSError:
                LOGGER.error("remote publication state could not be checked for issue #%s", number)
                state = "remote publication state could not be checked; operator inspection required"
            raise FactoryError(f"{reason}; {state}") from None

    # Report a concise failure with a bounded status-only budget, retaining private diagnostics without raw output.
    def report_failure(self, number: int, claimed: bool, reason: str, directory: Path | None) -> None:
        LOGGER.error("Issue #%s failed: %s", number, reason)
        if directory is not None:
            LOGGER.error("Retained private diagnostics: %s", directory)
        if claimed:
            try:
                github = GitHub(self.config.repository, Commands(deadline=time.monotonic() + 30))
                github.comment(number, "Failed: " + reason)
            except FactoryError, OSError:
                LOGGER.error("GitHub failure reporting unavailable for issue #%s", number)
