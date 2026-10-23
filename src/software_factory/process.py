# Execute host commands with a shared deadline, private diagnostics, and process-group termination.
import os
import signal
import subprocess
import time
from pathlib import Path


# Represent a safe, operator-visible failure without command output or credentials.
class FactoryError(Exception):
    pass


# Run argument-vector commands; enforce deadlines and optionally retain redacted private output.
class Commands:
    # Accept an absolute monotonic deadline and optional private log destination.
    def __init__(self, deadline: float | None = None, log: Path | None = None) -> None:
        self.deadline = deadline
        self.log = log
        self.secrets: list[str] = []

    # Return output or raise a sanitized failure; terminate descendants on timeout or interruption.
    def run(
        self,
        args: list[str],
        phase: str,
        *,
        input: str | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        private: bool = False,
    ) -> str:
        timeout = 60.0 if self.deadline is None else self.deadline - time.monotonic()
        if timeout <= 0:
            raise FactoryError("issue-run deadline expired")
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        except OSError:
            raise FactoryError(f"{phase}: tool unavailable or command could not start") from None
        failure = None
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except BaseException as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            failure = (
                FactoryError("issue-run deadline expired") if isinstance(error, subprocess.TimeoutExpired) else error
            )
        if self.log is not None and not private:
            output = f"[{phase}] exit={process.returncode}\n{stdout}\n{stderr}\n"
            for secret in self.secrets:
                output = output.replace(secret, "[REDACTED]")
            fd = os.open(self.log, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "a") as stream:
                stream.write(output)
        if failure is not None:
            raise failure
        if process.returncode:
            raise FactoryError(f"{phase} failed (exit {process.returncode})")
        return stdout
