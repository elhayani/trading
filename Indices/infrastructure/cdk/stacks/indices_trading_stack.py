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

class IndicesTradingStack(Stack):
    """Stack for Indices Live Trading System"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Base directory for resolving assets
        base_dir = os.path.dirname(os.path.realpath(__file__))
        lambda_root = os.path.join(base_dir, "../../../lambda")

        # =====================================================================
        # Lambda Function: Indices Trader
        # =====================================================================
        
        indices_lambda = lambda_.Function(
            self, "IndicesTrader",
            function_name="IndicesLiveTrader",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "indices_trader")),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "TRADING_MODE": "live",
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
            self, "IndicesDependencyLayer",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "layer_indices")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies: yfinance, pandas_ta"
        )
        
        indices_lambda.add_layers(pandas_layer)
        indices_lambda.add_layers(dependency_layer)
        
        # Grant Bedrock Permissions
        indices_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"]
            )
        )

        # Grant Permission to EmpireIndicesHistory (Specific Table)
        # We reference it by name since it's in a different stack
        history_table = dynamodb.Table.from_table_name(
            self, "HistoryTable",
            table_name="EmpireIndicesHistory"
        )
        history_table.grant_write_data(indices_lambda)
        history_table.grant_read_data(indices_lambda)
        
        # Add table name to env
        indices_lambda.add_environment("DYNAMO_TABLE", history_table.table_name)
        
        # =====================================================================
        # EventBridge Rule (Cron: Every Hour)
        # =====================================================================
        
        # Run at minute 10 past the hour to avoid conflict with other bots
        trading_rule = events.Rule(
            self, "IndicesTradingSchedule",
            rule_name="IndicesHourlyCron",
            description="Trigger Indices trader every hour",
            schedule=events.Schedule.expression("cron(10,40 * ? * MON-FRI *)"), # Explicit cron expression to avoid CDK validation issues
            enabled=True
        )
        
        trading_rule.add_target(targets.LambdaFunction(indices_lambda))
        
        # =====================================================================
        # Outputs
        # =====================================================================
        
        CfnOutput(
            self, "IndicesLambdaArn",
            value=indices_lambda.function_arn,
            description="Indices Trading Lambda ARN"
        )
