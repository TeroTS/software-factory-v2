import json
import os
import runpy
import subprocess
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "infra/ec2"


@cache
def template() -> dict:
    assert (SCRIPTS / "stack.py").is_file(), "Python CDK stack is missing"
    from aws_cdk import App, Environment
    from aws_cdk.assertions import Template

    stack_type = runpy.run_path(str(SCRIPTS / "stack.py"))["FactoryStack"]
    app = App()
    stack = stack_type(app, "software-factory", env=Environment(account="172318459814", region="eu-central-1"))
    return Template.from_stack(stack).to_json()


def bootstrap_script() -> str:
    userdata = template()["Resources"]["Host"]["Properties"]["UserData"]["Fn::Base64"]
    separator, parts = userdata["Fn::Join"]
    return separator.join(part if isinstance(part, str) else "vol-test" for part in parts)


def test_ec2_host_has_native_platform_session_manager_and_no_inbound_access() -> None:
    config = template()
    resources = config["Resources"]
    host = resources["Host"]["Properties"]
    assert host["InstanceType"] == "t4g.xlarge"
    assert "AvailabilityZone" not in host
    assert host["NetworkInterfaces"][0]["SubnetId"] == {"Ref": "Subnet"}
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


def test_ec2_ecr_repositories_and_scoped_pull_only_host_access() -> None:
    resources = template()["Resources"]
    for name in ("RunnerRepository", "AgentRepository"):
        repository = resources[name]
        assert repository["Type"] == "AWS::ECR::Repository"
        assert repository["DeletionPolicy"] == "Retain"
        assert "LifecyclePolicy" not in repository["Properties"]
        assert repository["Properties"]["EncryptionConfiguration"]["EncryptionType"] == "AES256"
    statements = resources["HostRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    assert statements[0]["Action"] == ["ecr:GetAuthorizationToken"]
    assert statements[1]["Resource"] == [
        {"Fn::GetAtt": ["RunnerRepository", "Arn"]},
        {"Fn::GetAtt": ["AgentRepository", "Arn"]},
    ]
    assert set(statements[1]["Action"]) == {
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
    }


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
    assert "vol-test" in script
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
    branch = f"\nsource {SCRIPTS / 'prepare-storage.sh'}\nprepare_storage vol-test\n"
    marker = tmp_path / "formatted"
    # Replace only privileged tool boundaries; execute the actual disk-safety branch.
    harness = """set -euo pipefail
test() { if [ "$1" = -b ]; then return 0; else builtin test "$@"; fi; }
function [ {
  if builtin [ "$#" = 4 ] && builtin [ "$1" = '!' ] && builtin [ "$2" = -b ]; then return 1
  else builtin [ "$@"; fi
}
lsblk() {
  case "$3" in
    SERIAL) echo voltest;;
    FSTYPE) printf '%s\\n' "$FILESYSTEM";;
    TYPE) printf '%s\\n' "$DEVICE_TYPE";;
  esac
}
blkid() { echo FILESYSTEM_SAFE >&2; return 1; }
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
    assert ("FILESYSTEM_SAFE" in result.stderr) is succeeds, result.stderr
    assert marker.exists() is formatted


def test_bootstrap_fstab_is_idempotent_and_rejects_conflicting_entries(tmp_path: Path) -> None:
    function = (SCRIPTS / "prepare-storage.sh").read_text()
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


def test_userdata_installs_exact_repository_files_before_invocation(tmp_path: Path) -> None:
    script = bootstrap_script()
    invocation = "/usr/local/sbin/factory-prepare-host 'vol-test'\n"
    assert script.endswith(invocation)
    script = script.removesuffix(invocation).replace("/usr/local/sbin", str(tmp_path))
    subprocess.run(["bash", "-c", script], check=True, capture_output=True, timeout=10)
    for name, installed in (
        ("prepare-storage", "prepare-storage"),
        ("prepare-host", "prepare-host"),
        ("check-host", "host-check"),
    ):
        path = tmp_path / f"factory-{installed}"
        expected = (SCRIPTS / f"{name}.sh").read_text().replace("@DATA_VOLUME_ID@", "vol-test")
        # Only the test destination prefix differs from the real embedded files.
        assert path.read_text() == expected.replace("/usr/local/sbin", str(tmp_path))
        assert path.stat().st_mode & 0o777 == 0o755
    assert "@DATA_VOLUME_ID@" not in script
    assert not (SCRIPTS / "factory.yaml").exists(), "Keep one authoritative deployment path"


def test_synthesis_rejects_oversized_userdata(tmp_path: Path) -> None:
    for name in ("prepare-storage", "prepare-host", "check-host"):
        (tmp_path / f"{name}.sh").write_text("#" * 6000 + "\n")
    build = runpy.run_path(str(SCRIPTS / "stack.py"))["user_data"]
    with pytest.raises(ValueError, match="16384-byte"):
        build("vol-test", tmp_path)


def test_cdk_app_synthesizes_fixed_account_region_without_bootstrap_or_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT))
    module = runpy.run_module("infra.ec2.app", run_name="__main__")
    assembly = Path(module["app"].outdir)
    manifest = json.loads((assembly / "manifest.json").read_text())
    artifact = manifest["artifacts"]["software-factory"]
    assert artifact["environment"] == "aws://172318459814/eu-central-1"
    assert not artifact["properties"].get("requiresBootstrapStackVersion")
    config = json.loads((assembly / "software-factory.template.json").read_text())
    assert config["Resources"]["Host"]["Properties"]["InstanceType"] == "t4g.xlarge"
    assert {output for output in config["Outputs"]} >= {
        "InstanceId",
        "DataVolumeId",
        "RunnerRepositoryUri",
        "AgentRepositoryUri",
    }
    assert {resource["Type"] for resource in config["Resources"].values()}.isdisjoint(
        {
            "AWS::EC2::NatGateway",
            "AWS::Lambda::Function",
            "AWS::CloudFormation::CustomResource",
        }
    )
