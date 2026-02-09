#!/bin/bash
# Build Lambda Layer with CCXT for Dashboard

set -e

echo "🔨 Building Dashboard Lambda Layer..."

# Navigate to layer directory
cd "$(dirname "$0")/../lambda/layer"

# Clean previous build
rm -rf python/
mkdir -p python

# Install dependencies for Linux (Lambda)
echo "📦 Installing CCXT for Linux x86_64 (Python 3.12)..."
python3 -m pip install \
    --platform manylinux2014_x86_64 \
    --target python/ \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade \
    -r requirements.txt



# Clean up unnecessary files to reduce layer size
echo "🧹 Cleaning up..."
find python/ -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find python/ -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find python/ -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find python/ -type f -name "*.pyc" -delete 2>/dev/null || true
find python/ -type f -name "*.pyo" -delete 2>/dev/null || true

echo "✅ Layer built successfully!"
echo "📊 Layer size:"
du -sh python/

echo ""
echo "💡 Next steps:"
echo "   1. Update dashboard_stack.py to use this layer"
echo "   2. Deploy: cd infrastructure/cdk && cdk deploy"
