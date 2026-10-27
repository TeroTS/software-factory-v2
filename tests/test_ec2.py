import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra/ec2/factory.yaml"


def template() -> dict:
    assert TEMPLATE.is_file(), "Repository-managed EC2 template is missing"
    # JSON-form YAML permits structural checks with the standard library.
    return json.loads(TEMPLATE.read_text())


def bootstrap_script() -> str:
    separator, lines = template()["Resources"]["Host"]["Properties"]["UserData"]["Fn::Base64"]["Fn::Join"]
    return separator.join(line if isinstance(line, str) else line["Fn::Sub"] for line in lines)


def test_ec2_host_has_native_platform_session_manager_and_no_inbound_access() -> None:
    config = template()
    resources = config["Resources"]
    host = resources["Host"]["Properties"]
    assert host["InstanceType"] == "t4g.xlarge"
    assert host["MetadataOptions"] == {"HttpTokens": "required", "HttpPutResponseHopLimit": 1}
    assert "KeyName" not in host
    assert host["NetworkInterfaces"][0]["AssociatePublicIpAddress"] is True
    assert resources["SecurityGroup"]["Properties"]["SecurityGroupIngress"] == []
    assert resources["HostRole"]["Properties"]["ManagedPolicyArns"] == [
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    ]
    assert resources["Subnet"]["Properties"]["VpcId"] == {"Ref": "Vpc"}
    assert resources["DefaultRoute"]["Properties"]["DestinationCidrBlock"] == "0.0.0.0/0"
    assert config["Parameters"]["UbuntuAmi"]["Type"] == "AWS::EC2::Image::Id"
    assert host["ImageId"] == {"Ref": "UbuntuAmi"}
    assert host["BlockDeviceMappings"][0]["Ebs"]["Encrypted"] is True
    assert host["BlockDeviceMappings"][0]["Ebs"]["DeleteOnTermination"] is True


def test_ec2_retains_encrypted_data_on_replacement_and_deletion() -> None:
    resources = template()["Resources"]
    data = resources["DataVolume"]
    assert data["DeletionPolicy"] == "Retain"
    assert data["UpdateReplacePolicy"] == "Retain"
    assert data["Properties"]["Encrypted"] is True
    assert data["Properties"]["Size"] == 100
    assert data["Properties"]["VolumeType"] == "gp3"
    assert data["Properties"]["AvailabilityZone"] == resources["Subnet"]["Properties"]["AvailabilityZone"]
    attachment = resources["DataAttachment"]["Properties"]
    assert attachment["VolumeId"] == {"Ref": "DataVolume"}
    assert attachment["InstanceId"] == {"Ref": "Host"}


def test_ec2_bootstrap_preserves_existing_data_and_keeps_execution_stopped(tmp_path: Path) -> None:
    script = bootstrap_script()
    path = tmp_path / "bootstrap.sh"
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True, timeout=10)
    assert "set -euo pipefail" in script
    assert "${DataVolume}" in script
    assert "wipefs --no-act --json" in script
    assert script.index("wipefs --no-act --json") < script.index("mkfs.ext4")
    assert "refusing" in script
    assert "mountpoint -q /srv/software-factory" in script
    assert "home:/home/factory docker:/var/lib/docker containerd:/var/lib/containerd" in script
    assert "RequiresMountsFor=/srv/software-factory /var/lib/docker /var/lib/containerd" in script
    assert "software_factory" not in script
    assert "git clone" not in script
    assert "chmod -R" not in script
    assert "chown -R" not in script


@pytest.mark.parametrize(
    ("filesystem", "signatures", "device_type", "succeeds", "formatted"),
    [
        ("ext4", [], "disk", True, False),
        ("xfs", [], "disk", False, False),
        ("", [{"type": "LVM2_member"}], "disk", False, False),
        ("", [], "disk\npart", False, False),
        ("", [], "disk", True, True),
    ],
)
def test_bootstrap_formats_only_a_blank_unpartitioned_disk(
    tmp_path: Path, filesystem: str, signatures: list, device_type: str, succeeds: bool, formatted: bool
) -> None:
    script = bootstrap_script()
    branch = script[script.index('if [ -z "$filesystem" ]; then') : script.index("# Persist")]
    marker = tmp_path / "formatted"
    # Replace only privileged tool boundaries; execute the actual disk-safety branch.
    harness = """set -euo pipefail
filesystem=$FILESYSTEM
device=/dev/test-only
lsblk() { if [ "$3" = TYPE ]; then printf '%s\\n' "$DEVICE_TYPE"; fi; }
wipefs() { printf '%s\\n' "$SIGNATURES"; }
mkfs.ext4() { touch "$MARKER"; }
"""
    result = subprocess.run(
        ["bash", "-c", harness + branch],
        env={
            **os.environ,
            "FILESYSTEM": filesystem,
            "SIGNATURES": json.dumps({"signatures": signatures}),
            "DEVICE_TYPE": device_type,
            "MARKER": str(marker),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) is succeeds, result.stderr
    assert marker.exists() is formatted


def test_bootstrap_fstab_is_idempotent_and_rejects_conflicting_entries(tmp_path: Path) -> None:
    script = bootstrap_script()
    function = script[script.index("persist_mount() {") : script.index("uuid=$(blkid")]
    fstab = tmp_path / "fstab"
    fstab.write_text("# existing root configuration\n")
    function = function.replace("/etc/fstab", str(fstab))
    entry = "UUID=expected /srv/software-factory ext4 defaults 0 2"
    for _ in range(2):
        subprocess.run(["bash", "-euc", function + "persist_mount " + entry], check=True, timeout=10)
    original = fstab.read_text()
    assert original == "# existing root configuration\n" + entry + "\n"
    result = subprocess.run(
        ["bash", "-euc", function + "persist_mount UUID=wrong /srv/software-factory ext4 defaults 0 2"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "refusing conflicting fstab entry" in result.stderr
    assert fstab.read_text() == original
