#!/bin/bash
set -e

ACCOUNT_ID="786382940258"
SOURCE_REGION="ap-northeast-2"
SOURCE_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${SOURCE_REGION}.amazonaws.com"
SOURCE_IMAGE="${SOURCE_REGISTRY}/karpenter-custom:latest"

TARGET_REGIONS=("ap-northeast-1" "eu-west-1" "us-east-1" "us-west-2")

echo "Logging in to source $SOURCE_REGISTRY..."
aws ecr get-login-password --region $SOURCE_REGION | docker login --username AWS --password-stdin $SOURCE_REGISTRY

echo "Pulling source image $SOURCE_IMAGE..."
docker pull --platform linux/amd64 $SOURCE_IMAGE

for REGION in "${TARGET_REGIONS[@]}"; do
    echo "Processing target region: $REGION"
    TARGET_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
    TARGET_IMAGE="${TARGET_REGISTRY}/karpenter-custom:latest"
    
    echo "Logging in to $TARGET_REGISTRY..."
    aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $TARGET_REGISTRY
    
    echo "Tagging image..."
    docker tag $SOURCE_IMAGE $TARGET_IMAGE
    
    echo "Pushing image to $REGION..."
    docker push $TARGET_IMAGE
    echo "Done for $REGION"
done
