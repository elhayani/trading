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
        account="946179054632",
        region="ap-northeast-1"  # Tokyo Region (Binance HFT Latency Optimized)
    ),
    description="V16.0 Momentum Scalping System (Tokyo Optimized)"
)

app.synth()
