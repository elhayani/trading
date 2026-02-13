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
        
        # Trading State Table (Keep as managed if it's new, or use from_table_name if legacy)
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

        # ✅ GSI Optimized Query (Audit #V11.5)
        state_table.add_global_secondary_index(
            index_name="status-timestamp-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL
        )
        
        # Trades History Table (OPEN/CLOSED only — V13.4 clean table)
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
        
        # Skipped Trades Table (séparation V13.4 - évite de polluer l'historique)
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
            time_to_live_attribute="ttl"  # Auto-delete old skips after 7 days
        )

        # ✅ NOUVEAU GSI — Daily PnL optimisé (Audit #V9.5)
        # Note: If the table exists, you might need to add this manually in the console or use a Custom Resource,
        # but in a CDK-managed context, we define it here.
        # Since it's from_table_name, CDK won't manage the index creation automatically if it's external.
        # But we keep it in the code as reference documentation for the infrastructure.
        
        # Legacy Crypto Table
        empire_crypto_table = dynamodb.Table.from_table_name(
            self, "EmpireCryptoTable",
            table_name="EmpireCryptoV4"
        )

        # Other History Tables
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
        # Lambda Function: V4 HYBRID Trader
        # =====================================================================
        
        trading_lambda = lambda_.Function(
            self, "V4HybridTrader",
            function_name="V4HybridLiveTrader",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="v4_hybrid_lambda.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "v4_trader")),
            timeout=Duration.minutes(5),
            memory_size=1536,  # 🚀 Optimization: 1.5GB for CCXT/Pandas/AI + OHLCV Cache
            ephemeral_storage_size=Size.mebibytes(1024),  # ✅ 1GB /tmp for OHLCV cache
            # reserved_concurrent_executions=1, # 🔒 Safety: Prevent double trades (Temporarily disabled due to env limit)
            environment={
                "STATE_TABLE": state_table.table_name,
                "HISTORY_TABLE": "EmpireTradesHistory",
                "SKIPPED_TABLE": "EmpireSkippedTrades",
                "TRADING_MODE": "live",
                "SECRET_NAME": "trading/binance", # 🛡️ SECURE: No hardcoded keys
                "CAPITAL": "1000",
                "SYMBOLS": "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,XRP/USDT:USDT,BNB/USDT:USDT,DOGE/USDT:USDT,PAXG/USDT:USDT,SPX/USDT:USDT,DAX/USDT:USDT,NDX/USDT:USDT,OIL/USDT:USDT,EUR/USD:USDT,GBP/USD:USDT,USD/JPY:USDT,USDC/USDT:USDT,AVAX/USDT:USDT,LINK/USDT:USDT,ADA/USDT:USDT,DOT/USDT:USDT,MATIC/USDT:USDT",
                "RSI_THRESHOLD": "35",
                "CHECK_INTERVAL": "3600",
                "EXCHANGE": "binance",
                "USE_CLAUDE_ANALYSIS": "true"  # Enable Claude 3.5 Sonnet for advanced analysis
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # Grant DynamoDB permissions
        state_table.grant_read_write_data(trading_lambda)
        unified_trades_table.grant_read_write_data(trading_lambda)
        skipped_table.grant_read_write_data(trading_lambda)
        empire_crypto_table.grant_read_write_data(trading_lambda)
        
        # 🛡️ AWS Secrets Manager Permission
        binance_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "BinanceKeys", "trading/binance"
        )
        binance_secret.grant_read(trading_lambda)
        
        # Grant Bedrock permissions for Claude 3.5 Sonnet (advanced news analysis)
        trading_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
                    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
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
                "SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,DOGEUSDT,PAXGUSDT,SPXUSDT,DAXUSDT,NDXUSDT,OILUSDT,EURUSDT,GBPUSDT,USDJPYUSDT,USDCUSDT,AVAXUSDT,LINKUSDT,ADAUSDT,DOTUSDT,MATICUSDT",
                "TRADING_MODE": "live",
                "HISTORY_TABLE": "EmpireTradesHistory",
                "SNS_TOPIC_ARN": status_topic.topic_arn
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # Reporter Permissions: Access to all relevant tables
        status_topic.grant_publish(reporter_lambda)
        unified_trades_table.grant_read_data(reporter_lambda)
        empire_crypto_table.grant_read_data(reporter_lambda)
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
                resources=["*"]
            )
        )
        
        # =====================================================================
        # LAYERS (Dependencies)
        # =====================================================================
        
        dependency_layer = lambda_.LayerVersion(
            self, "V4DependencyLayer",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "layer")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies: ccxt, requests, ta-lib fallback"
        )
        
        trading_lambda.add_layers(dependency_layer)
        reporter_lambda.add_layers(dependency_layer)
        
        # =====================================================================
        # EventBridge Rules (Timezone consideration: Crons are UTC)
        # =====================================================================
        
        # Global Heartbeat Rule (Every 1 minute)
        # Monitors market, manages exits, and checks entry signals continuously.
        # Note: News fetching is cached internally for 15 mins to save costs.
        global_rule = events.Rule(
            self, "EmpireGlobalMonitoring",
            rule_name="EmpireGlobalMonitoring",
            description="Global Heartbeat: 1 min interval",
            schedule=events.Schedule.expression("cron(* * * * ? *)"),
            enabled=True
        )
        global_rule.add_target(targets.LambdaFunction(trading_lambda))
        
        # Reporting Bot (Every 30 mins)
        reporting_rule = events.Rule(
            self, "V4ReportingSchedule",
            rule_name="V4ReporterCron",
            description="Trigger Status Report every 30 mins",
            schedule=events.Schedule.cron(minute="0/30", hour="9-21"),
            enabled=True
        )
        reporting_rule.add_target(targets.LambdaFunction(reporter_lambda))
        
        # =====================================================================
        # Manual Trigger Lambda
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
    response = lambda_client.invoke(
        FunctionName='{trading_lambda.function_name}',
        InvocationType='RequestResponse',
        Payload=json.dumps({{'manual': True}})
    )
    result = json.loads(response['Payload'].read())
    return {{'statusCode': 200, 'body': json.dumps(result)}}
            """),
            timeout=Duration.seconds(30)
        )
        trading_lambda.grant_invoke(manual_trigger)
        
        # =====================================================================
        # Outputs
        # =====================================================================
        
        CfnOutput(self, "TradingLambdaArn", value=trading_lambda.function_arn)
        CfnOutput(self, "StateTableName", value=state_table.table_name)
        CfnOutput(self, "HistoryTableName", value=unified_trades_table.table_name)
        CfnOutput(self, "ManualTriggerArn", value=manual_trigger.function_arn)
