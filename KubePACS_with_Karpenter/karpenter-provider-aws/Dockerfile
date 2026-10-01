# KubePACS-enabled Karpenter AWS provider controller.
# Multi-arch: build with `docker buildx build --platform linux/amd64,linux/arm64 ...`.
# The build context must be KubePACS_with_Karpenter/ because the provider uses the sibling core module.
FROM --platform=$BUILDPLATFORM golang:1.26 AS builder

ARG TARGETOS=linux
ARG TARGETARCH=amd64

WORKDIR /src

# Copy the entire project to handle relative paths in go.mod
COPY karpenter-core/ karpenter-core/
COPY karpenter-provider-aws/ karpenter-provider-aws/

WORKDIR /src/karpenter-provider-aws

# Download dependencies
# This will now work because ../karpenter-core exists
RUN go mod download

# Build (cross-compiled for the target platform)
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -o controller ./cmd/controller

# Use a Python base image
FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/ddps-lab/KubePACS"
LABEL org.opencontainers.image.description="KubePACS-enabled Karpenter AWS provider controller"
LABEL org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /

# Install pinned solver dependencies (PuLP bundles CBC for linux amd64 and arm64)
COPY karpenter-provider-aws/kubepacs-requirements.txt /tmp/kubepacs-requirements.txt
RUN pip install --no-cache-dir -r /tmp/kubepacs-requirements.txt && rm /tmp/kubepacs-requirements.txt

# Copy the binary
COPY --from=builder /src/karpenter-provider-aws/controller .

# Copy the Python script and CSV
COPY karpenter-core/pkg/controllers/provisioning/scheduling/kubepacs_cli.py /usr/local/bin/kubepacs_cli.py
COPY karpenter-core/pkg/controllers/provisioning/scheduling/aws_coremark_singlecore.csv /usr/local/bin/aws_coremark_singlecore.csv

ENTRYPOINT ["/controller"]
