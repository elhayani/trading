#!/bin/bash
set -e

echo "👑 DEPLOYING EMPIRE DASHBOARD INFRASTRUCTURE"
echo "=========================================="

cd EmpireDashboard/infrastructure/cdk

# Install requirements if needed (assuming global/shared venv or similar, but for now just relying on env)
# pip install -r requirements.txt 

cdk deploy EmpireDashboardStack --app "python3 app.py" --require-approval never

echo "✅ Empire Infrastructure Deployed!"
