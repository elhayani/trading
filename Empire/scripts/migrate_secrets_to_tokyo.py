
import boto3
import json
import logging
import sys

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def migrate_secrets():
    try:
        # 1. Connect to Paris (Source)
        logger.info("🌍 Connecting to eu-west-3 (Paris)...")
        client_paris = boto3.client('secretsmanager', region_name='eu-west-3')
        
        secret_name = "trading/binance"
        
        try:
            response = client_paris.get_secret_value(SecretId=secret_name)
        except Exception as e:
            logger.error(f"❌ Failed to get secret from Paris: {e}")
            return
            
        if 'SecretString' in response:
            secret_string = response['SecretString']
            logger.info("✅ Secret retrieved successfully from Paris.")
        else:
            logger.error("❌ Secret is binary, not supported by this script.")
            return

        # 2. Connect to Tokyo (Destination)
        logger.info("🇯🇵 Connecting to ap-northeast-1 (Tokyo)...")
        client_tokyo = boto3.client('secretsmanager', region_name='ap-northeast-1')
        
        # Check if secret exists in Tokyo
        try:
            client_tokyo.describe_secret(SecretId=secret_name)
            exists = True
            logger.info("ℹ️ Secret already exists in Tokyo.")
        except client_tokyo.exceptions.ResourceNotFoundException:
            exists = False
            logger.info("ℹ️ Secret does not exist in Tokyo. Creating...")

        if exists:
            # Update existing secret
            client_tokyo.put_secret_value(
                SecretId=secret_name,
                SecretString=secret_string
            )
            logger.info(f"✅ Secret '{secret_name}' UPDATED in Tokyo.")
        else:
            # Create new secret
            client_tokyo.create_secret(
                Name=secret_name,
                SecretString=secret_string,
                Description="Migrated from eu-west-3 via script"
            )
            logger.info(f"✅ Secret '{secret_name}' CREATED in Tokyo.")
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate_secrets()
