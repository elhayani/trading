#!/usr/bin/env python3
"""
CDK Stack: V4 HYBRID Live Trading
==================================
Deploy V4 HYBRID on AWS Lambda with EventBridge cron
"""

import os
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
    aws_sns as sns,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class V4TradingStack(Stack):
    """Stack for V4 HYBRID Live Trading System (Crypto)"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Base directory for resolving assets (relative to this file)
        base_dir = os.path.dirname(os.path.realpath(__file__))
        lambda_root = os.path.join(base_dir, "../../../lambda")

        # =====================================================================
        # SNS Topic (Notifications)
        # =====================================================================
        status_topic = sns.Topic(
            self, "EmpireStatusTopic",
            topic_name="Empire_Status_Reports",
            display_name="Empire V4 Status"
        )

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
        # Lambda Function: V4 HYBRID Trader
        # =====================================================================
        
        trading_lambda = lambda_.Function(
            self, "V4HybridTrader",
            function_name="V4HybridLiveTrader",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="v4_hybrid_lambda.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "v4_trader")),
            timeout=Duration.minutes(5),  # Max 5 minutes per execution
            memory_size=512,  # 512 MB
            environment={
                "STATE_TABLE": state_table.table_name,
                "HISTORY_TABLE": "EmpireTradesHistory",
                "TRADING_MODE": "live",  # 🚀 LIVE TRADING ACTIVATED
                "API_KEY": "8GMSKB5dEktu58yrd3P5NCNabI9mDHIY8zpvnO7ZXsIW3NnEzjD7Ppf5cZeoOCnC",
                "SECRET_KEY": "2V89JGWnqPdEL1ilbwx1va6r14Lc9g78ZufY3OJdQrjhRdZhE1DTc3nVBI6Y7sju",
                "CAPITAL": "1000",
                "SYMBOLS": "BTC/USDT,ETH/USDT,SOL/USDT,PAXG/USDT,XAG/USDT,OIL/USDT,SPX/USDT,NDX/USDT",
                "CHECK_INTERVAL": "3600",  # 1 hour
                "EXCHANGE": "binance"
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # Grant DynamoDB permissions
        state_table.grant_read_write_data(trading_lambda)
        history_table.grant_read_write_data(trading_lambda)
        # Grant Permission to EmpireCryptoV4 (Legacy)
        empire_history_table = dynamodb.Table(
            self, "EmpireCryptoTable",
            table_name="EmpireCryptoV4",
            partition_key=dynamodb.Attribute(
                name="TradeId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True
        )
        empire_history_table.grant_read_write_data(trading_lambda)
        
        # Grant access to unified EmpireTradesHistory table
        unified_trades_table = dynamodb.Table(
            self, "UnifiedEmpireTable",
            table_name="EmpireTradesHistory",
            partition_key=dynamodb.Attribute(name="TradeId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True
        )
        
        # 🚀 V8 PERFORMANCE INDEX: GSI_OpenByPair (Audit #V8.6: Optimized Composite Key)
        unified_trades_table.add_global_secondary_index(
            index_name="GSI_OpenByPair",
            partition_key=dynamodb.Attribute(name="Status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="PairTimestamp", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL
        )
        
        unified_trades_table.grant_read_write_data(trading_lambda)
        # Define other tables for Reporting (Forex, Indices, Commodities)
        # We define them here so CDK creates them if they don't exist, and we can grant permissions.
        
        empire_forex_table = dynamodb.Table(
            self, "EmpireForexTable",
            table_name="EmpireForexHistory",
            partition_key=dynamodb.Attribute(name="TradeId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True
        )

        empire_indices_table = dynamodb.Table(
            self, "EmpireIndicesTable",
            table_name="EmpireIndicesHistory",
            partition_key=dynamodb.Attribute(name="TradeId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True
        )

        empire_commodities_table = dynamodb.Table(
            self, "EmpireCommoditiesTable",
            table_name="EmpireCommoditiesHistory",
            partition_key=dynamodb.Attribute(name="TradeId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True
        )
        
        # Grant Bedrock permissions
        trading_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    f"arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
                ]
            )
        )
        
        # =====================================================================
        # Reporter Lambda (Independent)
        # =====================================================================
        reporter_lambda = lambda_.Function(
            self, "V4StatusReporter",
            function_name="V4StatusReporter",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="reporter.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "v4_trader")),
            timeout=Duration.minutes(1),
            memory_size=256,
            environment={
                "SYMBOLS": "BTC/USDT,ETH/USDT,SOL/USDT,PAXG/USDT,XAG/USDT,OIL/USDT,SPX/USDT,NDX/USDT",
                "TRADING_MODE": "live",
                "SNS_TOPIC_ARN": status_topic.topic_arn
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # Reporter Permissions
        # Reporter Permissions
        status_topic.grant_publish(reporter_lambda)
        empire_history_table.grant_read_data(reporter_lambda)
        empire_forex_table.grant_read_data(reporter_lambda)
        empire_indices_table.grant_read_data(reporter_lambda)
        empire_commodities_table.grant_read_data(reporter_lambda)
        
        # Grant SES SendEmail Permission
        reporter_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ses:SendEmail",
                    "ses:SendRawEmail"
                ],
                resources=["*"] # Can restrict to specific identity ARN for tighter security
            )
        )
        
        # =====================================================================
        # LAYERS (Dependencies)
        # =====================================================================
        
        # 1. AWS Managed Pandas Layer (Pandas, Numpy, AWS SDK)
        # ARN for us-east-1 Python 3.12 (Verify version matches runtime)
        # Note: Using eu-west-3 ARN if available or assuming deployment script handles it. 
        # Actually using strict ARN for eu-west-3 for Python 3.12:
        # pandas_layer = lambda_.LayerVersion.from_layer_version_arn(
        #      self, "AWSPandasLayer",
        #      layer_version_arn=f"arn:aws:lambda:eu-west-3:336392948345:layer:AWSSDKPandas-Python312:13" 
        # )
        # Note: Version 13 is current stable for py3.12 in eu-west-3 as of mid-2024. If error, try 8 or 12.
        
        # 2. Custom Layer (CCXT, Requests, etc.)
        dependency_layer = lambda_.LayerVersion(
            self, "V4DependencyLayer",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "layer")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies: ccxt, requests, ta-lib fallback"
        )
        
        # trading_lambda.add_layers(pandas_layer)
        trading_lambda.add_layers(dependency_layer)
        
        # reporter_lambda.add_layers(pandas_layer)
        reporter_lambda.add_layers(dependency_layer)
        
        # =====================================================================
        # EventBridge Rules
        # =====================================================================
        
        # 1. ECO Rule (Minuit - 06h Paris UTC+1 -> 23h-05h UTC) - 20 min
        eco_rule = events.Rule(
            self, "EmpireEcoRule",
            rule_name="EmpireEcoRule",
            description="ECO Mode: 20 min interval (00-06h Paris)",
            schedule=events.Schedule.expression("cron(0/20 23-4 * * ? *)"),
            enabled=True
        )
        eco_rule.add_target(targets.LambdaFunction(trading_lambda))

        # 2. STANDARD AM Rule (06h - 13h55 Paris UTC+1 -> 05h-12h55 UTC) - 5 min
        std_am_rule = events.Rule(
            self, "EmpireStandardAMRule",
            rule_name="EmpireStandardAMRule",
            description="STANDARD AM: 5 min interval (06h-14h Paris)",
            schedule=events.Schedule.expression("cron(0/5 5-12 * * ? *)"),
            enabled=True
        )
        std_am_rule.add_target(targets.LambdaFunction(trading_lambda))

        # 3. TURBO Rule (14h00 - 16h00 Paris UTC+1 -> 13h-15h UTC) - 1 min
        # Covers US Open (14h30/15h30 Paris depending on season, here broadly 13-14 UTC is 14-16h Paris winter)
        turbo_rule = events.Rule(
            self, "EmpireTurboRule",
            rule_name="EmpireTurboRule",
            description="TURBO SPX: 1 min interval (14h-16h Paris)",
            schedule=events.Schedule.expression("cron(* 13-14 * * ? *)"),
            enabled=True
        )
        turbo_rule.add_target(targets.LambdaFunction(trading_lambda))

        # 4. STANDARD PM Rule (16h - Minuit Paris UTC+1 -> 15h-23h UTC) - 5 min
        std_pm_rule = events.Rule(
            self, "EmpireStandardPMRule",
            rule_name="EmpireStandardPMRule",
            description="STANDARD PM: 5 min interval (16h-Minuit Paris)",
            schedule=events.Schedule.expression("cron(0/5 15-22 * * ? *)"),
            enabled=True
        )
        std_pm_rule.add_target(targets.LambdaFunction(trading_lambda))
        
        # 2. Reporting Bot (Every 30 mins, 9h-21h)
        reporting_rule = events.Rule(
            self, "V4ReportingSchedule",
            rule_name="V4ReporterCron",
            description="Trigger Status Report every 30 mins (9-21h UTC)",
            schedule=events.Schedule.cron(
                minute="0/30",
                hour="9-21",
                month="*",
                week_day="*",
                year="*"
            ),
            enabled=True
        )
        reporting_rule.add_target(targets.LambdaFunction(reporter_lambda))
        
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
            value=eco_rule.rule_name,
            description="EventBridge Eco Rule Name (Main)"
        )
        
        CfnOutput(
            self, "ManualTriggerArn",
            value=manual_trigger.function_arn,
            description="Manual Trigger Lambda ARN (for testing)"
        )
