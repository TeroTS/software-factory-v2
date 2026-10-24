# Execute one shared-image agent with local engine access, private Copilot input, and scoped Docker cleanup.
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from software_factory.process import Commands, FactoryError

PI_FLAGS = [
    "--no-extensions",
    "--no-mcp",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-approve",
]
RUN_LABEL = "software-factory.run-id"


# Validate bearer metadata without exposing it; accept supported Copilot endpoints with ≥20-minute lifetime.
def copilot_endpoint(bearer: str) -> str:
    endpoint = re.search(r"(?:^|;)proxy-ep=proxy\.(individual|business|enterprise)\.githubcopilot\.com(?:;|$)", bearer)
    expiry = re.search(r"(?:^|;)exp=(\d+)(?:;|$)", bearer)
    try:
        valid = endpoint and expiry and int(expiry[1]) - time.time() >= 1200
    except ValueError, OverflowError:
        valid = False
    if not valid:
        raise FactoryError("Copilot bearer requires validated endpoint metadata and at least 20 minutes remaining")
    return f"https://api.{endpoint[1]}.githubcopilot.com"


# Carry completed verification's redacted output privately while keeping the public error concise.
class VerificationFailed(FactoryError):
    # Separate feedback from the operator-visible summary so transcripts are never posted as errors.
    def __init__(self, output: str) -> None:
        super().__init__("verification failed")
        self.output = output


