import hashlib
import importlib
import io
import json
import stat
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from software_factory.process import FactoryError


def test_provisioning_script_rejects_macos_before_bootstrap():
    script = Path(__file__).resolve().parents[1] / "scripts/provision-host"
    assert script.is_file(), "Explicit host provisioning entrypoint is missing"
    if sys.platform != "darwin":
        pytest.skip("Direct macOS rejection is checked on macOS")
    result = subprocess.run([str(script), "--check"], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "Linux" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.fixture
def host():
    return importlib.import_module("software_factory.provision")


@pytest.mark.parametrize(
    "system,machine,release,uid",
    [
        ("Darwin", "arm64", {"ID": "ubuntu", "VERSION_ID": "24.04"}, 0),
        ("Linux", "x86_64", {"ID": "ubuntu", "VERSION_ID": "24.04"}, 0),
        ("Linux", "aarch64", {"ID": "debian", "VERSION_ID": "24.04"}, 0),
        ("Linux", "aarch64", {"ID": "ubuntu", "VERSION_ID": "22.04"}, 0),
        ("Linux", "aarch64", {"ID": "ubuntu", "VERSION_ID": "24.04"}, 2000),
    ],
)
def test_host_rejects_unsupported_or_unprivileged_invocation(host, monkeypatch, system, machine, release, uid):
    monkeypatch.setattr(host.platform, "system", lambda: system)
    monkeypatch.setattr(host.platform, "machine", lambda: machine)
    monkeypatch.setattr(host.platform, "freedesktop_os_release", lambda: release)
    monkeypatch.setattr(host.os, "geteuid", lambda: uid)
    with pytest.raises(FactoryError):
        host.validate_host()


def test_host_accepts_explicit_ubuntu_administrator(host, monkeypatch):
    monkeypatch.setattr(host.platform, "system", lambda: "Linux")
    monkeypatch.setattr(host.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(host.platform, "freedesktop_os_release", lambda: {"ID": "ubuntu", "VERSION_ID": "24.04"})
    monkeypatch.setattr(host.os, "geteuid", lambda: 0)
    host.validate_host()


def accounts(host, monkeypatch, users=(), groups=()):
    def find(items, field, value):
        for item in items:
            if getattr(item, field) == value:
                return item
        raise KeyError(value)

    monkeypatch.setattr(host.pwd, "getpwnam", lambda n: find(users, "pw_name", n))
    monkeypatch.setattr(host.pwd, "getpwuid", lambda n: find(users, "pw_uid", n))
    monkeypatch.setattr(host.grp, "getgrnam", lambda n: find(groups, "gr_name", n))
    monkeypatch.setattr(host.grp, "getgrgid", lambda n: find(groups, "gr_gid", n))


@pytest.mark.parametrize(
    "users,groups",
    [
        ([SimpleNamespace(pw_name="other", pw_uid=2000, pw_gid=2000)], []),
        ([SimpleNamespace(pw_name="factory", pw_uid=2001, pw_gid=2000)], []),
        ([SimpleNamespace(pw_name="factory", pw_uid=2000, pw_gid=1000)], []),
        ([], [SimpleNamespace(gr_name="other", gr_gid=2000)]),
        ([], [SimpleNamespace(gr_name="factory", gr_gid=2001)]),
    ],
)
def test_identity_conflicts_do_not_mutate_accounts(host, monkeypatch, users, groups):
    accounts(host, monkeypatch, users, groups)
    with pytest.raises(FactoryError, match="conflict"):
        host.validate_identity()


def test_identity_accepts_missing_or_matching_accounts(host, monkeypatch):
    accounts(host, monkeypatch)
    host.validate_identity()
    accounts(
        host,
        monkeypatch,
        [SimpleNamespace(pw_name="factory", pw_uid=2000, pw_gid=2000)],
        [SimpleNamespace(gr_name="factory", gr_gid=2000)],
    )
    host.validate_identity()


def test_managed_files_preserve_existing_state_and_reject_symlinks(host, tmp_path):
    path = tmp_path / "managed"
    host.write_once(path, b"expected")
    original = path.stat().st_mtime_ns
    host.write_once(path, b"expected")
    assert path.stat().st_mtime_ns == original
    with pytest.raises(FactoryError, match="existing"):
        host.write_once(path, b"different")
    assert path.read_bytes() == b"expected"
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(FactoryError):
        host.write_once(link, b"expected")


@pytest.mark.parametrize("bad", [False, True])
def test_download_checks_actual_bytes(host, monkeypatch, tmp_path, bad):
    class Response(io.BytesIO):
        def geturl(self):
            return "https://official.example/release"

    monkeypatch.setattr(host.urllib.request, "urlopen", lambda *a, **k: Response(b"release"))
    path = tmp_path / "download"
    digest = hashlib.sha256(b"other" if bad else b"release").hexdigest()
    if bad:
        with pytest.raises(FactoryError, match="checksum"):
            host.download("https://official.example/release", digest, path)
    else:
        host.download("https://official.example/release", digest, path)
        assert path.read_bytes() == b"release"


def test_download_unavailable_and_https_downgrade_fail_closed(host, monkeypatch, tmp_path):
    monkeypatch.setattr(host.urllib.request, "urlopen", Mock(side_effect=OSError("private transport detail")))
    with pytest.raises(FactoryError, match="download") as error:
        host.download("https://official.example/release", "0" * 64, tmp_path / "a")
    assert "private transport detail" not in str(error.value)

    class Response(io.BytesIO):
        def geturl(self):
            return "http://official.example/release"

    monkeypatch.setattr(host.urllib.request, "urlopen", lambda *a, **k: Response(b"release"))
    with pytest.raises(FactoryError, match="HTTPS"):
        host.download("https://official.example/release", "0" * 64, tmp_path / "b")


@pytest.mark.parametrize("name", ["../escape", "/absolute", "other/file"])
def test_archive_cannot_write_outside_expected_release(host, tmp_path, name):
    archive = tmp_path / "archive.tar"
    with tarfile.open(archive, "w") as stream:
        member = tarfile.TarInfo(name)
        member.size = 1
        stream.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(FactoryError, match="archive"):
        host.extract(archive, tmp_path / "out", "release")
    assert not (tmp_path / "escape").exists()


def test_archive_extracts_verified_release_without_overwriting(host, tmp_path):
    archive = tmp_path / "archive.tar"
    with tarfile.open(archive, "w") as stream:
        member = tarfile.TarInfo("release/file")
        member.size = 1
        stream.addfile(member, io.BytesIO(b"x"))
    host.extract(archive, tmp_path / "out", "release")
    assert (tmp_path / "out/release/file").read_bytes() == b"x"
    with pytest.raises(FactoryError, match="existing"):
        host.extract(archive, tmp_path / "out", "release")


def test_factory_commands_drop_administrator_environment(host, monkeypatch):
    monkeypatch.setattr(host.pwd, "getpwnam", lambda _: SimpleNamespace(pw_dir="/home/factory"))
    commands = Mock()
    host.as_factory(commands, ["node", "--version"], "node")
    args = commands.run.call_args.args[0]
    assert args[:6] == ["runuser", "-u", "factory", "--", "env", "-i"]
    assert "HOME=/home/factory" in args
    assert "NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt" in args
    assert "NPM_CONFIG_STRICT_SSL=true" in args
    assert "UV_NATIVE_TLS=true" in args
    assert args[-2:] == ["node", "--version"]


def test_apt_install_reuses_exact_packages_and_fails_without_fallback(host, tmp_path):
    commands = Mock()
    commands.run.return_value = "installed\t1.2"
    host.install_apt(commands, tmp_path, {"example": "1.2"}, "signed source")
    assert commands.run.call_count == 1
    commands.reset_mock()
    commands.run.side_effect = [FactoryError("not installed"), "", FactoryError("install failed")]
    with pytest.raises(FactoryError, match="install failed"):
        host.install_apt(commands, tmp_path, {"example": "1.2"}, "signed source")
    args = commands.run.call_args.args[0]
    assert "example=1.2" in args
    assert "--no-remove" in args
    assert "--allow-unauthenticated" not in args
    assert len(commands.run.call_args_list) == 3


def test_engine_readiness_requires_native_factory_access(host):
    commands = Mock()
    commands.run.return_value = json.dumps({"OSType": "linux", "Architecture": "aarch64"})
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(host.pwd, "getpwnam", lambda _: SimpleNamespace(pw_dir="/home/factory"))
        host.check_engine(commands)
        args = commands.run.call_args.args[0]
        assert args[-6:-2] == ["docker", "--host", "unix:///var/run/docker.sock", "info"]
        commands.run.return_value = json.dumps({"OSType": "linux", "Architecture": "x86_64"})
        with pytest.raises(FactoryError, match="native"):
            host.check_engine(commands)
        commands.run.side_effect = FactoryError("Docker unavailable")
        with pytest.raises(FactoryError, match="Docker unavailable"):
            host.check_engine(commands)


def test_node_signature_failure_prevents_extraction(host, monkeypatch, tmp_path):
    assert callable(getattr(host, "install_node", None)), "Node provisioning is missing"
    monkeypatch.setattr(host, "PREFIX", tmp_path / "tools")

    def fake_download(url, digest, path):
        path.write_text(f"{host.NODE_SHA}  node-v22.19.0-linux-arm64.tar.xz\n")

    monkeypatch.setattr(host, "download", fake_download)
    unpack = Mock()
    monkeypatch.setattr(host, "extract", unpack)
    commands = Mock()
    commands.run.side_effect = ["", FactoryError("bad signature")]
    with pytest.raises(FactoryError, match="bad signature"):
        host.install_node(commands, tmp_path)
    unpack.assert_not_called()


@pytest.mark.parametrize(
    "tool,dirname,executable,version",
    [
        ("install_python", "python-3.14.3", "python3", "Python 3.14.3"),
        ("install_node", "node-v22.19.0-linux-arm64", "node", "v22.19.0"),
        ("install_uv", "uv-0.5.13", "uv", "uv 0.5.13"),
    ],
)
def test_correct_release_reused_without_download_or_changes(
    host, monkeypatch, tmp_path, tool, dirname, executable, version
):
    assert callable(getattr(host, tool, None)), f"{tool} is missing"
    monkeypatch.setattr(host, "PREFIX", tmp_path)
    binary = tmp_path / dirname / "bin" / executable
    binary.parent.mkdir(parents=True)
    binary.write_text("sentinel")
    download = Mock(side_effect=AssertionError("Correct release should not be downloaded again"))
    monkeypatch.setattr(host, "download", download)
    commands = Mock()
    commands.run.return_value = version + "\n"
    getattr(host, tool)(commands, tmp_path)
    assert binary.read_text() == "sentinel"
    download.assert_not_called()
    commands.run.return_value = "wrong version\n"
    with pytest.raises(FactoryError, match="version"):
        getattr(host, tool)(commands, tmp_path)


@pytest.mark.parametrize("check_only", [False, True])
def test_entrypoint_orders_phases_and_reports_readiness_only_at_end(
    host, monkeypatch, tmp_path, capsys, caplog, check_only
):
    assert callable(getattr(host, "main", None)), "Host provisioning entrypoint is missing"
    events = []
    phases = [
        "validate_host",
        "validate_identity",
        "install_packages",
        "ensure_account",
        "install_python",
        "install_node",
        "install_uv",
        "install_pi",
        "check_readiness",
    ]
    for phase in phases:
        monkeypatch.setattr(host, phase, lambda *a, p=phase: events.append(p))
    monkeypatch.setattr(
        host.tempfile,
        "mkstemp",
        lambda **k: (host.os.open(tmp_path / "log", host.os.O_CREAT | host.os.O_WRONLY, 0o600), str(tmp_path / "log")),
    )
    assert host.main(["--check"] if check_only else []) == 0
    expected = ["validate_host", "validate_identity", "check_readiness"] if check_only else phases
    assert events == expected
    assert "ready" in capsys.readouterr().out.lower()
    events.clear()

    def fail(*args):
        raise FactoryError("failed step")

    monkeypatch.setattr(host, "check_readiness", fail)
    assert host.main(["--check"] if check_only else []) == 1
    output = capsys.readouterr()
    assert "ready" not in output.out.lower()
    assert "failed step" in caplog.text
    assert "partial" in caplog.text.lower()


def test_package_sources_are_isolated_signed_and_reused(host, monkeypatch, tmp_path):
    installs = []
    monkeypatch.setattr(host, "install_apt", lambda c, p, pins, sources: installs.append((pins, sources)))
    monkeypatch.setattr(host, "package_matches", lambda *a: False)
    downloads = []

    def fetch(url, digest, path):
        downloads.append((url, digest))
        path.write_text("public key")

    monkeypatch.setattr(host, "download", fetch)
    commands = Mock()
    commands.run.side_effect = lambda args, *a, **k: Path(args[args.index("--output") + 1]).write_text("keyring")
    host.install_packages(commands, tmp_path)
    assert installs[0][0] == host.UBUNTU_PACKAGES
    assert installs[1][0] == host.EXTERNAL_PACKAGES
    assert "signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg" in installs[0][1]
    assert "https://download.docker.com/linux/ubuntu noble stable" in installs[1][1]
    assert "https://cli.github.com/packages stable main" in installs[1][1]
    assert installs[1][1].count("signed-by=") == 5
    assert len(downloads) == 2 and all(len(digest) == 64 for _, digest in downloads)
    monkeypatch.setattr(host, "package_matches", lambda *a: True)
    installs.clear()
    host.install_packages(commands, tmp_path)
    assert len(installs) == 1
    assert len(downloads) == 2


@pytest.mark.parametrize("existing", [False, True])
def test_account_creation_never_repairs_or_grants_host_sudo(host, monkeypatch, existing):
    def group(name):
        if name == "factory" and not existing:
            raise KeyError(name)
        return SimpleNamespace(gr_gid=988 if name == "docker" else 2000)

    monkeypatch.setattr(host.grp, "getgrnam", group)

    def user(name):
        if not existing:
            raise KeyError(name)
        return SimpleNamespace(pw_dir="/home/factory")

    monkeypatch.setattr(host.pwd, "getpwnam", user)
    monkeypatch.setattr(host.os, "getgrouplist", lambda *a: [2000, 988] if existing else [2000])
    profile = Mock()
    monkeypatch.setattr(host, "write_once", profile)
    commands = Mock()
    host.ensure_account(commands)
    args = [call.args[0] for call in commands.run.call_args_list]
    assert [a[0] for a in args] == (["systemctl"] if existing else ["groupadd", "useradd", "usermod", "systemctl"])
    assert all(a[0] not in {"chown", "chmod", "sudo"} for a in args)
    content = profile.call_args.args[1].decode()
    assert 'if [ "$(id -u)" = 2000 ]' in content
    assert "NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt" in content
    assert "UV_NATIVE_TLS=true" in content
    assert "NOPASSWD" not in content


def test_python_build_is_separate_and_checked_before_execution(host, monkeypatch, tmp_path):
    monkeypatch.setattr(host, "PREFIX", tmp_path / "tools")
    download, unpack = Mock(), Mock()
    monkeypatch.setattr(host, "download", download)
    monkeypatch.setattr(host, "extract", unpack)
    commands = Mock()
    host.install_python(commands, tmp_path)
    assert download.call_args.args[1] == host.PYTHON_SHA
    assert unpack.call_args.args[2] == "Python-3.14.3"
    calls = commands.run.call_args_list
    assert calls[0].args[0] == ["./configure", f"--prefix={tmp_path}/tools/python-3.14.3", "--with-ensurepip=install"]
    assert calls[-1].args[0] == ["make", "install"]
    assert all(c.kwargs["cwd"] == tmp_path / "Python-3.14.3" for c in calls)


@pytest.mark.parametrize("manifest_matches", [True, False])
def test_node_install_requires_matching_signed_arm64_manifest(host, monkeypatch, tmp_path, manifest_matches):
    monkeypatch.setattr(host, "PREFIX", tmp_path / "tools")
    events = []

    def fetch(url, digest, path):
        events.append(url)
        path.write_text(f"{host.NODE_SHA if manifest_matches else '0' * 64}  node-v22.19.0-linux-arm64.tar.xz\n")

    monkeypatch.setattr(host, "download", fetch)
    unpack = Mock()
    monkeypatch.setattr(host, "extract", unpack)
    commands = Mock()
    commands.run.side_effect = lambda args, *a, **k: events.append(args[0])
    if manifest_matches:
        host.install_node(commands, tmp_path)
        assert events.index("gpgv") < events.index("https://nodejs.org/dist/v22.19.0/node-v22.19.0-linux-arm64.tar.xz")
        assert unpack.call_args.args[1:] == (tmp_path / "tools", "node-v22.19.0-linux-arm64")
    else:
        with pytest.raises(FactoryError, match="manifest"):
            host.install_node(commands, tmp_path)
        unpack.assert_not_called()


def test_uv_installs_only_verified_official_executables(host, monkeypatch, tmp_path):
    monkeypatch.setattr(host, "PREFIX", tmp_path / "tools")
    fetch = Mock()
    monkeypatch.setattr(host, "download", fetch)

    def unpack(archive, directory, top):
        (directory / top).mkdir()
        for name in ("uv", "uvx"):
            (directory / top / name).write_text(name)

    monkeypatch.setattr(host, "extract", unpack)
    host.install_uv(Mock(), tmp_path)
    assert fetch.call_args.args[1] == host.UV_SHA
    for name in ("uv", "uvx"):
        p = tmp_path / "tools/uv-0.5.13/bin" / name
        assert p.read_text() == name and p.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize("existing", [True, False])
def test_pi_install_is_user_scoped_private_and_not_repeated(host, monkeypatch, tmp_path, existing):
    monkeypatch.setattr(host.pwd, "getpwnam", lambda _: SimpleNamespace(pw_dir=str(tmp_path)))
    if existing:
        binary = tmp_path / ".local/bin/pi"
        binary.parent.mkdir(parents=True)
        binary.write_text("sentinel")
    fetch = Mock()
    monkeypatch.setattr(host, "download", fetch)
    factory = Mock(return_value="1.3.0")
    monkeypatch.setattr(host, "as_factory", factory)
    host.install_pi(Mock(), tmp_path)
    if existing:
        fetch.assert_not_called()
        assert binary.read_text() == "sentinel"
    else:
        assert fetch.call_args.args[1] == host.PI_SHA
        assert factory.call_args.args[1][:5] == ["npm", "install", "--global", "--no-audit", "--no-fund"]
        assert factory.call_args.kwargs["private"] is True


@pytest.mark.parametrize(
    "failure", [None, "newer-apt-patch", "uid", "gid", "tool", "missing-tool", "home", "sudo", "socket", "engine"]
)
def test_readiness_checks_fail_closed_without_live_authentication(host, monkeypatch, failure):
    packages = host.UBUNTU_PACKAGES | host.EXTERNAL_PACKAGES
    commands = Mock()
    commands.run.side_effect = lambda args, *a, **kw: (
        f"installed\t{packages[args[-1]]}{'.security' if failure == 'newer-apt-patch' else ''}"
    )
    socket = Mock(side_effect=FactoryError("socket unavailable") if failure == "socket" else None)
    monkeypatch.setattr(host, "check_socket", socket)
    engine = Mock(side_effect=FactoryError("Docker unavailable") if failure == "engine" else None)
    monkeypatch.setattr(host, "check_engine", engine)
    seen = []

    def factory(commands, args, phase, **kwargs):
        seen.append(args)
        if args[:1] == ["sudo"]:
            if failure == "sudo":
                return ""
            raise FactoryError("sudo denied")
        if args == ["id", "-u"]:
            return "0" if failure == "uid" else "2000"
        if args == ["id", "-g"]:
            return "0" if failure == "gid" else "2000"
        if phase == "check Python modules and factory home" and failure == "home":
            raise FactoryError("home is unusable")
        if phase == "check factory tools" and failure == "missing-tool":
            raise FactoryError("tool unavailable")
        if phase == "check tool version":
            return (
                "wrong"
                if failure == "tool"
                else {"python3": "Python 3.14.3", "node": "v22.19.0", "uv": "uv 0.5.13", "pi": "1.3.0"}[args[0]]
            )
        return ""

    monkeypatch.setattr(host, "as_factory", factory)
    if failure not in {None, "newer-apt-patch"}:
        with pytest.raises(FactoryError):
            host.check_readiness(commands)
        if failure == "engine":
            engine.assert_called_once()
        else:
            engine.assert_not_called()
    else:
        host.check_readiness(commands)
        socket.assert_called_once()
        engine.assert_called_once()
    assert all("auth" not in args for args in seen)


def test_socket_and_engine_malformed_state_is_actionable(host, monkeypatch):
    monkeypatch.setattr(host, "os", SimpleNamespace(stat=Mock(side_effect=FileNotFoundError())))
    with pytest.raises(FactoryError, match="socket"):
        host.check_socket()


@pytest.mark.parametrize("reply", ["not JSON", "null", "[]", '{"OSType":"linux","Architecture":[]}'])
def test_malformed_engine_reply_is_actionable(host, monkeypatch, reply):
    monkeypatch.setattr(host, "as_factory", Mock(return_value=reply))
    with pytest.raises(FactoryError, match="engine"):
        host.check_engine(Mock())


def test_archive_empty_component_fails_safely(host, tmp_path):
    archive = tmp_path / "empty-name.tar"
    with tarfile.open(archive, "w") as stream:
        stream.addfile(tarfile.TarInfo("."))
    with pytest.raises(FactoryError, match="archive"):
        host.extract(archive, tmp_path / "out", "release")


def test_release_symlink_is_not_executed_or_overwritten(host, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "release"
    link.symlink_to(real, target_is_directory=True)
    commands = Mock()
    with pytest.raises(FactoryError, match="symlink"):
        host.reuse_release(commands, link / "bin/tool", "tool 1.0")
    commands.run.assert_not_called()
    assert link.is_symlink()


def test_provisioning_budget_failure_is_not_an_issue_run_failure(host, monkeypatch, capsys, caplog):
    monkeypatch.setattr(host, "validate_host", Mock(side_effect=FactoryError("issue-run deadline expired")))
    assert host.main(["--check"]) == 1
    output = capsys.readouterr()
    assert "one-hour command budget" in caplog.text
    assert "issue-run" not in caplog.text
    assert not output.out


def test_safe_socket_is_accepted_without_permission_changes(host, monkeypatch):
    monkeypatch.setattr(host, "os", SimpleNamespace(stat=lambda _: SimpleNamespace(st_mode=stat.S_IFSOCK | 0o660)))
    host.check_socket()


def test_socket_must_not_be_world_writable(host, monkeypatch):
    monkeypatch.setattr(host, "os", SimpleNamespace(stat=lambda _: SimpleNamespace(st_mode=stat.S_IFSOCK | 0o666)))
    with pytest.raises(FactoryError, match="socket"):
        host.check_socket()
