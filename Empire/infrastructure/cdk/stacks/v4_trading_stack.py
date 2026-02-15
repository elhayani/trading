#!/usr/bin/env python3
"""
CDK Stack: V16.0 MOMENTUM SCALPING ARCHITECTURE
================================================
High-Frequency Position Management (4 checks/minute)

Timeline:
- 00s: Scanner (scan + open positions, ~20s duration)
- 15s: Closer #1 (TP/SL/MAX_HOLD check)
- 30s: Closer #2 (TP/SL/MAX_HOLD check)
- 45s: Closer #3 (TP/SL/MAX_HOLD check)

Strategy: 1-minute momentum scalping with 15s check intervals
Target: 40-70 trades/day @ 2-10min holding time
"""

import os
import json
from aws_cdk import (
    Stack,
    Duration,
    Size,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_sns as sns,
    aws_events as events,
    aws_events_targets as targets,
    aws_scheduler as scheduler,
    aws_scheduler_targets as targets_scheduler,
    aws_logs as logs,
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

        v4_trader_code = lambda_.Code.from_asset(
            os.path.join(lambda_root, "v4_trader"),
            exclude=[
                "__pycache__/**",
                "**/__pycache__/**",
                "**/tests/**",
                "numpy/**",
                "pandas/**",
                "numpy-*.dist-info/**",
                "pandas-*.dist-info/**",
                "python_dateutil-*.dist-info/**",
                "six-*.dist-info/**",
                "*.pyc",
            ],
        )

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
            "TRADING_MODE": "LIVE",  # Force LIVE Trading (V16)
        }
        
        # =====================================================================
        # Lambda 1: SCANNER / OPENER (Every minute at 00s)
        # =====================================================================
        
        lambda1_scanner = lambda_.Function(
            self, "Lambda1Scanner",
            function_name="V16_Scanner_00s",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda1_scanner.lambda_handler",
            code=v4_trader_code,
            timeout=Duration.seconds(90),  # Extended for 415 symbols scan
            memory_size=1536,  # Optimized for parallel processing
            ephemeral_storage_size=Size.mebibytes(1024),
            environment={
                **common_env,
                "TRADING_MODE": "dry_run",
                "CAPITAL": "1000",
                "SYMBOLS": "",  # Dynamic loading from Binance
                "MAX_SYMBOLS_PER_SCAN": "150",  # Top 150 by volume
                "LOG_LEVEL": "WARNING",
                "LAMBDA_ROLE": "SCANNER",
                "CLOSER_FUNCTION_NAME": "V16_Closer_15s"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        
        # =====================================================================
        # Lambda 2: CLOSER #1 (15s after scanner)
        # =====================================================================
        
        lambda2_closer15 = lambda_.Function(
            self, "Lambda2Closer15s",
            function_name="V16_Closer_15s",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda2_closer.lambda_handler",
            code=v4_trader_code,
            timeout=Duration.seconds(60),
            memory_size=256,  # Minimal - just price checks
            environment={
                **common_env,
                "TRADING_MODE": "dry_run",
                "LAMBDA_ROLE": "CLOSER_15S",
                "LOG_LEVEL": "WARNING"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        
        # =====================================================================
        # Lambda 3: CLOSER #2 (30s after scanner)
        # =====================================================================
        
        lambda3_closer30 = lambda_.Function(
            self, "Lambda3Closer30s",
            function_name="V16_Closer_30s",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda2_closer.lambda_handler",
            code=v4_trader_code,
            timeout=Duration.seconds(12),
            memory_size=256,
            environment={
                **common_env,
                "TRADING_MODE": "dry_run",
                "LAMBDA_ROLE": "CLOSER_30S",
                "LOG_LEVEL": "WARNING"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        
        # =====================================================================
        # Lambda 4: CLOSER #3 (45s after scanner)
        # =====================================================================
        
        lambda4_closer45 = lambda_.Function(
            self, "Lambda4Closer45s",
            function_name="V16_Closer_45s",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda2_closer.lambda_handler",
            code=v4_trader_code,
            timeout=Duration.seconds(12),
            memory_size=256,
            environment={
                **common_env,
                "TRADING_MODE": "dry_run",
                "LAMBDA_ROLE": "CLOSER_45S",
                "LOG_LEVEL": "WARNING"
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
            code=v4_trader_code,
            timeout=Duration.minutes(1),
            memory_size=512,  # Increased memory for Claude processing
            environment={
                "SYMBOLS": "",  # Empty to force dynamic loading from Binance API
                "MAX_SYMBOLS_PER_SCAN": "100",  # Reduced for Claude analysis performance
                "USE_CLAUDE_ANALYSIS": "true",  # Enabled for advanced sentiment analysis
                "LOG_LEVEL": "WARNING",  # Production: reduce CloudWatch costs
                "TRADING_MODE": "dry_run",
                "HISTORY_TABLE": "EmpireTradesHistory",
                "SNS_TOPIC_ARN": status_topic.topic_arn
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # =====================================================================
        # DynamoDB Permissions
        # =====================================================================
        
        for lam in [lambda1_scanner, lambda2_closer15, lambda3_closer30, lambda4_closer45]:
            state_table.grant_read_write_data(lam)
            unified_trades_table.grant_read_write_data(lam)
            skipped_table.grant_read_write_data(lam)
            empire_crypto_table.grant_read_write_data(lam)
            binance_secret.grant_read(lam)

        lambda2_closer15.grant_invoke(lambda1_scanner)
        
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
        lambda2_closer15.add_layers(dependency_layer)
        lambda3_closer30.add_layers(dependency_layer)
        lambda4_closer45.add_layers(dependency_layer)
        reporter_lambda.add_layers(dependency_layer)
        
        # =====================================================================
        # EventBridge Schedules - V16.0 Momentum Scalping
        # =====================================================================
        
        # Scanner: Every minute at 00s
        scanner_rule = events.Rule(
            self, "ScannerSchedule",
            rule_name="V16_Scanner_00s",
            description="V16 Scanner: Scan 415 symbols + Open positions (00s every minute)",
            schedule=events.Schedule.expression("cron(* * * * ? *)"),  # Every minute
            enabled=True
        )
        scanner_rule.add_target(targets.LambdaFunction(lambda1_scanner))
        
        # EventBridge Scheduler for precise timing
        scheduler_role = iam.Role(
            self, "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            description="Role for EventBridge Scheduler to invoke Lambda closers"
        )

        lambda2_closer15.grant_invoke(scheduler_role)

        # Closer: invoke once per minute, then run sub-minute ticks inside lambda.
        scheduler.CfnSchedule(
            self, "CloserSubMinuteSchedule",
            name="V16_Closer_SubMinute",
            description="V16 Closer: ticks at 00,08,16,24,32,39,46,53 each minute (sleep inside lambda)",
            schedule_expression="cron(* * * * ? *)",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(mode="OFF"),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=lambda2_closer15.function_arn,
                role_arn=scheduler_role.role_arn,
                input=json.dumps({"offset_seconds": [0, 8, 16, 24, 32, 39, 46, 53]}),
                retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(maximum_retry_attempts=0)
            )
        )

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
            self, "V16ManualTrigger",
            function_name="V16ManualTrigger",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=lambda_.Code.from_inline(f"""
import json
import boto3
lambda_client = boto3.client('lambda')
def lambda_handler(event, context):
    target = event.get('target', 'scanner')  # scanner, closer15, closer30, closer45
    
    function_map = {{
        'scanner': '{lambda1_scanner.function_name}',
        'closer15': '{lambda2_closer15.function_name}',
        'closer30': '{lambda3_closer30.function_name}',
        'closer45': '{lambda4_closer45.function_name}'
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
        lambda2_closer15.grant_invoke(manual_trigger)
        lambda3_closer30.grant_invoke(manual_trigger)
        lambda4_closer45.grant_invoke(manual_trigger)

        # =====================================================================
        # Outputs
        # =====================================================================

        CfnOutput(self, "Lambda1ScannerArn", value=lambda1_scanner.function_arn, description="V16 Scanner (00s)")
        CfnOutput(self, "Lambda2Closer15Arn", value=lambda2_closer15.function_arn, description="V16 Closer #1 (15s)")
        CfnOutput(self, "Lambda3Closer30Arn", value=lambda3_closer30.function_arn, description="V16 Closer #2 (30s)")
        CfnOutput(self, "Lambda4Closer45Arn", value=lambda4_closer45.function_arn, description="V16 Closer #3 (45s)")
        CfnOutput(self, "StateTableName", value=state_table.table_name, description="DynamoDB State Table")
        CfnOutput(self, "ManualTriggerArn", value=manual_trigger.function_arn, description="Manual Trigger Function")
