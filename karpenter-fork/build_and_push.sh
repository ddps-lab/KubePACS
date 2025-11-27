#!/bin/bash
set -e

# Configuration
ECR_REPO="786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom"
REGION="ap-northeast-2"
PROFILE="default"

# Login to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region $REGION --profile $PROFILE | docker login --username AWS --password-stdin $ECR_REPO 

# Build the image
echo "Building Docker image..."
# Build the image from the parent directory to include karpenter-core
cd $(dirname "$0")/..
docker build -f karpenter-fork/Dockerfile -t $ECR_REPO:latest .

# Push the image
echo "Pushing image to ECR..."
docker push $ECR_REPO:latest

echo "Done! Image pushed to $ECR_REPO:latest"
