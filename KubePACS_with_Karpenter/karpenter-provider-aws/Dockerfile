FROM golang:1.25 AS builder

WORKDIR /src

# Copy the entire project to handle relative paths in go.mod
ARG CACHEBUST=1
RUN echo "Cache bust: $CACHEBUST"
COPY karpenter-core/ karpenter-core/
COPY karpenter-provider-aws/ karpenter-provider-aws/

WORKDIR /src/karpenter-provider-aws

# Download dependencies
# This will now work because ../karpenter-core exists
RUN go mod download

# Build
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -a -o controller ./cmd/controller

# Use a Python base image
FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/ddps-lab/KubePACS"
LABEL org.opencontainers.image.description="KubePACS-enabled Karpenter AWS provider controller"
LABEL org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /

# Install dependencies
RUN pip install pandas pulp requests boto3 numpy

# Copy the binary
COPY --from=builder /src/karpenter-provider-aws/controller .

# Copy the Python script and CSV
# Note: We are copying from the build context (host), not the builder stage, 
# because we want to ensure we get the files even if they weren't used in the go build.
# But since we are running from root context, we can copy directly.
COPY karpenter-core/pkg/controllers/provisioning/scheduling/kubepacs_cli.py /usr/local/bin/kubepacs_cli.py
COPY karpenter-core/pkg/controllers/provisioning/scheduling/aws_coremark_singlecore.csv /usr/local/bin/aws_coremark_singlecore.csv

ENTRYPOINT ["/controller"]
