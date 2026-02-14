#!/usr/bin/env python3
"""
CDK Stack: V4 HYBRID 3-Lambda Architecture
==========================================
Lambda 1: Scanner/Opener (1 minute)
Lambda 2: Quick Closer (20 seconds)
Lambda 3: Quick Closer (40 seconds)
"""

import os
from aws_cdk import (
    Stack,
    Duration,
    Size,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
    aws_sns as sns,
    aws_secretsmanager as secretsmanager,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class V4TradingStack(Stack):
    """Stack for V4 HYBRID 3-Lambda Trading System"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Base directory for resolving assets
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
        
        state_table = dynamodb.Table(
            self, "TradingState",
            table_name="V4TradingState",
            partition_key=dynamodb.Attribute(
                name="trader_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True
        )

        state_table.add_global_secondary_index(
            index_name="status-timestamp-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL
        )
        
        unified_trades_table = dynamodb.Table(
            self, "TradesHistoryTable",
            table_name="EmpireTradesHistory",
            partition_key=dynamodb.Attribute(
                name="trader_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        
        skipped_table = dynamodb.Table(
            self, "SkippedTradesTable",
            table_name="EmpireSkippedTrades",
            partition_key=dynamodb.Attribute(
                name="trader_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl"
        )

        # Legacy tables
        empire_crypto_table = dynamodb.Table.from_table_name(
            self, "EmpireCryptoTable",
            table_name="EmpireCryptoV4"
        )

        empire_forex_table = dynamodb.Table.from_table_name(
            self, "EmpireForexTable",
            table_name="EmpireForexHistory"
        )

        empire_indices_table = dynamodb.Table.from_table_name(
            self, "EmpireIndicesTable",
            table_name="EmpireIndicesHistory"
        )

        empire_commodities_table = dynamodb.Table.from_table_name(
            self, "EmpireCommoditiesTable",
            table_name="EmpireCommoditiesHistory"
        )
        
        # =====================================================================
        # Secrets Manager
        # =====================================================================
        binance_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "BinanceKeys", "trading/binance"
        )
        
        # =====================================================================
        # Shared Environment Variables
        # =====================================================================
        common_env = {
            "STATE_TABLE": state_table.table_name,
            "HISTORY_TABLE": "EmpireTradesHistory",
            "SKIPPED_TABLE": "EmpireSkippedTrades",
            "SECRET_NAME": "trading/binance",
            "EXCHANGE": "binance",
            "AWS_REGION": "eu-west-3"
        }
        
        # =====================================================================
        # Lambda 1: SCANNER / OPENER (1 minute)
        # =====================================================================
        
        lambda1_scanner = lambda_.Function(
            self, "Lambda1Scanner",
            function_name="V4_Lambda1_Scanner",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda1_scanner.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "v4_trader")),
            timeout=Duration.seconds(55),  # 55s (marge 5s avant timeout EventBridge)
            memory_size=1536,  # Scanner needs OHLCV cache
            ephemeral_storage_size=Size.mebibytes(1024),
            reserved_concurrent_executions=1,  # Prevent double scans
            environment={
                **common_env,
                "TRADING_MODE": "live",
                "CAPITAL": "1000",
                "SYMBOLS": "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,XRP/USDT:USDT,BNB/USDT:USDT,DOGE/USDT:USDT,PAXG/USDT:USDT,SPX/USDT:USDT,DAX/USDT:USDT,NDX/USDT:USDT,OIL/USDT:USDT,EUR/USD:USDT,GBP/USD:USDT,USD/JPY:USDT,AVAX/USDT:USDT,LINK/USDT:USDT,ADA/USDT:USDT,DOT/USDT:USDT,POL/USDT:USDT",
                "USE_CLAUDE_ANALYSIS": "false",  # Disabled for speed
                "LAMBDA_ROLE": "SCANNER"  # Identifies role
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        
        # =====================================================================
        # Lambda 2: QUICK CLOSER (20 seconds)
        # =====================================================================
        
        lambda2_closer20 = lambda_.Function(
            self, "Lambda2Closer20s",
            function_name="V4_Lambda2_Closer20s",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda2_closer.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "v4_trader")),
            timeout=Duration.seconds(18),  # 18s (marge 2s)
            memory_size=256,  # Minimal - just price checks
            reserved_concurrent_executions=1,
            environment={
                **common_env,
                "TRADING_MODE": "live",
                "LAMBDA_ROLE": "CLOSER_20S"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        
        # =====================================================================
        # Lambda 3: QUICK CLOSER (40 seconds)
        # =====================================================================
        
        lambda3_closer40 = lambda_.Function(
            self, "Lambda3Closer40s",
            function_name="V4_Lambda3_Closer40s",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda2_closer.lambda_handler",  # Same handler
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "v4_trader")),
            timeout=Duration.seconds(18),
            memory_size=256,
            reserved_concurrent_executions=1,
            environment={
                **common_env,
                "TRADING_MODE": "live",
                "LAMBDA_ROLE": "CLOSER_40S"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        
        # =====================================================================
        # Reporter Lambda (unchanged)
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
                "SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,DOGEUSDT,PAXGUSDT,SPXUSDT,DAXUSDT,NDXUSDT,OILUSDT,EURUSDT,GBPUSDT,USDJPYUSDT,AVAXUSDT,LINKUSDT,ADAUSDT,DOTUSDT,POLMATUSDT",
                "TRADING_MODE": "live",
                "HISTORY_TABLE": "EmpireTradesHistory",
                "SNS_TOPIC_ARN": status_topic.topic_arn
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # =====================================================================
        # DynamoDB Permissions
        # =====================================================================
        
        for lam in [lambda1_scanner, lambda2_closer20, lambda3_closer40]:
            state_table.grant_read_write_data(lam)
            unified_trades_table.grant_read_write_data(lam)
            skipped_table.grant_read_write_data(lam)
            empire_crypto_table.grant_read_write_data(lam)
            binance_secret.grant_read(lam)
        
        # Reporter permissions
        status_topic.grant_publish(reporter_lambda)
        unified_trades_table.grant_read_data(reporter_lambda)
        empire_crypto_table.grant_read_data(reporter_lambda)
        empire_forex_table.grant_read_data(reporter_lambda)
        empire_indices_table.grant_read_data(reporter_lambda)
        empire_commodities_table.grant_read_data(reporter_lambda)
        
        reporter_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"]
            )
        )
        
        # =====================================================================
        # Lambda Layer (shared dependencies)
        # =====================================================================
        
        dependency_layer = lambda_.LayerVersion(
            self, "V4DependencyLayer",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "layer")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="CCXT, Pandas, Boto3"
        )
        
        lambda1_scanner.add_layers(dependency_layer)
        lambda2_closer20.add_layers(dependency_layer)
        lambda3_closer40.add_layers(dependency_layer)
        reporter_lambda.add_layers(dependency_layer)
        
        # =====================================================================
        # EventBridge Schedules
        # =====================================================================
        
        # Lambda 1: Every 1 minute (scan + open)
        scanner_rule = events.Rule(
            self, "ScannerSchedule",
            rule_name="V4_Scanner_1min",
            description="Scanner: Scan market + Open positions (1 min)",
            schedule=events.Schedule.expression("cron(* * * * ? *)"),  # Every minute
            enabled=True
        )
        scanner_rule.add_target(targets.LambdaFunction(lambda1_scanner))
        
        # Lambda 2: Every minute at :00, :20, :40 seconds
        # EventBridge doesn't support sub-minute precision natively
        # Workaround: Use Step Functions or custom logic
        # For now: Run every minute, but add 20s delay logic in code
        closer20_rule = events.Rule(
            self, "Closer20Schedule",
            rule_name="V4_Closer_20s",
            description="Closer: Check positions every 20s",
            schedule=events.Schedule.expression("cron(* * * * ? *)"),
            enabled=True
        )
        closer20_rule.add_target(targets.LambdaFunction(
            lambda2_closer20,
            retry_attempts=0  # No retry for time-sensitive closers
        ))
        
        # Lambda 3: Same as Lambda 2, but with 40s delay in code
        closer40_rule = events.Rule(
            self, "Closer40Schedule",
            rule_name="V4_Closer_40s",
            description="Closer: Check positions at 40s mark",
            schedule=events.Schedule.expression("cron(* * * * ? *)"),
            enabled=True
        )
        closer40_rule.add_target(targets.LambdaFunction(
            lambda3_closer40,
            retry_attempts=0
        ))
        
        # Reporter: Every 30 minutes during trading hours
        reporting_rule = events.Rule(
            self, "ReporterSchedule",
            rule_name="V4_Reporter_30min",
            description="Status report every 30 mins",
            schedule=events.Schedule.cron(minute="0/30", hour="9-21"),
            enabled=True
        )
        reporting_rule.add_target(targets.LambdaFunction(reporter_lambda))
        
        # =====================================================================
        # Manual Trigger
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
    target = event.get('target', 'scanner')  # scanner, closer20, closer40
    
    function_map = {{
        'scanner': '{lambda1_scanner.function_name}',
        'closer20': '{lambda2_closer20.function_name}',
        'closer40': '{lambda3_closer40.function_name}'
    }}
    
    function_name = function_map.get(target, '{lambda1_scanner.function_name}')
    
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType='RequestResponse',
        Payload=json.dumps({{'manual': True}})
    )
    result = json.loads(response['Payload'].read())
    return {{'statusCode': 200, 'body': json.dumps(result)}}
            """),
            timeout=Duration.seconds(30)
        )
        
        lambda1_scanner.grant_invoke(manual_trigger)
        lambda2_closer20.grant_invoke(manual_trigger)
        lambda3_closer40.grant_invoke(manual_trigger)
        
        # =====================================================================
        # Outputs
        # =====================================================================
        
        CfnOutput(self, "Lambda1ScannerArn", value=lambda1_scanner.function_arn)
        CfnOutput(self, "Lambda2Closer20Arn", value=lambda2_closer20.function_arn)
        CfnOutput(self, "Lambda3Closer40Arn", value=lambda3_closer40.function_arn)
        CfnOutput(self, "StateTableName", value=state_table.table_name)
        CfnOutput(self, "ManualTriggerArn", value=manual_trigger.function_arn)
