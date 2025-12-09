#!/bin/bash
set -e

ACCOUNT_ID="786382940258"
SOURCE_REGION="ap-northeast-1"
SOURCE_IMAGE="${ACCOUNT_ID}.dkr.ecr.${SOURCE_REGION}.amazonaws.com/karpenter-custom:latest"

REGIONS=("eu-west-1" "us-east-1" "us-west-2")

for REGION in "${REGIONS[@]}"; do
    echo "Processing region: $REGION"
    TARGET_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
    TARGET_IMAGE="${TARGET_REGISTRY}/karpenter-custom:latest"
    
    echo "Pulling latest image from $SOURCE_REGION..."
    aws ecr get-login-password --region $SOURCE_REGION | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${SOURCE_REGION}.amazonaws.com
    docker pull --platform linux/amd64 $SOURCE_IMAGE
    
    echo "Logging in to $TARGET_REGISTRY..."
    aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $TARGET_REGISTRY
    
    echo "Tagging image..."
    docker tag $SOURCE_IMAGE $TARGET_IMAGE
    
    echo "Pushing image to $REGION..."
    docker push $TARGET_IMAGE
    echo "Done for $REGION"
done
