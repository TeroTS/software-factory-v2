import json
import os
import runpy
import subprocess
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EC2 = ROOT / "infra/ec2"
SCRIPTS = EC2 / "scripts"


@cache
def template(kind: str = "FactoryStack") -> dict:
    module = "builder_stack.py" if kind == "BuilderStack" else "factory_stack.py"
    assert (EC2 / module).is_file(), "Python CDK stack is missing"
    from aws_cdk import App, Environment
    from aws_cdk.assertions import Template

    stack_type = runpy.run_path(str(EC2 / module))[kind]
    app = App()
    environment = Environment(account="172318459814", region="eu-central-1")
    shared_type = runpy.run_path(str(EC2 / "shared.py"))["SharedStack"]
    shared = shared_type(app, "software-factory-shared", env=environment)
    stack = stack_type(app, "software-factory", subnet=shared.subnet, env=environment)
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
    assert "Fn::ImportValue" in host["NetworkInterfaces"][0]["SubnetId"]
    assert host["MetadataOptions"] == {"HttpTokens": "required", "HttpPutResponseHopLimit": 1}
    assert "KeyName" not in host
    assert host["NetworkInterfaces"][0]["AssociatePublicIpAddress"] is True
    assert resources["SecurityGroup"]["Properties"]["SecurityGroupIngress"] == []
    assert resources["HostRole"]["Properties"]["ManagedPolicyArns"] == [
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    ]
    assert "Fn::ImportValue" in resources["SecurityGroup"]["Properties"]["VpcId"]
    assert config["Parameters"]["FactoryAmi"]["Type"] == "AWS::EC2::Image::Id"
    assert host["ImageId"] == {"Ref": "FactoryAmi"}
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
    assert "Fn::ImportValue" in data["Properties"]["AvailabilityZone"]
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
    assert "/usr/local/sbin/factory-prepare-host" in script
    assert "/etc/software-factory/volume-id" in script
    assert "apt-get" not in script and "curl" not in script
    assert "cat > /usr/local/sbin" not in script
    assert "vol-test" not in (SCRIPTS / "factory/check-host.sh").read_text()
    assert "systemctl start software-factory" not in script
    assert "systemctl enable software-factory" not in script
    assert "factory-bake-host" not in script
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
    branch = f"\nsource {SCRIPTS / 'shared/prepare-storage.sh'}\nprepare_storage vol-test\n"
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
    function = (SCRIPTS / "shared/prepare-storage.sh").read_text()
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


def test_builder_installs_exact_repository_files_before_baking(tmp_path: Path) -> None:
    build = runpy.run_path(str(EC2 / "builder_stack.py"))["builder_user_data"]
    script = build(EC2)
    assert len(script.encode()) < 16384
    import base64
    import gzip

    encoded = script.split("'")[3]
    script = gzip.decompress(base64.b64decode(encoded)).decode()
    invocation = "/usr/local/sbin/factory-bake-host\n"
    assert script.endswith(invocation)
    script = (
        script.removesuffix(invocation)
        .replace("/usr/local/sbin", str(tmp_path))
        .replace("/etc/systemd/system", str(tmp_path))
    )
    subprocess.run(["bash", "-c", script], check=True, capture_output=True, timeout=10)
    for source, installed in (
        ("shared/prepare-storage.sh", "prepare-storage"),
        ("factory/prepare-host.sh", "prepare-host"),
        ("factory/check-host.sh", "host-check"),
        ("factory/start-runner.sh", "start-runner"),
        ("factory/stop-runner.sh", "stop-runner"),
        ("builder/bake-host.sh", "bake-host"),
        ("builder/finalize-image.sh", "finalize-image"),
    ):
        path = tmp_path / f"factory-{installed}"
        expected = (SCRIPTS / source).read_text()
        # Only the test destination prefix differs from the real embedded files.
        assert path.read_text() == expected.replace("/usr/local/sbin", str(tmp_path)).replace(
            "/etc/systemd/system", str(tmp_path)
        )
        assert path.stat().st_mode & 0o777 == 0o755
    unit = tmp_path / "software-factory.service"
    assert unit.read_text() == (EC2 / "software-factory.service").read_text().replace("/usr/local/sbin", str(tmp_path))
    assert unit.stat().st_mode & 0o777 == 0o644
    assert "@DATA_VOLUME_ID@" not in script
    assert not (EC2 / "factory.yaml").exists(), "Keep one authoritative deployment path"


def test_synthesis_rejects_oversized_userdata(tmp_path: Path) -> None:
    import random
    import string

    content = "".join(random.Random(42).choices(string.ascii_letters + string.digits, k=30000))
    scripts = tmp_path / "scripts"
    for source in (
        "shared/prepare-storage.sh",
        "factory/prepare-host.sh",
        "factory/check-host.sh",
        "factory/start-runner.sh",
        "factory/stop-runner.sh",
        "builder/bake-host.sh",
        "builder/finalize-image.sh",
    ):
        path = scripts / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n")
    (tmp_path / "software-factory.service").write_text("[Service]\n")
    build = runpy.run_path(str(EC2 / "builder_stack.py"))["builder_user_data"]
    with pytest.raises(ValueError, match="16384-byte"):
        build(tmp_path)


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
    builder = manifest["artifacts"]["software-factory-ami-builder"]
    assert builder["environment"] == artifact["environment"]
    assert not builder["properties"].get("requiresBootstrapStackVersion")
    assert "software-factory-ami-builder" not in artifact.get("dependencies", [])
    assert "software-factory" not in builder.get("dependencies", [])
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


