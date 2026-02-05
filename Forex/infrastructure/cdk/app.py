#!/usr/bin/env python3
"""
CDK App: Forex Trading Deployment
=================================
"""

import aws_cdk as cdk
from stacks.forex_trading_stack import ForexTradingStack

app = cdk.App()

ForexTradingStack(
    app, "ForexTradingStack",
    env=cdk.Environment(
        account="946179054632",
        region="eu-west-3"
    ),
    description="Forex Live Trading System"
)

app.synth()
