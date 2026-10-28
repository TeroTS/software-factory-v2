# Own persistent public networking shared by disposable builders and the operational factory; never run workloads.
from aws_cdk import BootstraplessSynthesizer, Fn, Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


# Keep the VPC, subnet and outbound routing independent of either consumer stack's lifecycle.
class SharedStack(Stack):
    # Expose one public subnet in the approved region; consumers supply their own security groups and identities.
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, synthesizer=BootstraplessSynthesizer(), **kwargs)
        vpc = ec2.CfnVPC(self, "Vpc", cidr_block="10.77.0.0/16", enable_dns_support=True, enable_dns_hostnames=True)
        gateway = ec2.CfnInternetGateway(self, "InternetGateway")
        attachment = ec2.CfnVPCGatewayAttachment(
            self, "GatewayAttachment", vpc_id=vpc.ref, internet_gateway_id=gateway.ref
        )
        self.subnet = ec2.CfnSubnet(
            self, "Subnet", vpc_id=vpc.ref, cidr_block="10.77.1.0/24", availability_zone=Fn.select(0, Fn.get_azs())
        )
        table = ec2.CfnRouteTable(self, "RouteTable", vpc_id=vpc.ref)
        ec2.CfnSubnetRouteTableAssociation(
            self, "SubnetRouteTable", subnet_id=self.subnet.ref, route_table_id=table.ref
        )
        route = ec2.CfnRoute(
            self, "DefaultRoute", route_table_id=table.ref, destination_cidr_block="0.0.0.0/0", gateway_id=gateway.ref
        )
        route.add_resource_dependency(attachment)