def test_shared_network_outlives_consumers_without_coupling_builder_to_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT))
    module = runpy.run_module("infra.ec2.app", run_name="__main__")
    assembly = Path(module["app"].outdir)
    artifacts = json.loads((assembly / "manifest.json").read_text())["artifacts"]
    assert "software-factory-shared" in artifacts, "Persistent shared-network stack is missing"
    shared = json.loads((assembly / "software-factory-shared.template.json").read_text())
    assert not artifacts["software-factory-shared"].get("dependencies")
    assert artifacts["software-factory-shared"]["environment"] == "aws://172318459814/eu-central-1"
    types = [resource["Type"] for resource in shared["Resources"].values()]
    for kind in (
        "VPC",
        "Subnet",
        "InternetGateway",
        "VPCGatewayAttachment",
        "RouteTable",
        "Route",
        "SubnetRouteTableAssociation",
    ):
        assert types.count(f"AWS::EC2::{kind}") == 1
    assert set(types) <= {
        "AWS::EC2::VPC",
        "AWS::EC2::Subnet",
        "AWS::EC2::InternetGateway",
        "AWS::EC2::VPCGatewayAttachment",
        "AWS::EC2::RouteTable",
        "AWS::EC2::Route",
        "AWS::EC2::SubnetRouteTableAssociation",
        "AWS::CDK::Metadata",
    }
    configs = {}
    for name in ("software-factory-ami-builder", "software-factory"):
        assert "software-factory-shared" in artifacts[name]["dependencies"]
        config = json.loads((assembly / f"{name}.template.json").read_text())
        assert not any(
            resource["Type"] in set(types) - {"AWS::CDK::Metadata"} for resource in config["Resources"].values()
        )
        configs[name] = config["Resources"]
    builder, factory = configs["software-factory-ami-builder"], configs["software-factory"]
    builder_subnet = builder["Builder"]["Properties"]["NetworkInterfaces"][0]["SubnetId"]
    assert "Fn::ImportValue" in builder_subnet
    assert factory["Host"]["Properties"]["NetworkInterfaces"][0]["SubnetId"] == builder_subnet
    assert builder["SecurityGroup"]["Properties"]["VpcId"] == factory["SecurityGroup"]["Properties"]["VpcId"]
    assert shared["Resources"]["Subnet"]["Properties"]["VpcId"] == {"Ref": "Vpc"}
    assert shared["Resources"]["DefaultRoute"]["Properties"]["DestinationCidrBlock"] == "0.0.0.0/0"
    assert "GatewayAttachment" in shared["Resources"]["DefaultRoute"]["DependsOn"]
    zone_export = factory["DataVolume"]["Properties"]["AvailabilityZone"]["Fn::ImportValue"]
    assert any(
        output.get("Export", {}).get("Name") == zone_export
        and output["Value"] == {"Fn::GetAtt": ["Subnet", "AvailabilityZone"]}
        for output in shared["Outputs"].values()
    )
    assert "software-factory-ami-builder" not in artifacts["software-factory"]["dependencies"]
    assert "software-factory" not in artifacts["software-factory-ami-builder"]["dependencies"]


def test_builder_is_disposable_independent_and_has_no_ami_deletion_lifecycle() -> None:
    config = template("BuilderStack")
    resources = config["Resources"]
    host = resources["Builder"]["Properties"]
    assert host["ImageId"] == {"Ref": "UbuntuAmi"}
    assert host["MetadataOptions"]["HttpTokens"] == "required"
    assert host["BlockDeviceMappings"][0]["Ebs"] == {
        "VolumeSize": 30,
        "VolumeType": "gp3",
        "Encrypted": True,
        "DeleteOnTermination": True,
    }
    assert resources["SecurityGroup"]["Properties"]["SecurityGroupIngress"] == []
    assert resources["BuilderRole"]["Properties"]["ManagedPolicyArns"] == [
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    ]
    assert "Policies" not in resources["BuilderRole"]["Properties"]
    assert {resource["Type"] for resource in resources.values()}.isdisjoint(
        {
            "AWS::EC2::Volume",
            "AWS::EC2::VolumeAttachment",
            "AWS::ECR::Repository",
            "AWS::Lambda::Function",
            "AWS::CloudFormation::CustomResource",
        }
    )
    assert "Fn::ImportValue" in json.dumps(config)
    assert "SourceRevision" in config["Parameters"]
    assert "BuilderInstanceId" in config["Outputs"]
    assert "create-image" not in json.dumps(config)
