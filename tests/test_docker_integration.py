import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from tests_support import IMAGE, target_repository

from software_factory.process import Commands, FactoryError
from software_factory.runner import local_docker_environment
from software_factory.sandbox import RUN_LABEL, Sandbox, VerificationFailed

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("FACTORY_DOCKER_TESTS") != "1",
        reason="set FACTORY_DOCKER_TESTS=1 and build the shared ARM64 image",
    ),
]


@pytest.fixture
def sandbox(tmp_path: Path):
    target_repository(tmp_path / "workspace")
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True))[0]
    assert image["Architecture"] == "arm64"
    env = local_docker_environment(Commands())
    instance = Sandbox(
        image["Id"], env["DOCKER_HOST"], tmp_path, Commands(time.monotonic() + 180, tmp_path / "run.log")
    )
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()
        for kind in ("container", "network", "volume"):
            assert not instance.owned(Commands(), kind), f"leftover owned {kind}"
        subprocess.run(["docker", "image", "rm", "software-factory-fixture:" + instance.project], capture_output=True)


def execute(instance, *args):
    return instance.commands.run(instance.base + list(args), "fixture command", env=instance.env)


def implement(instance):
    bearer = f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}"
    instance.commands.secrets.append(bearer)
    instance.implement(
        {"number": 1, "title": "implement fixture", "body": None},
        bearer,
        "https://api.business.githubcopilot.com",
        "chosen",
    )
    return bearer


def test_host_user_has_writable_home_caches_socket_and_explicit_root(sandbox) -> None:
    assert execute(sandbox, "id", "-u").strip() == str(os.getuid())
    assert execute(sandbox, "id", "-g").strip() == str(os.getgid())
    execute(sandbox, "sh", "-ec", 'mkdir -p "$XDG_CACHE_HOME"; touch "$HOME/home-write" "$XDG_CACHE_HOME/cache-write"')
    assert execute(sandbox, "sudo", "-n", "id", "-u").strip() == "0"
    execute(sandbox, "sudo", "-n", "sh", "-ec", 'test "$HOME" = "$(getent passwd 0 | cut -d: -f6)"')
    execute(sandbox, "sudo", "-n", "sh", "-ec", "printf installed > /usr/local/share/factory-system-install")
    assert execute(sandbox, "cat", "/usr/local/share/factory-system-install").strip() == "installed"
    execute(sandbox, "docker", "info")
    execute(sandbox, "sh", "-ec", "printf ordinary > ordinary-output")
    before = (sandbox.workspace / "ordinary-output").stat()
    sandbox.stop()
    after = (sandbox.workspace / "ordinary-output").stat()
    assert (before.st_uid, before.st_gid, before.st_mode) == (after.st_uid, after.st_gid, after.st_mode)
    assert after.st_uid == os.getuid()


def test_real_build_compose_socket_same_path_setup_pi_service_verify_and_host_access(sandbox) -> None:
    instance = sandbox
    assert execute(instance, "pwd").strip() == str(instance.workspace)
    assert execute(instance, "sh", "-ec", "command -v docker").strip() == "/usr/local/bin/docker"
    assert (
        execute(
            instance,
            "python",
            "-c",
            "from pathlib import Path; print(Path('/usr/local/bin/docker').read_bytes()[:4].hex()); "
            "assert not Path('/usr/local/libexec/factory/docker').exists()",
        ).strip()
        == "7f454c46"
    )
    assert execute(instance, "printenv", "DOCKER_DEFAULT_PLATFORM").strip() == "linux/arm64"
    assert execute(instance, "docker", "info", "--format", "{{.Architecture}}").strip() in {"aarch64", "arm64"}
    instance.setup()
    bearer = implement(instance)
    instance.verify()
    assert (instance.workspace / "service-response").read_text() == "implemented\n"
    inspected = json.loads(subprocess.check_output(["docker", "inspect", instance.project], text=True))[0]
    assert inspected["Config"]["User"] == f"{os.getuid()}:{os.getgid()}"
    assert {mount["Source"] for mount in inspected["Mounts"] if mount["Type"] == "bind"} == {
        str(instance.workspace),
        instance.socket_path,
    }
    assert not any(
        value.startswith(("GH_", "GITHUB_", "PI_CODING_AGENT_DIR=", "COPILOT_")) for value in inspected["Config"]["Env"]
    )
    instance.stop()
    private = instance.workspace / "private-file"
    assert private.read_text() == "host-writable\n"
    private.write_text("host changed it\n")
    assert private.stat().st_uid == os.getuid()
    assert private.stat().st_gid == os.getgid()
    assert (instance.directory / "run.log").stat().st_mode & 0o777 == 0o600
    assert bearer not in (instance.directory / "run.log").read_text()


