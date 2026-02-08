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

class CommoditiesTradingStack(Stack):
    """Stack for Commodities Live Trading System"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Base directory for resolving assets
        base_dir = os.path.dirname(os.path.realpath(__file__))
        lambda_root = os.path.join(base_dir, "../../../lambda")

        # =====================================================================
        # Lambda Function: Commodities Trader
        # =====================================================================
        
        commodities_lambda = lambda_.Function(
            self, "CommoditiesTrader",
            function_name="CommoditiesLiveTrader",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "commodities_trader")),
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
            self, "CommoditiesDependencyLayer",
            code=lambda_.Code.from_asset(os.path.join(lambda_root, "layer_commodities")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies: yfinance, pandas_ta"
        )
        
        commodities_lambda.add_layers(pandas_layer)
        commodities_lambda.add_layers(dependency_layer)
        
        # Grant Bedrock Permissions
        commodities_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"]
            )
        )

        # Grant Permission to EmpireCommoditiesHistory (Dedicated Table)
        history_table = dynamodb.Table.from_table_name(
            self, "HistoryTable",
            table_name="EmpireCommoditiesHistory"
        )
        history_table.grant_read_write_data(commodities_lambda)
        
        # =====================================================================
        # EventBridge Rule (Cron: Every Hour)
        # =====================================================================
        
        # Run at minute 15 past the hour to avoid conflict with other bots
        trading_rule = events.Rule(
            self, "CommoditiesTradingSchedule",
            rule_name="CommoditiesHourlyCron",
            description="Trigger Commodities trader every hour",
            schedule=events.Schedule.expression("cron(15,45 * ? * MON-FRI *)"), 
            enabled=True
        )
        
        trading_rule.add_target(targets.LambdaFunction(commodities_lambda))
        
        # =====================================================================
        # Outputs
        # =====================================================================
        
        CfnOutput(
            self, "CommoditiesLambdaArn",
            value=commodities_lambda.function_arn,
            description="Commodities Trading Lambda ARN"
        )
