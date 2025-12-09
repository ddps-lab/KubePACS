#!/bin/bash
set -e

# Configuration
# This should match your Terraform variable 'cluster_name'
CLUSTER_NAME="kubepacs-t1-k8s-cluster" 
REGION="ap-northeast-2"
NAMESPACE="karpenter"
DEPLOYMENT_NAME="karpenter"
# This matches the repo in build_and_push.sh
IMAGE_REPO="786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom"
# Default to v20 as per build_and_push.sh, but allow override
IMAGE_TAG="${1:-v30}"

echo "==============================================="
echo " Deploying Karpenter Custom Image: $IMAGE_TAG"
echo "==============================================="

# 1. Update Kubeconfig
echo "[Step 1] Updating kubeconfig for cluster: $CLUSTER_NAME..."
aws eks update-kubeconfig --region $REGION --name $CLUSTER_NAME

# 2. Update Image
echo "[Step 2] Updating Deployment image..."
# 'controller' is the standard container name for Karpenter
kubectl set image deployment/$DEPLOYMENT_NAME -n $NAMESPACE controller=$IMAGE_REPO:$IMAGE_TAG

# 3. Restart Deployment
echo "[Step 3] Restarting Karpenter Deployment..."
kubectl rollout restart deployment/$DEPLOYMENT_NAME -n $NAMESPACE

# 4. Wait for Rollout
echo "[Step 4] Waiting for rollout to complete..."
kubectl rollout status deployment/$DEPLOYMENT_NAME -n $NAMESPACE

# 5. Check Logs
echo "[Step 5] Fetching recent logs..."
# Using --tail to just show recent startup logs, not stream indefinitely by default unless asked
kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=karpenter --tail=20

echo "==============================================="
echo " Deployment Complete!"
echo " check logs with: kubectl logs -f -n $NAMESPACE -l app.kubernetes.io/name=karpenter"
echo "==============================================="
