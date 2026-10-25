import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_lima_configuration_limits_resources_sharing_and_networking() -> None:
    limactl = shutil.which("limactl")
    if limactl is None:
        pytest.skip("Lima configuration validation requires operator-installed limactl")
    template = ROOT / "infra/lima/factory.yaml"
    assert template.is_file(), "Repository-maintained factory VM configuration is missing"
    result = subprocess.run(
        [limactl, "template", "yq", str(template), "@json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    config = json.loads(result.stdout)
    assert config["cpus"] == 4
    assert config["memory"] == "8GiB"
    assert config["disk"] == "40GiB"
    assert config["vmType"] == "vz"
    assert config["arch"] == "aarch64"
    assert config.get("mounts", []) == []
    assert config.get("base", []) == []
    assert config["containerd"]["system"] is False
    assert config["containerd"]["user"] is False
    assert config["vmOpts"]["vz"]["rosetta"]["enabled"] is False
    assert config["ssh"]["forwardAgent"] is False
    assert config["ssh"]["loadDotSSHPubKeys"] is False
    assert config["upgradePackages"] is False
    assert config["user"]["name"] != "factory"
    assert len(config["images"]) == 1
    image = config["images"][0]
    assert image["arch"] == "aarch64"
    assert image["location"] == (
        "https://cloud-images.ubuntu.com/releases/noble/release-20260926/ubuntu-24.04-server-cloudimg-arm64.img"
    )
    assert image["digest"] == "sha256:1d6bffe64b848468ac97f821d369a4846d983de1800ccf6b5ec8853e85cefc55"
    forward, deny = config["portForwards"]
    assert forward["guestPortRange"] == [8080, 8080]
    assert forward["hostPortRange"] == [8080, 8080]
    assert forward["hostIP"] == "127.0.0.1"
    assert forward["proto"] == "tcp"
    assert not forward.get("ignore", False)
    assert deny["guestIP"] == "0.0.0.0"
    assert deny["guestIPMustBeZero"] is False
    assert deny["guestPortRange"] == [1, 65535]
    assert deny["proto"] == "any"
    assert deny["ignore"] is True
