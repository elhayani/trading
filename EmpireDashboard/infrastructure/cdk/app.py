
#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.dashboard_stack import EmpireDashboardStack

app = cdk.App()

EmpireDashboardStack(
    app, "EmpireDashboardStack",
    env=cdk.Environment(
        account="946179054632",
        region="eu-west-3"
    ),
    description="Empire Dashboard Shared Infrastructure"
)

app.synth()
