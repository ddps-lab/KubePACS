# KubePACS with Karpenter

This directory packages a KubePACS-enabled Karpenter controller and Helm chart.

## What Helm Installs

The chart can install:

- Karpenter controller using the KubePACS custom image
- KubePACS scheduler settings as controller environment variables
- Optional `EC2NodeClass`
- Optional KubePACS-enabled `NodePool`
- Optional smoke-test workload

Helm installs Kubernetes resources into an existing EKS cluster. AWS-side prerequisites still need to exist: an EKS cluster, controller IAM role, node IAM role, tagged subnets/security groups, and an interruption queue if used. By default the chart uses the public KubePACS controller image at `ghcr.io/ddps-lab/kubepacs-karpenter-controller:1.8.1-kubepacs`.

## Build and Push a Custom Controller Image

```bash
cd KubePACS_with_Karpenter
REGION=us-east-1 AWS_PROFILE=default IMAGE_TAG=latest ./deploy_all.sh
```

For build-only:

```bash
REGION=us-east-1 AWS_PROFILE=default IMAGE_TAG=latest \
  ./karpenter-provider-aws/build_and_push.sh
```

## Install with Helm

Copy and edit the example values file:

```bash
cp karpenter-provider-aws/charts/karpenter/examples/kubepacs-values.yaml /tmp/kubepacs-values.yaml
```

Then install:

```bash
helm upgrade --install karpenter ./karpenter-provider-aws/charts/karpenter \
  --namespace karpenter \
  --create-namespace \
  -f /tmp/kubepacs-values.yaml
```

The NodePool opts in to KubePACS with:

```yaml
metadata:
  annotations:
    kubepacs.io/strategy: kubepacs
```