def test_root_user_configuration_does_not_import_workspace_python_modules(sandbox) -> None:
    sandbox.stop()
    (sandbox.workspace / "uuid.py").write_text("raise RuntimeError('untrusted workspace import')\n")
    instance = Sandbox(sandbox.image_id, sandbox.env["DOCKER_HOST"], sandbox.directory, Commands())
    try:
        instance.start()
        assert execute(instance, "id", "-u").strip() == str(os.getuid())
    finally:
        instance.stop()


def test_cleanup_preserves_file_modes_ownership_symlinks_and_git_diff(sandbox) -> None:
    execute(
        sandbox,
        "sh",
        "-ec",
        "printf readonly > readonly; chmod 444 readonly; "
        "printf executable > group-executable; chmod 654 group-executable; "
        "ln -s /etc/passwd external-link",
    )
    files = [sandbox.workspace / name for name in ("readonly", "group-executable", "external-link")]
    before = [(path.lstat().st_uid, path.lstat().st_gid, path.lstat().st_mode) for path in files]
    git = ["git", "-C", str(sandbox.workspace)]
    subprocess.run(git + ["init"], check=True, capture_output=True)
    subprocess.run(git + ["add", "."], check=True, capture_output=True)
    diff = subprocess.check_output(git + ["diff", "--cached", "--raw"])
    sandbox.stop()
    assert [(path.lstat().st_uid, path.lstat().st_gid, path.lstat().st_mode) for path in files] == before
    subprocess.run(git + ["add", "."], check=True, capture_output=True)
    assert subprocess.check_output(git + ["diff", "--cached", "--raw"]) == diff
    assert os.readlink(files[-1]) == "/etc/passwd"


def test_service_verification_failure_is_completed_private_feedback(sandbox) -> None:
    sandbox.setup()
    with pytest.raises(VerificationFailed) as failure:
        sandbox.verify()
    assert str(failure.value) == "verification failed"
    assert (sandbox.workspace / "service-response").read_text() == "before\n"


@pytest.mark.parametrize("entrypoint", ["setup", "verify"])
@pytest.mark.parametrize("invalid", ["missing", "nonexecutable"])
def test_invalid_entrypoint_prevents_setup(sandbox, entrypoint, invalid) -> None:
    path = sandbox.workspace / "scripts" / entrypoint
    if invalid == "missing":
        path.unlink()
    else:
        path.chmod(0o644)
    setup = sandbox.workspace / "scripts/setup"
    if setup.exists():
        setup.write_text(setup.read_text() + "touch setup-ran\n")
    with pytest.raises(FactoryError, match="required entrypoints"):
        sandbox.setup()
    assert not (sandbox.workspace / "setup-ran").exists()
    assert not sandbox.owned(Commands(), "network")


def test_setup_permission_failure_is_not_retried_as_root(sandbox) -> None:
    setup = sandbox.workspace / "scripts/setup"
    setup.write_text("#!/bin/sh\nprintf denied > /usr/local/share/forbidden-install\n")
    with pytest.raises(FactoryError, match="setup failed"):
        sandbox.setup()
    execute(sandbox, "test", "!", "-e", "/usr/local/share/forbidden-install")


def test_setup_failure_never_becomes_implementation(sandbox) -> None:
    setup = sandbox.workspace / "scripts/setup"
    setup.write_text(setup.read_text() + "printf diagnostic > setup-diagnostic\nexit 8\n")
    with pytest.raises(FactoryError, match="setup failed"):
        sandbox.setup()
    assert len(sandbox.owned(Commands(), "container")) == 2
    sandbox.stop()
    assert not sandbox.owned(Commands(), "container")
    assert (sandbox.workspace / "setup-diagnostic").read_text() == "diagnostic"


def test_deadline_kills_daemon_work_during_scoped_cleanup(sandbox) -> None:
    (sandbox.workspace / "scripts/setup").write_text("#!/bin/sh\nsleep 3\ntouch too-late\n")
    sandbox.commands.deadline = time.monotonic() + 0.3
    with pytest.raises(FactoryError, match="deadline"):
        sandbox.setup()
    sandbox.stop()
    time.sleep(3)
    assert not (sandbox.workspace / "too-late").exists()


