#!/usr/bin/env python3
"""
CDK Stack: V4 HYBRID Live Trading
==================================
Deploy V4 HYBRID on AWS Lambda with EventBridge cron
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class V4TradingStack(Stack):
    """Stack for V4 HYBRID Live Trading System (Crypto)"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =====================================================================
        # DynamoDB Tables
        # =====================================================================
        
        # Trading State Table
        state_table = dynamodb.Table(
            self, "TradingState",
            table_name="V4TradingState",
            partition_key=dynamodb.Attribute(
                name="trader_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,  # Don't delete on stack destroy
            point_in_time_recovery=True
        )
        
        # Trade History Table
        history_table = dynamodb.Table(
            self, "TradeHistory",
            table_name="V4TradeHistory",
            partition_key=dynamodb.Attribute(
                name="trade_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True
        )
        
        # =====================================================================
        # Lambda Layer (Dependencies)
        # =====================================================================
        
        # Note: You need to create this layer manually or with script
        # Includes: ccxt, numpy, requests, etc.
        # See: scripts/create_lambda_layer.sh
        
        # =====================================================================
        # Lambda Function: V4 HYBRID Trader
        # =====================================================================
        
        trading_lambda = lambda_.Function(
            self, "V4HybridTrader",
            function_name="V4HybridLiveTrader",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="v4_hybrid_lambda.lambda_handler",
            code=lambda_.Code.from_asset("../../lambda/v4_trader"),  # Relative to cdk dir
            timeout=Duration.minutes(5),  # Max 5 minutes per execution
            memory_size=512,  # 512 MB
            environment={
               "STATE_TABLE": state_table.table_name,
                "HISTORY_TABLE": history_table.table_name,
                "TRADING_MODE": "test",  # 'test' or 'live'
                "CAPITAL": "1000",
                "SYMBOLS": "SOL/USDT",
                "CHECK_INTERVAL": "3600",  # 1 hour
                "EXCHANGE": "binance"
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # Grant DynamoDB permissions
        state_table.grant_read_write_data(trading_lambda)
        history_table.grant_read_write_data(trading_lambda)
        
        # Grant Permission to EmpireTradesHistory (Shared Table)
        empire_history_table = dynamodb.Table.from_table_name(
            self, "EmpireHistoryTable",
            table_name="EmpireTradesHistory"
        )
        empire_history_table.grant_write_data(trading_lambda)
        
        # Grant Bedrock permissions
        trading_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
                ]
            )
        )
        
        # =====================================================================
        # LAYERS (Dependencies)
        # =====================================================================
        
        # 1. AWS Managed Pandas Layer (Pandas, Numpy, AWS SDK)
        # ARN for us-east-1 Python 3.12 (Verify version matches runtime)
        pandas_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, "AWSPandasLayer",
            layer_version_arn=f"arn:aws:lambda:{self.region}:336392948345:layer:AWSSDKPandas-Python312:8" 
        )
        
        # 2. Custom Layer (CCXT, Requests, etc.)
        # Assumes 'lambda/layer' directory is prepared by deployment script
        dependency_layer = lambda_.LayerVersion(
            self, "V4DependencyLayer",
            code=lambda_.Code.from_asset("../../lambda/layer"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies: ccxt, requests, ta-lib fallback"
        )
        
        trading_lambda.add_layers(pandas_layer)
        trading_lambda.add_layers(dependency_layer)
        
        # =====================================================================
        # EventBridge Rule (Cron: Every Hour)
        # =====================================================================
        
        trading_rule = events.Rule(
            self, "V4TradingSchedule",
            rule_name="V4HybridHourlyCron",
            description="Trigger V4 HYBRID trader every hour",
            schedule=events.Schedule.cron(
                minute="0",  # At minute 0
                hour="*",    # Every hour
                month="*",
                week_day="*",
                year="*"
            ),
            enabled=True  # Set to False to pause trading
        )
        
        # Add Lambda as target
        trading_rule.add_target(
            targets.LambdaFunction(trading_lambda)
        )
        
        # =====================================================================
        # Manual Trigger Lambda (for testing)
        # =====================================================================
        
        manual_trigger = lambda_.Function(
            self, "V4ManualTrigger",
            function_name="V4ManualTrigger",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=lambda_.Code.from_inline(f"""
import json
import boto3

lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    '''Manually trigger V4 trader for testing'''
    
    response = lambda_client.invoke(
        FunctionName='{trading_lambda.function_name}',
        InvocationType='RequestResponse',
        Payload=json.dumps({{'manual': True}})
    )
    
    result = json.loads(response['Payload'].read())
    
    return {{
        'statusCode': 200,
        'body': json.dumps(result)
    }}
            """),
            timeout=Duration.seconds(30)
        )
        
        # Grant permission to invoke trading lambda
        trading_lambda.grant_invoke(manual_trigger)
        
        # =====================================================================
        # Outputs
        # =====================================================================
        
        CfnOutput(
            self, "TradingLambdaArn",
            value=trading_lambda.function_arn,
            description="V4 HYBRID Trading Lambda ARN"
        )
        
        CfnOutput(
            self, "StateTableName",
            value=state_table.table_name,
            description="DynamoDB State Table Name"
        )
        
        CfnOutput(
            self, "HistoryTableName",
            value=history_table.table_name,
            description="DynamoDB History Table Name"
        )
        
        CfnOutput(
            self, "ScheduleRuleName",
            value=trading_rule.rule_name,
            description="EventBridge Cron Rule Name"
        )
        
        CfnOutput(
            self, "ManualTriggerArn",
            value=manual_trigger.function_arn,
            description="Manual Trigger Lambda ARN (for testing)"
        )
