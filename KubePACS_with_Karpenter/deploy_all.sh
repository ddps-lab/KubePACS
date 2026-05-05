#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PREFIX="${PREFIX:-kubepacs-e1}"
CLUSTER_NAME="${CLUSTER_NAME:-${PREFIX}-k8s-cluster}"
REGION="${REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-${PROFILE:-default}}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NAMESPACE="${NAMESPACE:-karpenter}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-karpenter}"
CONTAINER_NAME="${CONTAINER_NAME:-controller}"

export PREFIX CLUSTER_NAME REGION PROFILE IMAGE_TAG NAMESPACE DEPLOYMENT_NAME CONTAINER_NAME

echo "=== Building and pushing KubePACS Karpenter image ==="
"${SCRIPT_DIR}/karpenter-provider-aws/build_and_push.sh"

echo "=== Deploying KubePACS Karpenter image ==="
"${SCRIPT_DIR}/karpenter-provider-aws/deploy_and_verify.sh" "${IMAGE_TAG}"

echo "Deployment complete: ${CLUSTER_NAME} -> ${IMAGE_TAG}"
