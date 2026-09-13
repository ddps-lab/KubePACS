# KubePACS With Karpenter

This directory contains the modified Karpenter core, AWS provider, Python
optimizer, and Helm chart. Commands start at the repository root.

## Scope And Prerequisites

Figure generation does not need this deployment. This workflow tests live
provisioning integration and creates billable AWS resources. Use a dedicated
test cluster/account, Docker, AWS CLI, kubectl, and Helm 3. The controller image
targets Linux AMD64.

An existing EKS cluster needs controller and node IAM roles, tagged discovery
subnets/security groups, and an interruption queue when enabled. Alternatively,
use the [Terraform environment](../IaC/IaC_karpenter_kubepacs/README.md).
Do not manage the same Helm release with both Terraform and manual Helm.

The controller's `kubepacs_cli.py` accepts a local JSON or gzip JSON snapshot
through `KUBEPACS_SPOT_DATA_PATH` (or `--spot-data-path` for direct CLI use).
Package or mount the input at an absolute path in the controller container;
the solver runs from `/tmp`. The API's `data/latest_aws.json` can be reused.
Build an image containing this CLI revision; the published 1.8.1-kubepacs
image does not automatically gain changes made in the checkout.

Without a local path the CLI uses the live CloudFront endpoint with a
30-second request timeout. An explicitly configured missing/invalid file
fails instead of falling back to live input. Validate the optimizer path:
a ready controller or ready workload alone is insufficient because solver
failure can fall back to ordinary Karpenter.

## Build And Inspect

Build locally without publishing or deploying:

```sh
docker build --platform linux/amd64 -t kubepacs-controller:artifact \
  -f KubePACS_with_Karpenter/karpenter-provider-aws/Dockerfile \
  KubePACS_with_Karpenter
helm lint KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter
```

The build context must include both fork directories because the provider
uses the sibling core module. The Dockerfile installs unpinned Python
dependencies; record the image digest and resolved dependencies for evaluation.
A successful Helm lint is not a container build or deployment test.

`karpenter-provider-aws/build_and_push.sh` builds and pushes images, including
a `latest` tag, and can create an ECR repository. `deploy_all.sh` also deploys.
Neither is a build-only command.

## Configure And Deploy

Copy the example:

```sh
cp KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter/examples/kubepacs-values.yaml /tmp/kubepacs-values.yaml
```

Replace every placeholder with the target cluster's values. Review controller
replicas and scheduling: chart defaults require two separate non-Karpenter
nodes for two controller replicas. A single bootstrap-node test cluster needs
`replicas: 1`. Review the NodePool's CPU limit (default 1000) against your
budget. Set `controller.image.repository` and an immutable
`controller.image.digest` to an image accessible from the cluster. The default
public tag is a convenience, not proof of correspondence to submitted source.
Record the resolved AMI as well; the example uses `al2023@latest`.

Render first, then install only into the intended test cluster:

```sh
kubectl config current-context
helm template karpenter KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter \
  --namespace karpenter -f /tmp/kubepacs-values.yaml > /tmp/kubepacs-rendered.yaml
helm upgrade --install karpenter KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter \
  --namespace karpenter --create-namespace -f /tmp/kubepacs-values.yaml --wait --timeout 10m
```

Review the rendered YAML before installing. The chart adds the strategy
annotation to opted-in NodePools at this location:

```yaml
spec:
  template:
    metadata:
      annotations:
        kubepacs.io/strategy: kubepacs
```

## Functional Acceptance

For a Helm-managed dedicated test cluster, enable the optional five-pod
workload (each pod requests 1 CPU and 1 GiB):

```sh
helm upgrade karpenter KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter \
  --namespace karpenter -f /tmp/kubepacs-values.yaml --set kubepacsVerification.enabled=true
kubectl rollout status deployment/karpenter -n karpenter --timeout=5m
kubectl get pods -n karpenter -o wide
kubectl get nodepools,ec2nodeclasses,nodeclaims
kubectl logs -n karpenter deployment/karpenter --all-pods=true --since=10m
kubectl get nodes -L node.kubernetes.io/instance-type,topology.kubernetes.io/zone,karpenter.sh/capacity-type
```

Retain logs, rendered values, image digest, NodeClaims, node labels, and pod
events. Success requires all of the following:

- Eligible pending pods trigger the opted-in NodePool and Python solver.
- Logs show `Calling Python solver` and a usable `Python solver output`,
  without `python solver failed, falling back to default` for that request.
- New NodeClaims and nodes agree with the resulting allocation, and the test
  pods become Ready.

If all pods fit existing nodes, the optimizer was not tested. Workload
readiness after fallback is not KubePACS success. These checks establish
integration behavior, not the paper's availability/performance improvements.
End-to-end cluster validation and measured runtime/cost remain pending.

## Cleanup

Disable the Helm-managed test workload using the same values:

```sh
helm upgrade karpenter KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter \
  --namespace karpenter -f /tmp/kubepacs-values.yaml --set kubepacsVerification.enabled=false
```

In the dedicated test cluster, remove the test NodePool while the controller
is still running and verify its NodeClaims and EC2 instances terminate before
uninstalling the controller. Do not remove a shared/production NodePool.
Then uninstall a manually managed release with
`helm uninstall karpenter -n karpenter`. Helm may retain CRDs; it does not
remove an independently provisioned EKS cluster, IAM roles, queues, or VPC.
For Terraform-managed resources, use the Terraform cleanup procedure instead.
