#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.commodities_trading_stack import CommoditiesTradingStack

app = cdk.App()

CommoditiesTradingStack(
    app, "CommoditiesTradingStack",
    env=cdk.Environment(
        account="946179054632",
        region="eu-west-3"
    ),
    description="Commodities Live Trading System"
)

app.synth()
