FROM golang:1.25 as builder

WORKDIR /src

# Copy the entire project to handle relative paths in go.mod
COPY karpenter-core/ karpenter-core/
COPY karpenter-fork/ karpenter-fork/

WORKDIR /src/karpenter-fork

# Download dependencies
# This will now work because ../karpenter-core exists
RUN go mod download

# Build
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -a -o controller cmd/controller/main.go

# Use a Python base image
FROM python:3.13-slim

WORKDIR /

# Install dependencies
RUN pip install pandas pulp requests boto3 numpy

# Copy the binary
COPY --from=builder /src/karpenter-fork/controller .

# Copy the Python script and CSV
# Note: We are copying from the build context (host), not the builder stage, 
# because we want to ensure we get the files even if they weren't used in the go build.
# But since we are running from root context, we can copy directly.
COPY karpenter-core/pkg/controllers/provisioning/scheduling/kubecaps_cli.py /usr/local/bin/kubecaps_cli.py
COPY karpenter-core/pkg/controllers/provisioning/scheduling/aws_coremark_singlecore.csv /usr/local/bin/aws_coremark_singlecore.csv

ENTRYPOINT ["/controller"]
