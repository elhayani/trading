import os
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    CfnOutput
)
from constructs import Construct

class ForexTradingStack(Stack):
    """Stack for Forex Live Trading System"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Base directory for resolving assets
        base_dir = os.path.dirname(os.path.realpath(__file__))
        lambda_root = os.path.join(base_dir, "../../../lambda")

        # =====================================================================
        # Lambda Function: Forex Trader
        # =====================================================================
        
        forex_lambda = lambda_.Function(
            self, "ForexTrader",
            function_name="ForexLiveTrader",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "forex_trader")),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "TRADING_MODE": "live"
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )
        
        # =====================================================================
        # LAYERS (Dependencies)
        # =====================================================================
        
        # 1. AWS Managed Pandas Layer (Pandas, Numpy)
        pandas_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, "AWSPandasLayer",
            layer_version_arn=f"arn:aws:lambda:{self.region}:336392948345:layer:AWSSDKPandas-Python312:8"
        )
        
        # 2. Custom Layer (yfinance, pandas_ta)
        dependency_layer = lambda_.LayerVersion(
            self, "ForexDependencyLayer",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "layer_forex")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies: yfinance, pandas_ta"
        )
        
        forex_lambda.add_layers(pandas_layer)
        forex_lambda.add_layers(dependency_layer)
        
        # Grant Bedrock Permissions
        forex_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"]
            )
        )

        # Grant Permission to EmpireForexHistory (Specific Table)
        history_table = dynamodb.Table.from_table_name(
            self, "HistoryTable",
            table_name="EmpireForexHistory"
        )
        history_table.grant_write_data(forex_lambda)
        history_table.grant_read_data(forex_lambda)
        
        # Add table name to env
        forex_lambda.add_environment("DYNAMO_TABLE", history_table.table_name)
        
        # =====================================================================
        # EventBridge Rule (Cron: Every Hour)
        # =====================================================================
        
        # Run at minute 5 past the hour to avoid conflict with other bots at :00
        trading_rule = events.Rule(
            self, "ForexTradingSchedule",
            rule_name="ForexHourlyCron",
            description="Trigger Forex trader every hour",
            schedule=events.Schedule.cron(
                minute="5,35",
                hour="*",
                month="*",
                week_day="*",
                year="*"
            ),
            enabled=True
        )
        
        trading_rule.add_target(targets.LambdaFunction(forex_lambda))
        
        # =====================================================================
        # Outputs
        # =====================================================================
        
        CfnOutput(
            self, "ForexLambdaArn",
            value=forex_lambda.function_arn,
            description="Forex Trading Lambda ARN"
        )
