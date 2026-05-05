#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_CONTEXT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REGION="${REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-${PROFILE:-default}}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ECR_REPOSITORY_NAME="${ECR_REPOSITORY_NAME:-karpenter-custom}"
PLATFORM="${PLATFORM:-linux/amd64}"

if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --profile "${PROFILE}")"
fi

ECR_REGISTRY="${ECR_REGISTRY:-${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com}"
ECR_REPO="${ECR_REPO:-${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}}"

echo "Logging in to ${ECR_REPO}..."
aws ecr get-login-password --region "${REGION}" --profile "${PROFILE}" |
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

if ! aws ecr describe-repositories \
  --repository-names "${ECR_REPOSITORY_NAME}" \
  --region "${REGION}" \
  --profile "${PROFILE}" >/dev/null 2>&1; then
  aws ecr create-repository \
    --repository-name "${ECR_REPOSITORY_NAME}" \
    --image-scanning-configuration scanOnPush=true \
    --region "${REGION}" \
    --profile "${PROFILE}" >/dev/null
fi

if ! docker buildx inspect karpenter-builder >/dev/null 2>&1; then
  docker buildx create --name karpenter-builder --use
fi

echo "Building and pushing ${ECR_REPO}:${IMAGE_TAG}..."
docker buildx build \
  --platform "${PLATFORM}" \
  --build-arg "CACHEBUST=$(date +%s)" \
  -f "${BUILD_CONTEXT}/karpenter-provider-aws/Dockerfile" \
  -t "${ECR_REPO}:${IMAGE_TAG}" \
  -t "${ECR_REPO}:latest" \
  --push \
  "${BUILD_CONTEXT}"

echo "Done: ${ECR_REPO}:${IMAGE_TAG}"
