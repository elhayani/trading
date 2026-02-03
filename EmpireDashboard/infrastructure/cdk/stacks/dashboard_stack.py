
from aws_cdk import (
    Stack,

    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as integrations,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct

class EmpireDashboardStack(Stack):
    """Stack for Empire Dashboard Shared Resources"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =====================================================================
        # DynamoDB: Empire Trades History (Source of Truth)
        # =====================================================================
        trades_table = dynamodb.Table(
            self, "EmpireTradesHistory",
            table_name="EmpireTradesHistory",  # Fixed name for easy access by other stacks
            partition_key=dynamodb.Attribute(
                name="TradeId",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN, # Don't delete data if stack is destroyed
        )

        # =====================================================================
        # Lambda: Dashboard API (Reader)
        # =====================================================================
        api_lambda = lambda_.Function(
            self, "DashboardApiLambda",
            function_name="EmpireDashboardApi",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            code=lambda_.Code.from_asset("../../lambda/dashboard_api"),  # Relative to cdk dir
            environment={
                "TABLE_NAME": trades_table.table_name
            }
        )
        
        # Grant Read Access to Table
        trades_table.grant_read_data(api_lambda)

        # =====================================================================
        # API Gateway (HTTP API - Low Cost)
        # =====================================================================
        
        # Define the API
        http_api = apigw.HttpApi(
            self, "EmpireDashboardGateway",
            api_name="EmpireDashboardApi",
            cors_preflight={
                "allow_origins": ["*"],
                "allow_methods": [apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.OPTIONS],
                "allow_headers": ["*"]
            }
        )
        
        # Add Route (GET /stats)
        http_api.add_routes(
            path="/stats",
            methods=[apigw.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration(
                "DashboardApiIntegration",
                api_lambda
            )
        )

        # =====================================================================
        # Outputs
        # =====================================================================


        CfnOutput(
            self, "ApiEndpoint",
            value=http_api.api_endpoint,
            description="Dashboard API Endpoint URL"
        )
