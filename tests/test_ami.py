import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "infra/ec2/scripts/builder"


@pytest.mark.parametrize("failure", ["", "account", "packages", "versions"])
def test_bake_masks_engines_before_package_install_and_records_provenance(tmp_path: Path, failure: str) -> None:
    path = SCRIPTS / "bake-host.sh"
    assert path.is_file(), "AMI bake script is missing"
    code = path.read_text().replace("/etc/software-factory", str(tmp_path / "settings"))
    code = code.replace("/run/factory-ami-builder", str(tmp_path / "builder"))
    code = code.replace("/usr/sbin/policy-rc.d", str(tmp_path / "policy-rc.d"))
    code = code.replace("source /usr/local/sbin/factory-prepare-storage", ":")
    code = code.replace("/usr/local/sbin/factory-bake-host", str(tmp_path / "bake-host"))
    boundaries = """
validate_host() { echo validate; }
ensure_account() { echo account; test "$FAILURE" != account; }
install_storage_guards() { echo guards; }
systemctl() { echo "systemctl $*"; }
install_docker() {
  test -x "$TEST_ROOT/policy-rc.d"
  test "$("$TEST_ROOT/policy-rc.d"; echo $?)" = 101
  echo packages
  test "$FAILURE" != packages
}
systemd-analyze() { echo verify; }
dpkg-query() { echo installed-package-versions; test "$FAILURE" != versions; }
aws() { echo aws-cli/fixture; }
"""
    result = subprocess.run(
        ["bash", "-c", code + boundaries + "bake_host"],
        env={
            **os.environ,
            "TEST_ROOT": str(tmp_path),
            "FACTORY_PARENT_AMI": "ami-parent",
            "FACTORY_SOURCE_REVISION": "a" * 40,
            "FAILURE": failure,
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) is (not failure), result.stderr
    assert not (tmp_path / "policy-rc.d").exists()
    if failure:
        assert not (tmp_path / "builder").exists()
        assert "AMI bake complete" not in result.stdout
        return
    lines = result.stdout.splitlines()
    assert lines.index("systemctl mask docker.service docker.socket containerd.service") < lines.index("packages")
    assert lines.index("guards") < lines.index("packages")
    assert "systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service" in lines
    assert not (tmp_path / "policy-rc.d").exists()
    assert (tmp_path / "builder").exists()
    record = (tmp_path / "settings/image-info").read_text()
    assert "ami-parent" in record and "a" * 40 in record
    assert "installed-package-versions" in record and "aws-cli/fixture" in record
    assert "enable --now docker" not in result.stdout


@pytest.mark.parametrize(
    "failure", ["", "not-builder", "mounted", "private-data", "root-credentials", "clean", "stop-ssm"]
)
def test_finalize_is_builder_only_and_cleans_identity_before_poweroff(tmp_path: Path, failure: str) -> None:
    path = SCRIPTS / "finalize-image.sh"
    assert path.is_file(), "AMI finalization script is missing"
    code = path.read_text()
    for original, replacement in {
        "/run/factory-ami-builder": tmp_path / "builder",
        "/srv/software-factory": tmp_path / "data",
        "/etc/software-factory": tmp_path / "settings",
        "/home/factory": tmp_path / "home",
        "/root/.aws": tmp_path / "root-aws",
        "/root/.docker": tmp_path / "root-docker",
        "/root/.pi": tmp_path / "root-pi",
        "/var/lib/docker": tmp_path / "docker",
        "/var/lib/containerd": tmp_path / "containerd",
        "/var/lib/amazon/ssm": tmp_path / "ssm",
        "/var/snap/amazon-ssm-agent/common": tmp_path / "ssm-snap",
        "/var/log/amazon/ssm": tmp_path / "ssm-log",
        "/etc/ssh": tmp_path / "ssh",
    }.items():
        code = code.replace(original, str(replacement))
    (tmp_path / "settings").mkdir()
    (tmp_path / "builder").write_text("builder")
    if failure == "not-builder":
        (tmp_path / "builder").unlink()
    (tmp_path / "home").mkdir()
    if failure == "private-data":
        (tmp_path / "home/private").write_text("preserve")
    if failure == "root-credentials":
        (tmp_path / "root-aws").mkdir()
        (tmp_path / "root-aws/credentials").write_text("preserve-secret")
    for name in ("ssm", "ssm-snap", "ssm-log", "ssh"):
        (tmp_path / name).mkdir()
        (tmp_path / name / ("ssh_host_test_key" if name == "ssh" else "state")).write_text("builder identity")
    boundaries = """
id() { echo 0; }
mountpoint() { test "$FAILURE" = mounted; }
systemctl() { echo "systemctl $*"; test "$FAILURE" != stop-ssm; }
cloud-init() { echo "cloud-init $*"; test "$FAILURE" != clean; }
"""
    result = subprocess.run(
        ["bash", "-c", boundaries + code],
        env={**os.environ, "FAILURE": failure},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) is (not failure), result.stderr
    if not failure:
        assert "cloud-init clean --logs --machine-id --seed" in result.stdout
        assert result.stdout.index("cloud-init clean") < result.stdout.index("systemctl poweroff")
        assert not (tmp_path / "ssm/state").exists()
        assert not (tmp_path / "ssm-snap/state").exists()
        assert not (tmp_path / "ssm-log/state").exists()
        assert not (tmp_path / "ssh/ssh_host_test_key").exists()
        assert (tmp_path / "settings/capture-ready").exists()
    else:
        assert "poweroff" not in result.stdout
        assert (tmp_path / "ssm/state").read_text() == "builder identity"
        assert not (tmp_path / "settings/capture-ready").exists()
        if failure == "root-credentials":
            assert (tmp_path / "root-aws/credentials").read_text() == "preserve-secret"