def test_cleanup_preserves_unrelated_resources_and_ignores_mutated_compose(sandbox) -> None:
    instance = sandbox
    sentinel = "factory-sentinel-" + uuid.uuid4().hex
    commands = Commands()
    for kind in ("network", "volume"):
        commands.run(["docker", kind, "create", sentinel], "sentinel setup", env=instance.env)
    commands.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            sentinel,
            "--network",
            sentinel,
            "--mount",
            f"type=volume,src={sentinel},dst=/data",
            "--entrypoint",
            "sleep",
            instance.image_id,
            "infinity",
        ],
        "sentinel setup",
        env=instance.env,
    )
    try:
        instance.setup()
        execute(
            instance,
            "docker",
            "volume",
            "create",
            "--label",
            f"{RUN_LABEL}={instance.project}",
            instance.project + "-direct",
        )
        execute(
            instance,
            "docker",
            "network",
            "create",
            "--label",
            f"{RUN_LABEL}={instance.project}",
            instance.project + "-direct",
        )
        execute(
            instance,
            "docker",
            "run",
            "--detach",
            "--label",
            f"{RUN_LABEL}={instance.project}",
            "--network",
            instance.project + "-direct",
            "--entrypoint",
            "sleep",
            IMAGE,
            "infinity",
        )
        (instance.workspace / "compose.yaml").write_text("this is not valid Compose; never execute my teardown\n")
        instance.stop()
        for kind in ("container", "network", "volume"):
            assert not instance.owned(Commands(), kind)
            commands.run(["docker", kind, "inspect", sentinel], "sentinel preserved", env=instance.env)
    finally:
        commands.run(["docker", "rm", "--force", sentinel], "sentinel cleanup", env=instance.env)
        for kind in ("network", "volume"):
            commands.run(["docker", kind, "rm", sentinel], "sentinel cleanup", env=instance.env)


def test_partial_agent_start_is_cleaned_using_host_owned_identity(sandbox) -> None:
    sandbox.stop()

    class LostStartupResponse(Commands):
        def run(self, args, phase, **kwargs):
            result = super().run(args, phase, **kwargs)
            if phase == "agent startup":
                raise FactoryError("startup response lost")
            return result

    partial = Sandbox(sandbox.image_id, sandbox.env["DOCKER_HOST"], sandbox.directory, LostStartupResponse())
    try:
        with pytest.raises(FactoryError, match="startup response lost"):
            partial.start()
    finally:
        partial.stop()
    assert not partial.owned(Commands(), "container")


def test_removed_verify_and_stopped_agent_are_not_completed_verification(sandbox) -> None:
    (sandbox.workspace / "scripts/verify").unlink()
    with pytest.raises(FactoryError) as failure:
        sandbox.verify()
    assert not isinstance(failure.value, VerificationFailed)
    sandbox.stop()
    with pytest.raises(FactoryError) as failure:
        sandbox.verify()
    assert not isinstance(failure.value, VerificationFailed)


def test_cleanup_failure_preserves_permissions_when_owned_network_is_still_in_use(sandbox) -> None:
    instance = sandbox
    execute(instance, "sh", "-ec", "printf retained > cleanup-diagnostic; chmod 000 cleanup-diagnostic")
    private = instance.workspace / "cleanup-diagnostic"
    name = instance.project + "-shared"
    execute(instance, "docker", "network", "create", "--label", f"{RUN_LABEL}={instance.project}", name)
    Commands().run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            name,
            "--entrypoint",
            "sleep",
            instance.image_id,
            "infinity",
        ],
        "unowned resource setup",
        env=instance.env,
    )
    try:
        with pytest.raises(FactoryError, match="cleanup failed"):
            instance.stop()
        assert private.stat().st_mode & 0o777 == 0
        assert private.stat().st_uid == os.getuid()
        assert private.stat().st_gid == os.getgid()
        assert not instance.owned(Commands(), "container")
        Commands().run(["docker", "container", "inspect", name], "unowned resource preserved", env=instance.env)
    finally:
        private.chmod(0o600)  # Explicit test-fixture disposal, not factory permission repair.
        Commands().run(["docker", "rm", "--force", name], "unowned resource cleanup", env=instance.env)
