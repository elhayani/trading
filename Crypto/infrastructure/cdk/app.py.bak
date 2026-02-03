#!/usr/bin/env python3
"""
CDK App: V4 HYBRID Trading Deployment
======================================
"""

import aws_cdk as cdk
from stacks.v4_trading_stack import V4TradingStack

app = cdk.App()

V4TradingStack(
    app, "V4TradingStack",
    env=cdk.Environment(
        account="946179054632",  # Replace with your AWS account
        region="us-east-1"
    ),
    description="V4 HYBRID Live Trading System"
)

app.synth()
