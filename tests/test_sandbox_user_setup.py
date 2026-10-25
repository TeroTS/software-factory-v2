import os
import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest

import software_factory.sandbox as sandbox

SCRIPT = Path(sandbox.__file__).with_name("sandbox_user_setup.py")


@pytest.fixture
def account_files(tmp_path, monkeypatch):
    (tmp_path / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\n")
    (tmp_path / "shadow").write_text("root:!:1:0:99999:7:::\n")
    (tmp_path / "group").write_text("root:x:0:\n")
    socket = Mock()
    socket.exists.return_value = True
    socket.stat.return_value.st_gid = 456
    chown = Mock()
    paths = {
        "/tmp/factory-home": tmp_path / "home",
        "/etc/passwd": tmp_path / "passwd",
        "/etc/shadow": tmp_path / "shadow",
        "/etc/group": tmp_path / "group",
        "/var/run/docker.sock": socket,
    }

    def run(uid=123, gid=234):
        assert SCRIPT.is_file(), "user setup must be a standalone Python script"
        with monkeypatch.context() as patch:
            # Only these container paths are allowed; never fall through to host account files.
            patch.setattr("pathlib.Path", lambda path: paths[path])
            patch.setattr(os, "chown", chown)
            patch.setattr("sys.argv", [str(SCRIPT), str(uid), str(gid)])
            patch.setattr("time.time", lambda: 172800)
            runpy.run_path(str(SCRIPT), run_name="__main__")

    return tmp_path, run, chown, socket


def test_new_account_home_shadow_and_socket_groups(account_files) -> None:
    root, run, chown, _ = account_files
    run()
    users = (root / "passwd").read_text().splitlines()
    assert users[0] == "root:x:0:0:root:/root:/bin/bash"
    user = users[1].split(":")
    assert user[1:] == ["x", "123", "234", "", str(root / "home"), "/bin/sh"]
    assert user[0].startswith("f")
    assert (root / "home").stat().st_mode & 0o777 == 0o700
    chown.assert_called_once_with(root / "home", 123, 234)
    assert (root / "shadow").read_text() == f"root:!:1:0:99999:7:::\n{user[0]}:!:2:0:99999:7:::\n"
    groups = [line.split(":") for line in (root / "group").read_text().splitlines()]
    assert groups[0] == ["root", "x", "0", ""]
    assert {entry[2] for entry in groups[1:]} == {"234", "456"}
    assert all(entry[3] == user[0] for entry in groups[1:])


@pytest.mark.parametrize("has_shadow", [False, True])
@pytest.mark.parametrize("socket_gid", [234, 456])
def test_existing_account_and_groups_preserve_unrelated_records(account_files, has_shadow, socket_gid) -> None:
    root, run, chown, socket = account_files
    (root / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\nexisting:x:123:999:Name:/old:/bin/bash\n")
    shadow = "root:!:1:0:99999:7:::\n"
    if has_shadow:
        shadow += "existing:locked:1:2:3:4:5:6:7\n"
    (root / "shadow").write_text(shadow)
    (root / "group").write_text("root:x:0:\nprimary:x:234:other,existing\ndocker:x:456:service\n")
    socket.stat.return_value.st_gid = socket_gid
    run()
    assert (root / "passwd").read_text() == (
        f"root:x:0:0:root:/root:/bin/bash\nexisting:x:123:234:Name:{root / 'home'}:/bin/bash\n"
    )
    chown.assert_called_once_with(root / "home", 123, 234)
    assert (root / "shadow").read_text() == shadow + ("" if has_shadow else "existing:!:2:0:99999:7:::\n")
    members = "existing,service" if socket_gid == 456 else "service"
    assert (root / "group").read_text() == (f"root:x:0:\nprimary:x:234:existing,other\ndocker:x:456:{members}\n")


def test_missing_socket_only_configures_primary_group(account_files) -> None:
    root, run, _, socket = account_files
    socket.exists.return_value = False
    run()
    socket.stat.assert_not_called()
    groups = (root / "group").read_text().splitlines()
    assert len(groups) == 2
    assert groups[1].split(":")[2] == "234"


def test_baked_home_contents_are_preserved(account_files) -> None:
    root, run, _, _ = account_files
    (root / "home" / ".cache").mkdir(parents=True)
    (root / "home" / ".cache" / "sentinel").write_text("baked content")
    run(uid=2000, gid=2000)
    assert (root / "home" / ".cache" / "sentinel").read_text() == "baked content"


@pytest.mark.parametrize("failure", ["home", "ownership", "passwd", "shadow", "group"])
def test_filesystem_failures_propagate_without_retry(account_files, failure) -> None:
    root, run, chown, _ = account_files
    if failure == "home":
        (root / "home").write_text("not a directory")
    elif failure == "ownership":
        chown.side_effect = PermissionError("ownership denied")
    else:
        (root / failure).unlink()
    with pytest.raises(OSError):
        run()
    assert chown.call_count <= 1
