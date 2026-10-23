# Keep host Git metadata outside the sandbox workspace and publish through trusted configuration only.
import os
from pathlib import Path

from software_factory.process import Commands, FactoryError


# Manage a fresh checkout and host-side commits without loading repository-supplied Git settings or hooks.
class Repository:
    # Create an exposed workspace and a separate, unexposed Git directory under the private run directory.
    def __init__(self, directory: Path, commands: Commands) -> None:
        self.directory = directory
        self.commands = commands
        self.workspace = directory / "workspace"
        self.workspace.mkdir()
        self.metadata = directory / "host.git"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_SYSTEM="/dev/null",
            GIT_ATTR_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
        )
        self.git("init")

    # Execute Git with explicit trusted metadata, no hooks/fsmonitor/global filters, and host gh authentication.
    def git(self, *args: str) -> str:
        return self.commands.run(
            [
                "git",
                "--git-dir=" + str(self.metadata),
                "--work-tree=" + str(self.workspace),
                "-c",
                "core.bare=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.attributesFile=/dev/null",
                "-c",
                "credential.helper=",
                "-c",
                "credential.helper=!gh auth git-credential",
                "-c",
                "user.name=Autonomous coding factory",
                "-c",
                "user.email=factory@localhost",
                *args,
            ],
            "git " + args[0],
            cwd=self.directory,
            env=self.env,
        )

    # Fetch and check out the current default branch with no submodules or repository scripts run on the host.
    def checkout(self, url: str, branch: str) -> str:
        self.git("check-ref-format", "refs/heads/" + branch)
        self.git("fetch", "--no-tags", "--", url, "refs/heads/" + branch)
        self.git("checkout", "--force", "--detach", "FETCH_HEAD")
        return self.git("rev-parse", "HEAD").strip()

    # Stage current files using only trusted Git metadata, require changes, and create a runner-owned commit.
    def commit(self, number: int) -> str:
        # shortcut: nested repositories are rejected; add safe gitlink handling when a target needs submodules.
        for directory, dirs, files in os.walk(self.workspace, followlinks=False):
            if Path(directory) == self.workspace:
                dirs[:] = [name for name in dirs if name.lower() != ".git"]
            elif any(name.lower() == ".git" for name in dirs + files):
                raise FactoryError("nested Git metadata is not allowed during host publication")
        self.git("add", "--all", "--", ".")
        if not self.git("diff", "--cached", "--name-only", "--no-ext-diff"):
            raise FactoryError("no changes produced")
        self.git("commit", "--no-gpg-sign", "-m", f"Implement issue #{number}")
        return self.git("rev-parse", "HEAD").strip()

    # Refuse an existing factory branch and push once without force; ambiguous outcomes require operator inspection.
    def push(self, url: str, number: int) -> None:
        ref = f"refs/heads/factory/issue-{number}"
        if self.git("ls-remote", "--heads", "--", url, ref).strip():
            raise FactoryError("remote factory branch already exists; operator cleanup required")
        self.git("push", "--porcelain", "--", url, "HEAD:" + ref)
