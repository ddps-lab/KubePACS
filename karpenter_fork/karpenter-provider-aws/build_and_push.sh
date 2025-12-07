#!/bin/bash
set -e

# Configuration
ECR_REPO="786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom"
REGION="ap-northeast-2"
PROFILE="default"

# Login to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region $REGION --profile $PROFILE | docker login --username AWS --password-stdin $ECR_REPO 

# Create and use a builder instance that supports multi-arch
if ! docker buildx inspect karpenter-builder > /dev/null 2>&1; then
    docker buildx create --name karpenter-builder --use
fi

# Build and push the image
echo "Building and pushing multi-arch Docker image..."
# Build the image from the parent directory to include karpenter-core
cd $(dirname "$0")/..
docker buildx build --platform linux/amd64 --build-arg CACHEBUST=$(date +%s) -f karpenter-fork/Dockerfile -t $ECR_REPO:v17 --push .

echo "Done! Image pushed to $ECR_REPO:v17"
