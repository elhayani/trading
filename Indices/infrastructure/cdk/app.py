#!/usr/bin/env python3
"""
CDK App: Forex Trading Deployment
=================================
"""

import aws_cdk as cdk
from stacks.indices_trading_stack import IndicesTradingStack

app = cdk.App()

IndicesTradingStack(
    app, "IndicesTradingStack",
    env=cdk.Environment(
        account="946179054632",
        region="eu-west-3"
    ),
    description="Indices Live Trading System"
)

app.synth()
