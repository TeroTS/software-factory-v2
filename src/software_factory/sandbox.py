# Validate Compose isolation and execute repository work in run-owned containers with Copilot-only credentials.
import copy
import json
import os
import re
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
SERVICE_FIELDS = {
    "image",
    "command",
    "entrypoint",
    "environment",
    "working_dir",
    "user",
    "volumes",
    "tmpfs",
    "depends_on",
    "healthcheck",
    "init",
    "read_only",
    "cap_drop",
    "security_opt",
    "networks",
    "mem_limit",
    "cpus",
    "pids_limit",
    "shm_size",
    "stop_grace_period",
    "restart",
    "pull_policy",
}


# Limit Compose interpolation to nonsecret tooling inputs and the runner-controlled workspace placeholder.
def docker_environment(workspace: Path) -> dict[str, str]:
    keys = {"PATH", "HOME", "USER", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"}
    return {**{key: value for key, value in os.environ.items() if key in keys}, "FACTORY_WORKSPACE": str(workspace)}


# Return an isolated copy of resolved Compose JSON, rejecting unsupported settings before any container starts.
def prepare_compose(data: dict, service: str, workspace: Path) -> dict:
    try:
        return _prepare_compose(data, service, workspace)
    except TypeError, KeyError, AttributeError, ValueError:
        raise FactoryError("Compose: malformed resolved configuration") from None


# Check supported isolation settings in every service and remove externally shared resource names.
def _prepare_compose(data: dict, service: str, workspace: Path) -> dict:
    result = copy.deepcopy(data)
    if set(result) - {"name", "services", "networks"}:
        raise FactoryError("Compose: unsupported top-level resource; use run-local networks and anonymous volumes")
    result.pop("name", None)
    services = result.get("services", {})
    if service not in services:
        raise FactoryError("Compose: configured compose_service is missing")
    for network in result.get("networks", {}).values():
        if set(network) - {"name", "driver", "internal", "attachable", "enable_ipv6", "ipam"}:
            raise FactoryError("Compose: external or unsupported network settings")
        if network.get("driver", "bridge") != "bridge" or network.get("ipam", {}).get("driver", "default") != "default":
            raise FactoryError("Compose: only isolated bridge networks are supported")
        network.pop("name", None)
    for spec in services.values():
        if set(spec) - SERVICE_FIELDS or not spec.get("image"):
            raise FactoryError("Compose: unsupported service settings; supply prebuilt images without host access")
        if spec.get("restart", "no") != "no" or spec.get("security_opt", []) not in ([], ["no-new-privileges:true"]):
            raise FactoryError("Compose: unsafe restart or security settings")
        for key in spec.get("environment", {}):
            if re.search(r"TOKEN|SECRET|API_KEY|AUTH|CREDENTIAL|^GH_|^GITHUB_|^COPILOT_|^PI_|^SSH_", key, re.I):
                raise FactoryError("Compose: credentials or Pi configuration must not be supplied through environment")
        for volume in spec.get("volumes", []):
            if volume.get("type") == "bind":
                if Path(volume["source"]).resolve() != workspace.resolve() or volume.get("target") != "/workspace":
                    raise FactoryError("Compose: bind mounts must expose only FACTORY_WORKSPACE at /workspace")
            elif volume.get("type") != "volume" or volume.get("source"):
                raise FactoryError("Compose: only workspace binds and anonymous volumes are supported")
        spec.update(restart="no", cap_drop=["ALL"], security_opt=["no-new-privileges:true"])
    agent = services[service]
    if agent.get("working_dir") != "/workspace" or not any(
        v.get("type") == "bind" and v.get("target") == "/workspace" for v in agent.get("volumes", [])
    ):
        raise FactoryError("Compose: agent needs working_dir /workspace and a FACTORY_WORKSPACE bind")
    agent.update(entrypoint=["sleep", "infinity"], command=[], init=True)
    return result


# Validate bearer metadata without exposing it; only known Copilot endpoints and ≥20-minute lifetime are accepted.
def copilot_endpoint(bearer: str) -> str:
    endpoint = re.search(r"(?:^|;)proxy-ep=proxy\.(individual|business|enterprise)\.githubcopilot\.com(?:;|$)", bearer)
    expiry = re.search(r"(?:^|;)exp=(\d+)(?:;|$)", bearer)
    if not endpoint or not expiry or int(expiry[1]) - time.time() < 1200:
        raise FactoryError("Copilot bearer requires validated endpoint metadata and at least 20 minutes remaining")
    return f"https://api.{endpoint[1]}.githubcopilot.com"


# Carry only completed verification's redacted output for repair; the public error stays concise.
class VerificationFailed(FactoryError):
    # Keep local feedback separate from the operator-visible summary to avoid publishing transcripts.
    def __init__(self, output: str) -> None:
        super().__init__("verification failed")
        self.output = output


# Own a unique Compose project and immutable host-side configuration outside the exposed workspace.
class Sandbox:
    # Persist the prepared configuration outside the workspace; commands share the issue-run deadline.
    def __init__(self, prepared_compose: dict, service: str, directory: Path, commands: Commands) -> None:
        self.service = service
        self.commands = commands
        self.directory = directory
        self.env = docker_environment(directory / "workspace")
        self.path = directory / "compose.json"
        self.path.write_text(json.dumps(prepared_compose))
        self.project = "factory-" + uuid.uuid4().hex
        self.base = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            "/dev/null",
            "-f",
            str(self.path),
        ]

    # Start the complete prepared dependency environment without builds or autonomous restart behavior.
    def start(self) -> None:
        self.commands.run(
            self.base + ["up", "-d", "--no-build", "--wait"], "sandbox startup", cwd=self.directory, env=self.env
        )

    # Require both canonical scripts before running setup; all repository commands remain inside the container.
    def setup(self) -> None:
        self.commands.run(
            self.base + ["exec", "-T", self.service, "sh", "-c", "test -x ./scripts/setup && test -x ./scripts/verify"],
            "required entrypoints",
            cwd=self.directory,
            env=self.env,
        )
        self.commands.run(
            self.base + ["exec", "-T", self.service, "./scripts/setup"], "setup", cwd=self.directory, env=self.env
        )

    # Send the immutable task, bearer, and optional failed-check feedback to a fresh nonpersistent Pi invocation.
    def implement(
        self, snapshot: dict, bearer: str, endpoint: str, model: str, *, verification_output: str | None = None
    ) -> None:
        script = Path(__file__).with_name("sandbox_agent.mjs").read_text()
        self.commands.run(
            self.base + ["exec", "-T", self.service, "node", "--input-type=module", "-e", script],
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

    # Separate completed repository check failures from missing scripts, Docker errors, or deadline expiry.
    def verify(self) -> None:
        output = self.commands.run(
            self.base
            + [
                "exec",
                "-T",
                self.service,
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

    # Attempt cleanup with a separate bounded budget even after run expiry; propagate failures for local reporting.
    def stop(self) -> None:
        Commands(log=self.commands.log).run(
            self.base + ["down", "--volumes", "--remove-orphans", "--timeout", "0"],
            "sandbox cleanup",
            cwd=self.directory,
            env=self.env,
        )
