# Synthesize persistent networking and separate builder/factory stacks in the approved account/region; never deploy.
from aws_cdk import App, Environment

from infra.ec2.builder_stack import BuilderStack
from infra.ec2.factory_stack import FactoryStack
from infra.ec2.shared import SharedStack

app = App()
environment = Environment(account="172318459814", region="eu-central-1")
shared = SharedStack(app, "software-factory-shared", env=environment)
BuilderStack(app, "software-factory-ami-builder", subnet=shared.subnet, env=environment)
FactoryStack(app, "software-factory", subnet=shared.subnet, env=environment)
app.synth()