# Own one fresh root agent and exact resource identity; Docker access is not a host-security boundary.
class Sandbox:
    # Keep cleanup identity and engine selection on the host, outside the ordinary same-path workspace mount.
    def __init__(self, image_id: str, docker_host: str, directory: Path, commands: Commands) -> None:
        self.image_id = image_id
        self.directory = directory
        self.workspace = directory / "workspace"
        self.commands = commands
        self.project = "factory-" + uuid.uuid4().hex
        keys = {"PATH", "HOME", "USER", "TMPDIR", "DOCKER_CONFIG"}
        self.env = {key: value for key, value in os.environ.items() if key in keys}
        self.env["DOCKER_HOST"] = docker_host
        # Desktop's host socket is a proxy, not a bindable path in the Linux daemon's filesystem.
        self.socket_path = "/var/run/docker.sock" if sys.platform == "darwin" else docker_host[7:]
        self.base = ["docker", "exec", "-i", self.project]

    # Start the pinned native image with root, a same-path bind, and the resolved local Unix engine socket.
    def start(self) -> None:
        self.commands.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                self.project,
                "--pull=never",
                "--platform",
                "linux/arm64",
                "--user",
                "0:0",
                "--init",
                "--label",
                f"{RUN_LABEL}={self.project}",
                "--mount",
                f"type=bind,src={self.workspace},dst={self.workspace}",
                "--mount",
                f"type=bind,src={self.socket_path},dst=/var/run/docker.sock",
                "--workdir",
                str(self.workspace),
                "--env",
                "DOCKER_HOST=unix:///var/run/docker.sock",
                "--env",
                "DOCKER_DEFAULT_PLATFORM=linux/arm64",
                "--env",
                f"FACTORY_RUN_ID={self.project}",
                "--env",
                f"COMPOSE_PROJECT_NAME={self.project}",
                "--entrypoint",
                "sleep",
                self.image_id,
                "infinity",
            ],
            "agent startup",
            cwd=self.directory,
            env=self.env,
        )

    # Require both canonical executable entrypoints before setup; do not invent commands or repair setup failures.
    def setup(self) -> None:
        self.commands.run(
            self.base + ["sh", "-ec", "test -x ./scripts/setup && test -x ./scripts/verify"],
            "required entrypoints",
            cwd=self.directory,
            env=self.env,
        )
        self.commands.run(self.base + ["./scripts/setup"], "setup", cwd=self.directory, env=self.env)

    # Send the immutable task and Copilot-only bearer through stdin to a fresh nonpersistent Pi invocation.
    def implement(
        self, snapshot: dict, bearer: str, endpoint: str, model: str, *, verification_output: str | None = None
    ) -> None:
        script = Path(__file__).with_name("sandbox_agent.mjs").read_text()
        self.commands.run(
            self.base + ["node", "--input-type=module", "-e", script],
            "implementation" if verification_output is None else "repair",
            cwd=self.directory,
            env=self.env,
            input=json.dumps(
                {
                    "snapshot": snapshot,
                    "bearer": bearer,
                    "endpoint": endpoint,
                    "model": model,
                    "flags": PI_FLAGS,
                    "verification_output": verification_output,
                }
            ),
        )

    # Distinguish completed repository check failures from missing scripts, Docker errors, or deadline expiry.
    def verify(self) -> None:
        output = self.commands.run(
            self.base
            + [
                "sh",
                "-c",
                "test -x ./scripts/verify || exit 127; ./scripts/verify 2>&1; "
                'status=$?; printf "\\nFACTORY_VERIFY_EXIT=%s\\n" "$status"',
            ],
            "verification",
            cwd=self.directory,
            env=self.env,
        )
        feedback, marker, status = output.rpartition("\nFACTORY_VERIFY_EXIT=")
        if not marker or not re.fullmatch(r"\d+\n", status) or not 0 <= int(status) <= 255:
            raise FactoryError("verification did not return a valid result")
        if int(status):
            for secret in self.commands.secrets:
                feedback = feedback.replace(secret, "[REDACTED]")
            raise VerificationFailed(feedback)

    # Enumerate exact cooperative ownership independently of any agent-modified Compose or teardown files.
    def owned(self, commands: Commands, kind: str) -> set[str]:
        ids = set()
        for label in (RUN_LABEL, "com.docker.compose.project"):
            args = ["docker", kind, "ls", "--quiet", "--filter", f"label={label}={self.project}"]
            if kind == "container":
                args.append("--all")
            ids.update(commands.run(args, "owned resource discovery", env=self.env).splitlines())
        return ids

    # Remove a known resource, tolerating confirmed absence but never treating a failed engine read as absence.
    def remove(self, commands: Commands, kind: str, identity: str) -> None:
        args = ["docker", kind, "rm"] + (["--force"] if kind == "container" else []) + [identity]
        try:
            commands.run(args, "owned resource cleanup", env=self.env)
        except FactoryError:
            if kind in {"container", "network"} and re.fullmatch(r"[a-f0-9]{12,64}", identity):
                args = ["docker", kind, "ls", "--quiet", "--filter", "id=" + identity]
                if kind == "container":
                    args.append("--all")
                remaining = bool(commands.run(args, "cleanup absence check", env=self.env).strip())
            else:
                args = ["docker", kind, "ls", "--format", "{{.Names}}" if kind == "container" else "{{.Name}}"]
                if kind == "container":
                    args.append("--all")
                remaining = identity in commands.run(args, "cleanup absence check", env=self.env).splitlines()
            if remaining:
                raise FactoryError("owned resource cleanup failed; inspect run identity " + self.project) from None

    # Restore host-operator access after mutators stop, using fixed trusted code with no socket or credentials.
    def restore_ownership(self, commands: Commands) -> None:
        name = self.project + "-ownership"
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
                    "--user",
                    "0:0",
                    "--mount",
                    f"type=bind,src={self.workspace},dst={self.workspace}",
                    "--workdir",
                    str(self.workspace),
                    "--entrypoint",
                    "sh",
                    self.image_id,
                    "-ec",
                    'find . -xdev -exec chown -h "$1" {} +; find . -xdev ! -type l -exec chmod u+rwX {} +',
                    "factory-ownership",
                    f"{os.getuid()}:{os.getgid()}",
                ],
                "workspace ownership",
                env=self.env,
            )
        finally:
            cleanup = Commands(deadline=time.monotonic() + 10)
            cleanup.secrets = self.commands.secrets.copy()
            self.remove(cleanup, "container", name)

    # Stop the agent first, then owned containers/networks/volumes, and restore files under a bounded cleanup budget.
    def stop(self) -> None:
        # Cleanup must still reach the engine when private diagnostic storage has failed.
        cleanup = Commands(deadline=time.monotonic() + 60)
        cleanup.secrets = self.commands.secrets.copy()
        failures = []
        try:
            self.remove(cleanup, "container", self.project)
        except FactoryError as error:
            failures.append(error)
        resources = {}
        for kind in ("container", "network", "volume"):
            try:
                resources[kind] = self.owned(cleanup, kind)
            except FactoryError as error:
                failures.append(error)
        for kind, identities in resources.items():
            for identity in sorted(identities):
                try:
                    self.remove(cleanup, kind, identity)
                except FactoryError as error:
                    failures.append(error)
        if not failures:
            self.restore_ownership(cleanup)
        if failures:
            raise FactoryError("run cleanup failed; inspect run identity " + self.project)
