
from aws_cdk import (
    Stack,

    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as integrations,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
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

        # Config Table (Panic Switch State)
        config_table = dynamodb.Table(
            self, "EmpireConfig",
            table_name="EmpireConfig",
            partition_key=dynamodb.Attribute(
                name="ConfigKey",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN
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
                "TABLE_NAME": trades_table.table_name,
                "CONFIG_TABLE": config_table.table_name
            }
        )
        
        # Grant Permissions
        trades_table.grant_read_data(api_lambda)
        config_table.grant_read_write_data(api_lambda)

        # =====================================================================
        # API Gateway (HTTP API - Low Cost)
        # =====================================================================
        
        # Define the API
        http_api = apigw.HttpApi(
            self, "EmpireDashboardGateway",
            api_name="EmpireDashboardApi",
            cors_preflight={
                "allow_origins": ["*"],
                "allow_methods": [apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.OPTIONS],
                "allow_headers": ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"]
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

        # Add Route (POST /status) - For Panic Switch
        http_api.add_routes(
            path="/status",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.POST],
            integration=integrations.HttpLambdaIntegration(
                "DashboardApiStatusIntegration",
                api_lambda
            )
        )

        # =====================================================================
        # S3 Frontend Hosting
        # =====================================================================
        
        # 1. Bucket
        frontend_bucket = s3.Bucket(
            self, "EmpireFrontendBucket",
            public_read_access=True,
            website_index_document="index.html",
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            removal_policy=RemovalPolicy.DESTROY, # For dev, clean up easily
            auto_delete_objects=True
        )

        # 2. Deployment (Upload index.html)
        s3deploy.BucketDeployment(
            self, "DeployFrontend",
            sources=[s3deploy.Source.asset("../../frontend")], # Points to EmpireDashboard/frontend
            destination_bucket=frontend_bucket
        )

        # =====================================================================
        # Outputs
        # =====================================================================


        CfnOutput(
            self, "ApiEndpoint",
            value=http_api.api_endpoint,
            description="Dashboard API Endpoint URL"
        )

        CfnOutput(
            self, "DashboardUrl",
            value=frontend_bucket.bucket_website_url,
            description="Empire Dashboard Frontend URL"
        )
