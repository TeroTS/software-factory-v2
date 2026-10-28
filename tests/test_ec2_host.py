import os
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest
from test_ec2 import ROOT, SCRIPTS, bootstrap_script


def functions() -> str:
    return "\n".join(
        (SCRIPTS / name).read_text()
        for name in ("shared/prepare-storage.sh", "builder/bake-host.sh", "factory/prepare-host.sh")
    )


def run_shell(code: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" + code],
        env={**os.environ, "TEST_ROOT": str(tmp_path), **env},
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_boot_uses_baked_tools_and_orders_storage_before_docker(tmp_path: Path) -> None:
    script = bootstrap_script()
    assert len(script.encode()) < 16384
    assert "git clone" not in script
    assert "software-factory-storage-ready" not in script
    assert "software_factory.provision" not in script
    for retired in (
        "src/software_factory/provision.py",
        "scripts/provision-host",
        "infra/lima/factory.yaml",
        "tests/test_provision.py",
        "tests/test_provision_lima.py",
        "tests/test_lima.py",
    ):
        assert not (ROOT / retired).exists(), f"Retire the old provisioning path: {retired}"
    code = (SCRIPTS / "factory/prepare-host.sh").read_text()
    assert "apt-get" not in code and "curl" not in code
    code = code.replace("volume=$(</etc/software-factory/volume-id)", "volume=vol-test")
    boundaries = """
validate_host() { echo host; }
validate_identity() { echo identity; }
systemd-analyze() { echo verify; }
systemctl() { echo "systemctl $*"; }
prepare_storage() { echo storage; }
"""
    code = code.replace("/usr/local/sbin/factory-prepare-storage", "prepare_storage")
    code = code.replace("/usr/local/sbin/factory-host-check", "echo readiness")
    result = run_shell(code + boundaries + "prepare_host vol-test", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "host",
        "identity",
        "storage",
        "systemctl unmask docker.service docker.socket containerd.service",
        "verify",
        "systemctl enable --now docker",
        "readiness",
    ]


@pytest.mark.parametrize(
    "phase", ["validate_host", "prepare_storage", "validate_identity", "systemctl", "systemd-analyze"]
)
def test_preparation_failure_never_reports_readiness(tmp_path: Path, phase: str) -> None:
    code = (SCRIPTS / "factory/prepare-host.sh").read_text()
    code = code.replace("volume=$(</etc/software-factory/volume-id)", "volume=vol-test")
    code = code.replace("/usr/local/sbin/factory-prepare-storage", "prepare_storage")
    code = code.replace("/usr/local/sbin/factory-host-check", "echo unexpected")
    boundaries = "\n".join(
        f'{name}() {{ echo "{name} $*"; {"return 1" if name == phase else ":"}; }}'
        for name in ("validate_host", "systemctl", "prepare_storage", "validate_identity", "systemd-analyze")
    )
    result = run_shell(code + boundaries + "\nprepare_host vol-test", tmp_path)
    assert result.returncode != 0
    assert "unexpected" not in result.stdout
    assert "ready" not in result.stdout.lower()
    assert "systemctl enable --now docker" not in result.stdout
    if phase in {"validate_host", "prepare_storage", "validate_identity"}:
        assert "systemctl unmask" not in result.stdout


@pytest.mark.parametrize("conflict", ["user-name", "user-id", "user-group", "group-name", "group-id", "home"])
def test_account_conflicts_fail_before_mutation(tmp_path: Path, conflict: str) -> None:
    boundary = """
getent() {
  case "$CONFLICT:$1:$2" in
    user-name:passwd:factory) echo factory:x:2001:2000::/home/factory:/bin/bash;;
    user-id:passwd:2000) echo other:x:2000:2000::/home/other:/bin/bash;;
    user-group:passwd:factory) echo factory:x:2000:1000::/home/factory:/bin/bash;;
    home:passwd:factory) echo factory:x:2000:2000::/other:/bin/bash;;
    group-name:group:factory) echo factory:x:2001:;;
    group-id:group:2000) echo other:x:2000:;;
    *) return 2;;
  esac
}
groupadd() { echo MUTATED; }
useradd() { echo MUTATED; }
"""
    result = run_shell(functions() + boundary + "ensure_account", tmp_path, CONFLICT=conflict)
    assert result.returncode != 0
    assert "MUTATED" not in result.stdout


@pytest.mark.parametrize("existing", ["0", "1"])
def test_account_creation_uses_fixed_ids_without_home_or_sudo_repair(tmp_path: Path, existing: str) -> None:
    boundary = """
getent() {
  [ "$EXISTING" = 1 ] || return 2
  case "$1" in
    passwd) echo factory:x:2000:2000::/home/factory:/bin/bash;;
    group) echo factory:x:2000:;;
  esac
}
groupadd() { echo "groupadd $*"; }
useradd() { echo "useradd $*"; }
"""
    result = run_shell(functions() + boundary + "ensure_account", tmp_path, EXISTING=existing)
    assert result.returncode == 0, result.stderr
    if existing == "1":
        assert not result.stdout
    else:
        assert result.stdout.splitlines() == [
            "groupadd --gid 2000 factory",
            "useradd --uid 2000 --gid 2000 --no-create-home --home-dir /home/factory --shell /bin/bash factory",
        ]


@pytest.mark.parametrize(
    "failure",
    [
        "",
        "update",
        "install",
        "aws-download",
        "aws-unzip",
        "aws-install",
        "aws-existing",
        "curl",
        "checksum",
        "docker-install",
    ],
)
def test_signed_package_installation_fails_closed(tmp_path: Path, failure: str) -> None:
    code = functions().replace("/etc/apt/keyrings", str(tmp_path / "keyrings"))
    code = code.replace("/etc/apt/sources.list.d", str(tmp_path / "sources"))
    (tmp_path / "sources").mkdir()
    boundary = """
test() {
  case "$1:$2" in
    -e:/usr/local/aws-cli|-e:/usr/bin/aws|-e:/usr/bin/aws_completer) [ "$FAILURE" = aws-existing ];;
    -L:/usr/local/aws-cli|-L:/usr/bin/aws|-L:/usr/bin/aws_completer) return 1;;
    *) builtin test "$@";;
  esac
}
apt-get() {
  echo "apt-get $*" >> "$TEST_ROOT/events"
  if [ ! -f "$TEST_ROOT/ubuntu-sources" ]; then cp "$work/sources.list" "$TEST_ROOT/ubuntu-sources"; fi
  case "$FAILURE:$*" in
    update:*update*|install:*install*|docker-install:*docker-ce*) return 1;;
  esac
}
curl() {
  echo "curl $*" >> "$TEST_ROOT/events"
  case "${@: -1}" in
    https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip) [ "$FAILURE" != aws-download ];;
    https://download.docker.com/linux/ubuntu/gpg)
      [ "$FAILURE" != curl ] || return 1
      printf key > "$work/docker.asc";;
    *) return 1;;
  esac
}
unzip() {
  echo "unzip $* umask=$(umask)" >> "$TEST_ROOT/events"
  [ "$FAILURE" != aws-unzip ] || return 1
  mkdir -p "$work/aws"
  printf '%s\\n' '#!/bin/sh' \
    'echo "aws-install $* umask=$(umask)" >> "$TEST_ROOT/events"' \
    'test "$FAILURE" != aws-install' > "$work/aws/install"
  chmod 0755 "$work/aws/install"
}
sha256sum() {
  echo checksum >> "$TEST_ROOT/events"
  [ "$FAILURE" != checksum ]
}
usermod() { echo "usermod $*" >> "$TEST_ROOT/events"; }
systemctl() { echo "systemctl $*" >> "$TEST_ROOT/events"; }
"""
    result = run_shell(code + boundary + "install_docker", tmp_path, FAILURE=failure)
    assert (result.returncode == 0) is (not failure), result.stderr
    events = (tmp_path / "events").read_text()
    assert "--allow-unauthenticated" not in events
    assert "--no-remove" in events or failure == "update"
    assert "--no-install-recommends" in events or failure == "update"
    assert "systemctl enable --now docker" not in events
    if not failure:
        assert "usermod --append --groups docker factory" in events
        assert "docker-ce docker-ce-cli containerd.io" in events
        prerequisites = next(line for line in events.splitlines() if "install --yes" in line)
        assert "awscli" not in prerequisites
        assert "unzip" in prerequisites
        assert "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" in events
        assert "--proto =https --proto-redir =https" in events
        assert "aws-install --install-dir /usr/local/aws-cli --bin-dir /usr/bin umask=0022" in events
        assert ".sig" not in events
        assert "gpg --verify" not in code
        assert "systemctl start" not in events
        ubuntu = (tmp_path / "ubuntu-sources").read_text().splitlines()
        assert len(ubuntu) == 3
        for suite, source in zip(("noble", "noble-updates", "noble-security"), ubuntu, strict=True):
            assert source.endswith(f"{suite} main")
            assert "signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg" in source
        assert (tmp_path / "keyrings/docker.asc").stat().st_mode & 0o777 == 0o644
        source = (tmp_path / "sources/factory-docker.list").read_text()
        assert "signed-by=" in source
        assert "https://download.docker.com/linux/ubuntu noble stable" in source
    elif failure in {"curl", "checksum"}:
        assert "docker-ce" not in events


@pytest.mark.parametrize("failure", ["", "token", "login", "pull", "temp"])
def test_documented_ecr_pull_uses_temporary_login_and_fails_closed(tmp_path: Path, failure: str) -> None:
    procedure = (ROOT / "docs/operations.md").read_text().split("```bash\n", 1)[1].split("```", 1)[0]
    prior = tmp_path / "prior-login"
    prior.mkdir()
    (prior / "config.json").write_text("preserve-existing-login")
    boundary = """
mktemp() {
  [ "$FAILURE" != temp ] || return 1
  command mktemp -d "$TEST_ROOT/login.XXXXXX"
}
aws() {
  [ "$FAILURE" != token ] || return 1
  printf fixture-token
}
docker() {
  [ "$1" = --host ] && [ "$2" = unix:///var/run/docker.sock ]
  shift 2
  echo "$*" >> "$TEST_ROOT/events"
  case "$1" in
    login)
      [ "$(cat)" = fixture-token ]
      printf private-login > "$DOCKER_CONFIG/config.json"
      [ "$FAILURE" != login ];;
    pull) [ "$FAILURE" != pull ];;
    *) return 1;;
  esac
}
"""
    result = run_shell(
        boundary + procedure,
        tmp_path,
        FAILURE=failure,
        DOCKER_CONFIG=str(prior),
        RUNNER_IMAGE="registry/runner@sha256:" + "a" * 64,
        AGENT_IMAGE="registry/agent@sha256:" + "b" * 64,
    )
    assert (result.returncode == 0) is (not failure), result.stderr
    assert not list(tmp_path.glob("login.*"))
    assert (prior / "config.json").read_text() == "preserve-existing-login"
    assert "fixture-token" not in result.stdout + result.stderr
    events = (tmp_path / "events").read_text() if (tmp_path / "events").exists() else ""
    assert ("registry/agent" in events) is (not failure)
    if failure in {"token", "login", "temp"}:
        assert "pull " not in events


def installed_checker(tmp_path: Path) -> Path:
    destination = tmp_path / "factory-host-check"
    volume = tmp_path / "volume-id"
    volume.write_text("vol-test\n")
    destination.write_text(
        (SCRIPTS / "factory/check-host.sh").read_text().replace("/etc/software-factory/volume-id", str(volume))
    )
    destination.chmod(0o755)
    return destination


def test_readiness_checker_is_standalone_read_only_and_installed_executable(tmp_path: Path) -> None:
    checker = installed_checker(tmp_path)
    assert checker.stat().st_mode & 0o777 == 0o755
    check = checker.read_text()
    subprocess.run(["bash", "-n", str(checker)], check=True, capture_output=True, timeout=10)
    assert "volume=$(<" in check
    assert "runuser -u factory -- env -i" in check
    assert "unix:///var/run/docker.sock" in check
    for forbidden in ("apt-get", "mkfs", "usermod", "chown", "chmod", "systemctl start", "touch"):
        assert forbidden not in check


def test_readiness_missing_volume_setting_is_an_observable_failure(tmp_path: Path) -> None:
    checker = installed_checker(tmp_path)
    (tmp_path / "volume-id").unlink()
    result = subprocess.run(["bash", str(checker)], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "Host readiness failed at line" in result.stderr
    assert "Factory host ready" not in result.stdout


@pytest.mark.parametrize(
    "failure",
    [
        "",
        "uid",
        "arch",
        "release",
        "volume",
        "filesystem",
        "mount",
        "identity",
        "home",
        "sudo",
        "socket",
        "engine",
        "access",
        "aws-missing",
        "aws-broken",
    ],
)
def test_readiness_checks_real_script_and_reports_success_only_at_end(tmp_path: Path, failure: str) -> None:
    checker = installed_checker(tmp_path).read_text()
    root = tmp_path / "host"
    root.mkdir()
    release = root / "os-release"
    release.write_text('ID=ubuntu\nVERSION_ID="22.04"\n' if failure == "release" else 'ID=ubuntu\nVERSION_ID="24.04"\n')
    checker = checker.replace("/etc/os-release", str(release))
    checker = checker.replace("/srv/software-factory", str(root / "data"))
    for name, target in (
        ("home", "/home/factory"),
        ("docker", "/var/lib/docker"),
        ("containerd", "/var/lib/containerd"),
    ):
        source = root / "data" / name
        source.mkdir(parents=True)
        link = root / name
        link.symlink_to(source, target_is_directory=True)
        checker = checker.replace(target, str(link))
    # AF_UNIX paths are short on macOS, so keep the socket outside pytest's long temporary path.
    with tempfile.TemporaryDirectory(prefix="ec2-check-", dir="/tmp") as directory:
        endpoint = Path(directory) / "sock"
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(endpoint))
            checker = checker.replace("/var/run/docker.sock", str(endpoint))
            boundary = """
uname() {
  if [ "$1" = -s ]; then echo Linux
  elif [ "$FAILURE" = arch ]; then echo x86_64
  else echo aarch64; fi
}
id() {
  if [ "$FAILURE" = uid ]; then echo 1000
  elif [ "$FAILURE" = identity ] && [ "$#" = 2 ]; then echo 1000
  elif [ "$#" = 1 ]; then echo 0
  else echo 2000; fi
}
findmnt() {
  if [ "$2" = SOURCE ]; then echo /dev/test
  elif [ "$FAILURE" = filesystem ]; then echo xfs
  else echo ext4; fi
}
lsblk() { if [ "$FAILURE" = volume ]; then echo vol-wrong; else echo vol-test; fi; }
mountpoint() { [ "$FAILURE" != mount ]; }
getent() { echo "factory:x:2000:2000::$TEST_ROOT/host/home:/bin/bash"; }
stat() {
  if [ "$2" = %a ]; then
    if [ "$FAILURE" = socket ]; then echo 666; else echo 660; fi
  elif [ "$FAILURE" = home ]; then echo 0:0:755
  else echo 2000:2000:700; fi
}
timeout() { shift; "$@"; }
runuser() {
  case " $* " in
    *' sudo '*) [ "$FAILURE" = sudo ];;
    *' aws '*)
      printf '%s\\n' "$*" >> "$TEST_ROOT/aws-check"
      case "$FAILURE" in aws-missing) return 127;; aws-broken) return 1;; esac
      echo 'aws-cli/2.fixture';;
    *' docker '*)
      [ "$FAILURE" != access ] || return 1
      if [ "$FAILURE" = engine ]; then echo linux/x86_64; else echo linux/aarch64; fi;;
    *) return 0;;
  esac
}
"""
            result = run_shell(boundary + checker, tmp_path, FAILURE=failure)
    assert (result.returncode == 0) is (not failure), result.stderr
    assert ("Factory host ready" in result.stdout) is (not failure)
    if failure:
        assert "Host readiness failed at line" in result.stderr
    else:
        invocation = (tmp_path / "aws-check").read_text()
        assert "env -i" in invocation
        assert " aws --version" in invocation
        assert "get-login-password" not in invocation


@pytest.mark.parametrize("failure", ["", "uid", "arch", "release", "active"])
def test_ami_and_active_service_checks_precede_preparation(tmp_path: Path, failure: str) -> None:
    release = tmp_path / "os-release"
    release.write_text('ID=ubuntu\nVERSION_ID="22.04"\n' if failure == "release" else 'ID=ubuntu\nVERSION_ID="24.04"\n')
    code = functions().replace("/etc/os-release", str(release))
    boundary = """
id() { if [ "$FAILURE" = uid ]; then echo 1000; else echo 0; fi; }
uname() {
  if [ "$1" = -s ]; then echo Linux
  elif [ "$FAILURE" = arch ]; then echo x86_64
  else echo aarch64; fi
}
systemctl() { [ "$FAILURE" = active ]; }
"""
    result = run_shell(code + boundary + "validate_host", tmp_path, FAILURE=failure)
    assert (result.returncode == 0) is (not failure)


@pytest.mark.parametrize("failure", ["timeout", "serial"])
def test_storage_rejects_missing_or_wrong_volume_before_filesystem_operations(tmp_path: Path, failure: str) -> None:
    boundary = """
test() { if [ "$1" = -b ]; then [ "$FAILURE" != timeout ]; else builtin test "$@"; fi; }
function [ {
  if builtin [ "$#" = 4 ] && builtin [ "$1" = '!' ] && builtin [ "$2" = -b ]; then
    builtin [ "$FAILURE" = timeout ]
  else builtin [ "$@"; fi
}
seq() { printf '1\\n2\\n'; }
sleep() { echo wait; }
lsblk() {
  if [ "$3" = SERIAL ]; then echo vol-wrong; else echo UNEXPECTED; fi
}
mkfs.ext4() { echo UNEXPECTED; }
mount() { echo UNEXPECTED; }
"""
    result = run_shell(functions() + boundary + "prepare_storage vol-test", tmp_path, FAILURE=failure)
    assert result.returncode != 0
    assert "UNEXPECTED" not in result.stdout
    assert result.stdout.count("wait") == (2 if failure == "timeout" else 0)


@pytest.mark.parametrize("failure", ["", "root-files", "bind-files", "uuid", "home-owner", "fstab", "symlink"])
def test_storage_mounts_preserve_files_and_require_persistent_state(tmp_path: Path, failure: str) -> None:
    code = functions()
    paths = {
        "/srv/software-factory": tmp_path / "data",
        "/home/factory": tmp_path / "home",
        "/var/lib/docker": tmp_path / "docker",
        "/var/lib/containerd": tmp_path / "containerd",
        "/etc/systemd/system": tmp_path / "systemd",
        "/etc/fstab": tmp_path / "fstab",
    }
    for original, replacement in paths.items():
        code = code.replace(original, str(replacement))
    (tmp_path / "fstab").write_text(
        f"UUID=wrong {tmp_path}/data ext4 defaults 0 2\n" if failure == "fstab" else "# root entry preserved\n"
    )
    sentinel = None
    if failure in {"root-files", "bind-files"}:
        directory = tmp_path / ("data" if failure == "root-files" else "docker")
        directory.mkdir()
        sentinel = directory / "sentinel"
        sentinel.write_text("preserve")
    if failure == "symlink":
        (tmp_path / "data").symlink_to(tmp_path / "other")
    boundary = """
test() {
  if [ "$1" = -b ]; then return 0
  elif [ "$#" = 3 ] && [ "$2" = -ef ]; then return 0
  else builtin test "$@"; fi
}
function [ {
  if builtin [ "$#" = 4 ] && builtin [ "$1" = '!' ] && builtin [ "$2" = -b ]; then return 1
  else builtin [ "$@"; fi
}
lsblk() { if [ "$3" = SERIAL ]; then echo vol-test; else echo ext4; fi; }
blkid() { echo expected-uuid; }
findmnt() { if [ "$FAILURE" = uuid ]; then echo wrong-uuid; else echo expected-uuid; fi; }
mountpoint() {
  if [ "$FAILURE" = uuid ] && [ "$2" = "$TEST_ROOT/data" ]; then return 0; fi
  grep -Fxq -- "$2" "$TEST_ROOT/mounted" 2>/dev/null
}
mount() { printf '%s\\n' "${@: -1}" >> "$TEST_ROOT/mounted"; }
install() { mkdir -p "${@: -1}"; }
stat() { if [ "$FAILURE" = home-owner ]; then echo 0:0; else echo 2000:2000; fi; }
systemctl() { echo "systemctl $*"; }
"""
    result = run_shell(
        code + boundary + "prepare_storage vol-test\nprepare_storage vol-test", tmp_path, FAILURE=failure
    )
    assert (result.returncode == 0) is (not failure), result.stderr
    if sentinel:
        assert sentinel.read_text() == "preserve"
    if not failure:
        fstab = (tmp_path / "fstab").read_text()
        assert fstab.startswith("# root entry preserved\n")
        assert fstab.count("UUID=expected-uuid") == 1
        assert fstab.count("none bind,") == 3
        assert len((tmp_path / "mounted").read_text().splitlines()) == 4
        for service in ("docker", "containerd"):
            dropin = (tmp_path / "systemd" / f"{service}.service.d/factory-storage.conf").read_text()
            assert f"RequiresMountsFor={tmp_path}/data {tmp_path}/docker {tmp_path}/containerd" in dropin
            assert f"ExecStartPre=/usr/bin/mountpoint -q {tmp_path}/data" in dropin
            assert f"ExecStartPre=/usr/bin/mountpoint -q {tmp_path}/docker" in dropin
            assert f"ExecStartPre=/usr/bin/mountpoint -q {tmp_path}/containerd" in dropin
