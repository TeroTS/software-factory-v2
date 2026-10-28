# Define disposable AMI-builder infrastructure and embed host files; leave image capture and selection manual.
import base64
import gzip
from pathlib import Path

from aws_cdk import BootstraplessSynthesizer, CfnOutput, CfnParameter, CfnTag, Fn, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from constructs import Construct


# Embed exact repository host files, compressed deterministically to fit EC2's UserData limit; never fetch source.
def builder_user_data(directory: Path) -> str:
    script = "set -euo pipefail\numask 077\n"
    for source in (
        "shared/prepare-storage.sh",
        "factory/prepare-host.sh",
        "factory/check-host.sh",
        "factory/start-runner.sh",
        "factory/stop-runner.sh",
        "builder/bake-host.sh",
        "builder/finalize-image.sh",
    ):
        path = directory / "scripts" / source
        content = path.read_text()
        destination = "/usr/local/sbin/factory-" + ("host-check" if path.stem == "check-host" else path.stem)
        script += f"cat > {destination} <<'FACTORY_SCRIPT'\n{content}FACTORY_SCRIPT\nchmod 0755 {destination}\n"
    unit = (directory / "software-factory.service").read_text()
    script += (
        "cat > /etc/systemd/system/software-factory.service <<'FACTORY_UNIT'\n"
        + unit
        + "FACTORY_UNIT\nchmod 0644 /etc/systemd/system/software-factory.service\n"
        "/usr/local/sbin/factory-bake-host\n"
    )
    encoded = base64.b64encode(gzip.compress(script.encode(), mtime=0)).decode()
    result = f"printf '%s' '{encoded}' | base64 --decode | gzip --decompress | bash\n"
    if len(result.encode()) + 512 > 16384:
        raise ValueError("EC2 UserData exceeds the 16384-byte limit")
    return result


# Own only disposable builder infrastructure; operator-created AMIs/snapshots are deliberately outside this stack.
class BuilderStack(Stack):
    # Bake a verified Canonical parent in the shared subnet; omit private data and ECR/capture access.
    def __init__(self, scope: Construct, construct_id: str, *, subnet: ec2.CfnSubnet, **kwargs: object) -> None:
        super().__init__(scope, construct_id, synthesizer=BootstraplessSynthesizer(), **kwargs)
        ami = CfnParameter(self, "UbuntuAmi", type="AWS::EC2::Image::Id")
        revision = CfnParameter(self, "SourceRevision", type="String", allowed_pattern="[a-f0-9]{40}")
        group = ec2.CfnSecurityGroup(
            self,
            "SecurityGroup",
            vpc_id=subnet.vpc_id,
            group_description="SSM-only AMI builder; no inbound access",
            security_group_ingress=[],
            security_group_egress=[ec2.CfnSecurityGroup.EgressProperty(ip_protocol="-1", cidr_ip="0.0.0.0/0")],
        )
        role = iam.CfnRole(
            self,
            "BuilderRole",
            assume_role_policy_document={
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}
                ],
            },
            managed_policy_arns=["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"],
        )
        profile = iam.CfnInstanceProfile(self, "InstanceProfile", roles=[role.ref])
        script = (
            "#!/bin/bash\nset -euo pipefail\n"
            f"export FACTORY_PARENT_AMI='{ami.value_as_string}'\n"
            f"export FACTORY_SOURCE_REVISION='{revision.value_as_string}'\n" + builder_user_data(Path(__file__).parent)
        )
        host = ec2.CfnInstance(
            self,
            "Builder",
            image_id=ami.value_as_string,
            instance_type="t4g.xlarge",
            iam_instance_profile=profile.ref,
            metadata_options=ec2.CfnInstance.MetadataOptionsProperty(
                http_tokens="required", http_put_response_hop_limit=1
            ),
            network_interfaces=[
                ec2.CfnInstance.NetworkInterfaceProperty(
                    device_index="0",
                    associate_public_ip_address=True,
                    subnet_id=subnet.ref,
                    group_set=[group.ref],
                )
            ],
            block_device_mappings=[
                ec2.CfnInstance.BlockDeviceMappingProperty(
                    device_name="/dev/sda1",
                    ebs=ec2.CfnInstance.EbsProperty(
                        volume_size=30,
                        volume_type="gp3",
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
            tags=[CfnTag(key="Name", value="software-factory-ami-builder")],
            user_data=Fn.base64(script),
        )
        CfnOutput(self, "BuilderInstanceIdOutput", key="BuilderInstanceId", value=host.ref)
