# Orchestrate US-01 serial issue runs through GitHub, isolated Compose execution, verification, and host publication.
import copy
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from software_factory.config import Config
from software_factory.github import GitHub
from software_factory.process import Commands, FactoryError
from software_factory.repository import Repository
from software_factory.sandbox import PI_FLAGS, Sandbox, copilot_endpoint, docker_environment, prepare_compose

LOGGER = logging.getLogger("software_factory")


# Check host tools/authentication and freeze validated Compose configuration before any issue claim.
def preflight(config: Config) -> dict:
    for tool in ("git", "gh", "docker", "pi"):
        if shutil.which(tool) is None:
            raise FactoryError(f"required tool unavailable: {tool}")
    commands = Commands()
    commands.run(["docker", "info", "--format", "{{.ServerVersion}}"], "Docker readiness")
    commands.run(["docker", "compose", "version"], "Compose readiness")
    commands.run(["gh", "auth", "status", "--hostname", "github.com"], "GitHub authentication", private=True)
    placeholder = config.compose_file.parent / "artifacts" / ".workspace-placeholder"
    output = commands.run(
        ["docker", "compose", "--env-file", "/dev/null", "-f", str(config.compose_file), "config", "--format", "json"],
        "Compose configuration",
        env=docker_environment(placeholder),
        cwd=config.compose_file.parent,
    )
    try:
        data = json.loads(output)
    except ValueError:
        raise FactoryError("Compose returned invalid configuration JSON") from None
    return prepare_compose(data, config.compose_service, placeholder)


# Coordinate one repository without local recovery state; the operator must prevent simultaneous runner instances.
class Runner:
    # Accept immutable prepared Compose input; keep private artifacts beside the operator's Compose file by default.
    def __init__(self, config: Config, prepared: dict, artifacts: Path | None = None) -> None:
        self.config = config
        self.prepared = prepared
        self.artifacts = artifacts if artifacts is not None else config.compose_file.parent / "artifacts"
        self.artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Poll until operator interruption; read failures stay visible and do not authorize execution or automatic requeue.
    def run(self) -> None:
        while True:
            try:
                self.poll_once()
            except FactoryError as error:
                LOGGER.error("Polling failed: %s", error)
            time.sleep(30)

    # Discover and process issues serially; retained diagnostics are never interpreted as resumable jobs.
    def poll_once(self) -> None:
        github = GitHub(self.config.repository, Commands())
        for number in github.discover():
            self.process_issue(number)

    # Execute one first-pass issue run, retaining failures and always attempting container cleanup.
    def process_issue(self, number: int) -> None:
        directory = Path(tempfile.mkdtemp(prefix=f"issue-{number}-", dir=self.artifacts)).resolve()
        commands = Commands(time.monotonic() + 900, directory / "run.log")
        github = GitHub(self.config.repository, commands)
        claimed = False
        sandbox = None
        failure = None
        interrupted = False
        publication_started = False
        try:
            existing = github.open_pr(number)
            if existing:
                github.remove_trigger(number)
                github.comment(number, f"Skipped: existing open PR {existing}")
            elif github.branch_exists(number):
                github.remove_trigger(number)
                github.comment(number, f"Skipped: delete remote factory/issue-{number} and reapply agent:implement")
            else:
                github.remove_trigger(number)
                claimed = True
                github.comment(number, "Running: implementation started")
                snapshot = github.snapshot(number)
                base = github.default_branch()
                repository = Repository(directory, commands)
                url = f"https://github.com/{self.config.repository}.git"
                snapshot["base_commit"] = repository.checkout(url, base)
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
                    cwd=directory,
                    private=True,
                ).strip()
                commands.secrets.append(bearer)
                endpoint = copilot_endpoint(bearer)
                prepared = copy.deepcopy(self.prepared)
                for service in prepared["services"].values():
                    for volume in service.get("volumes", []):
                        if volume.get("type") == "bind":
                            volume["source"] = str(repository.workspace)
                sandbox = Sandbox(prepared, self.config.compose_service, directory, commands)
                sandbox.start()
                sandbox.setup()
                sandbox.implement(snapshot, bearer, endpoint, self.config.model)
                sandbox.verify()
                sandbox.stop()
                sandbox = None
                repository.commit(number)
                publication_started = True
                repository.push(url, number)
                pr = github.publish(number, snapshot["title"], base)
                github.comment(number, f"Succeeded: {pr}")
        except KeyboardInterrupt:
            failure = "operator interruption"
            interrupted = True
        except FactoryError as error:
            failure = str(error)
        except OSError:
            failure = "local workspace or diagnostics operation failed"
        finally:
            if sandbox is not None:
                try:
                    sandbox.stop()
                except FactoryError, OSError:
                    failure = failure or "sandbox cleanup failed"
                    LOGGER.error("Sandbox cleanup failed; inspect retained diagnostics at %s", directory)
        if failure:
            if publication_started:
                observed = GitHub(self.config.repository, Commands())
                try:
                    remote_pr = observed.open_pr(number)
                    if remote_pr:
                        failure += f"; remote PR observed: {remote_pr}; inspect before requeue"
                    elif observed.branch_exists(number):
                        failure += (
                            f"; remote branch exists: factory/issue-{number}; inspect and clean up before requeue"
                        )
                except FactoryError:
                    LOGGER.error("Issue #%s remote publication state could not be checked", number)
            LOGGER.error("Issue #%s failed: %s; diagnostics: %s", number, failure, directory)
            if claimed:
                try:
                    GitHub(self.config.repository, Commands()).comment(number, f"Failed: {failure}")
                except FactoryError:
                    LOGGER.error(
                        "GitHub failure reporting unavailable for issue #%s; diagnostics: %s", number, directory
                    )
        else:
            try:
                shutil.rmtree(directory)
            except OSError:
                LOGGER.warning("Could not remove successful workspace; retained at %s", directory)
        if interrupted:
            raise KeyboardInterrupt
