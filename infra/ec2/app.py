# Synthesize the approved account/region stack without lookups, assets, bootstrap resources, or deployment side effects.
from aws_cdk import App, Environment

from infra.ec2.stack import FactoryStack

app = App()
FactoryStack(app, "software-factory", env=Environment(account="172318459814", region="eu-central-1"))
app.synth()
