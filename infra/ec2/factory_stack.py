# Define the operational factory stack from a verified AMI with retained storage and stopped execution.
from aws_cdk import BootstraplessSynthesizer, CfnOutput, CfnParameter, CfnTag, Fn, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from constructs import Construct


# Supply only the deployment-specific volume ID to baked storage-first boot preparation.
def user_data(volume_id: str) -> str:
    return (
        "#!/bin/bash\nset -euo pipefail\numask 077\n"
        "install -d -m 0755 /etc/software-factory\n"
        f"printf '%s\\n' '{volume_id}' > /etc/software-factory/volume-id\n"
        "/usr/local/sbin/factory-prepare-host\n"
    )


# Own the SSM host, security group, retained volume and pull-only ECR infrastructure, not shared networking.
class FactoryStack(Stack):
    # Build the operational host in the shared subnet from an explicit verified AMI, without a builder dependency.
    def __init__(self, scope: Construct, construct_id: str, *, subnet: ec2.CfnSubnet, **kwargs: object) -> None:
        super().__init__(scope, construct_id, synthesizer=BootstraplessSynthesizer(), **kwargs)
        ami = CfnParameter(self, "FactoryAmi", type="AWS::EC2::Image::Id")
        runner = ecr.CfnRepository(self, "RunnerRepository", repository_name="software-factory-runner")
        agent = ecr.CfnRepository(self, "AgentRepository", repository_name="software-factory-agent")
        for repository in (runner, agent):
            repository.encryption_configuration = ecr.CfnRepository.EncryptionConfigurationProperty(
                encryption_type="AES256"
            )
            repository.apply_removal_policy(RemovalPolicy.RETAIN)
        group = ec2.CfnSecurityGroup(
            self,
            "SecurityGroup",
            vpc_id=subnet.vpc_id,
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
            availability_zone=subnet.attr_availability_zone,
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
            user_data=Fn.base64(user_data(volume.ref)),
        )
        ec2.CfnVolumeAttachment(self, "DataAttachment", instance_id=host.ref, volume_id=volume.ref, device="/dev/sdf")
        for name, value in {
            "RunnerRepositoryUri": runner.attr_repository_uri,
            "AgentRepositoryUri": agent.attr_repository_uri,
            "InstanceId": host.ref,
            "DataVolumeId": volume.ref,
            "AvailabilityZone": host.attr_availability_zone,
            "FactoryAmi": ami.value_as_string,
        }.items():
            CfnOutput(self, f"{name}Output", key=name, value=value)
