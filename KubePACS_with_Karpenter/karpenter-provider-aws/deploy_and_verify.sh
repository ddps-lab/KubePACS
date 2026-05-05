#!/bin/bash
set -euo pipefail

PREFIX="${PREFIX:-kubepacs-e1}"
CLUSTER_NAME="${CLUSTER_NAME:-${PREFIX}-k8s-cluster}"
REGION="${REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-${PROFILE:-default}}"
IMAGE_TAG="${1:-${IMAGE_TAG:-latest}}"
ECR_REPOSITORY_NAME="${ECR_REPOSITORY_NAME:-karpenter-custom}"
NAMESPACE="${NAMESPACE:-karpenter}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-karpenter}"
CONTAINER_NAME="${CONTAINER_NAME:-controller}"

if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --profile "${PROFILE}")"
fi

IMAGE_REPO="${ECR_REPO:-${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}}"

echo "Deploying ${IMAGE_REPO}:${IMAGE_TAG} to ${CLUSTER_NAME} (${REGION})"

aws eks update-kubeconfig \
  --region "${REGION}" \
  --name "${CLUSTER_NAME}" \
  --profile "${PROFILE}"

kubectl set image "deployment/${DEPLOYMENT_NAME}" \
  -n "${NAMESPACE}" \
  "${CONTAINER_NAME}=${IMAGE_REPO}:${IMAGE_TAG}"

kubectl rollout status "deployment/${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --timeout=180s
kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/name=karpenter --tail=50
