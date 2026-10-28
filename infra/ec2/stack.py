# Create one factory deployment: a dedicated VPC, public subnet, internet gateway
# and routes, plus an outbound-only security group with Session Manager access.
# Provision one Ubuntu ARM64 t4g.xlarge host with IMDSv2, an encrypted disposable
# root disk, and a separate retained, encrypted 100 GiB gp3 data volume.
# Create retained runner/agent ECR repositories and an instance role/profile with
# SSM permissions and repository-scoped image pulls. Embed local host-preparation
# scripts in UserData; leave credentials, image selection, and factory starts manual.
# Export host, volume, repository, AZ, and AMI identifiers; synthesis never contacts AWS.
from pathlib import Path

from aws_cdk import BootstraplessSynthesizer, CfnOutput, CfnParameter, CfnTag, Fn, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from constructs import Construct


# Assemble first-boot files with the exact volume reference; reject EC2's decoded UserData size limit.
def user_data(volume_id: str, directory: Path) -> str:
    script = "#!/bin/bash\nset -euo pipefail\numask 077\n"
    for name in ("prepare-storage", "prepare-host", "check-host"):
        content = (directory / f"{name}.sh").read_text().replace("@DATA_VOLUME_ID@", volume_id)
        destination = "/usr/local/sbin/factory-" + ("host-check" if name == "check-host" else name)
        script += f"cat > {destination} <<'FACTORY_SCRIPT'\n{content}FACTORY_SCRIPT\nchmod 0755 {destination}\n"
    script += f"/usr/local/sbin/factory-prepare-host '{volume_id}'\n"
    # CDK token spelling differs from the resolved EBS volume ID (vol- plus 17 hex digits).
    if len(script.replace(volume_id, "vol-" + "0" * 17).encode()) > 16384:
        raise ValueError("EC2 UserData exceeds the 16384-byte limit")
    return script


# Own only the approved network, SSM host, retained volume and pull-only ECR infrastructure.
class FactoryStack(Stack):
    # Build one fixed-region stack; Ubuntu AMI remains an explicit operator-verified deployment parameter.
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, synthesizer=BootstraplessSynthesizer(), **kwargs)
        ami = CfnParameter(self, "UbuntuAmi", type="AWS::EC2::Image::Id")
        runner = ecr.CfnRepository(self, "RunnerRepository", repository_name="software-factory-runner")
        agent = ecr.CfnRepository(self, "AgentRepository", repository_name="software-factory-agent")
        for repository in (runner, agent):
            repository.encryption_configuration = ecr.CfnRepository.EncryptionConfigurationProperty(
                encryption_type="AES256"
            )
            repository.apply_removal_policy(RemovalPolicy.RETAIN)
        vpc = ec2.CfnVPC(self, "Vpc", cidr_block="10.77.0.0/16", enable_dns_support=True, enable_dns_hostnames=True)
        gateway = ec2.CfnInternetGateway(self, "InternetGateway")
        gateway_attachment = ec2.CfnVPCGatewayAttachment(
            self, "GatewayAttachment", vpc_id=vpc.ref, internet_gateway_id=gateway.ref
        )
        az = Fn.select(0, Fn.get_azs())
        subnet = ec2.CfnSubnet(self, "Subnet", vpc_id=vpc.ref, cidr_block="10.77.1.0/24", availability_zone=az)
        table = ec2.CfnRouteTable(self, "RouteTable", vpc_id=vpc.ref)
        association = ec2.CfnSubnetRouteTableAssociation(
            self, "SubnetRouteTable", subnet_id=subnet.ref, route_table_id=table.ref
        )
        route = ec2.CfnRoute(
            self, "DefaultRoute", route_table_id=table.ref, destination_cidr_block="0.0.0.0/0", gateway_id=gateway.ref
        )
        route.add_resource_dependency(gateway_attachment)
        group = ec2.CfnSecurityGroup(
            self,
            "SecurityGroup",
            vpc_id=vpc.ref,
            group_description="Outbound only; administer through Session Manager",
            security_group_ingress=[],
            security_group_egress=[ec2.CfnSecurityGroup.EgressProperty(ip_protocol="-1", cidr_ip="0.0.0.0/0")],
        )
        role = iam.CfnRole(
            self,
            "HostRole",
            assume_role_policy_document={
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}
                ],
            },
            managed_policy_arns=["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"],
            policies=[
                iam.CfnRole.PolicyProperty(
                    policy_name="FactoryImagePull",
                    policy_document={
                        "Version": "2012-10-17",
                        "Statement": [
                            {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "ecr:BatchCheckLayerAvailability",
                                    "ecr:GetDownloadUrlForLayer",
                                    "ecr:BatchGetImage",
                                ],
                                "Resource": [runner.attr_arn, agent.attr_arn],
                            },
                        ],
                    },
                )
            ],
        )
        profile = iam.CfnInstanceProfile(self, "InstanceProfile", roles=[role.ref])
        volume = ec2.CfnVolume(
            self,
            "DataVolume",
            availability_zone=az,
            encrypted=True,
            size=100,
            volume_type="gp3",
            tags=[CfnTag(key="Name", value="software-factory-data")],
        )
        volume.apply_removal_policy(RemovalPolicy.RETAIN)
        host = ec2.CfnInstance(
            self,
            "Host",
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
            tags=[CfnTag(key="Name", value="software-factory")],
            user_data=Fn.base64(user_data(volume.ref, Path(__file__).parent)),
        )
        host.add_resource_dependency(route)
        host.add_resource_dependency(association)
        ec2.CfnVolumeAttachment(self, "DataAttachment", instance_id=host.ref, volume_id=volume.ref, device="/dev/sdf")
        for name, value in {
            "RunnerRepositoryUri": runner.attr_repository_uri,
            "AgentRepositoryUri": agent.attr_repository_uri,
            "InstanceId": host.ref,
            "DataVolumeId": volume.ref,
            "AvailabilityZone": host.attr_availability_zone,
            "UbuntuAmi": ami.value_as_string,
        }.items():
            CfnOutput(self, f"{name}Output", key=name, value=value)
