# AWS Test Environment

This Terraform configuration creates a dedicated EKS environment and installs
the local KubePACS Helm chart. It is not required to regenerate figures.
Commands below start at the repository root.

## Requirements And Safety

Use Terraform compatible with the pinned modules, AWS CLI, Helm 3, kubectl,
and an AWS profile authorized to manage EKS, EC2/VPC, IAM, ECR, SQS, and related
resources. Provider constraints are in `versions.tf`; EKS module 20.37.2 and
VPC module 5.21.0 are pinned. Preserve the provider lock file and Terraform
state. Do not apply from another evaluator's existing state directory.

Review these source defaults before any apply:

| Setting | Current configuration |
| --- | --- |
| Region/profile | `us-east-1` / `default` |
| Cluster name | `${prefix}-k8s-cluster`, prefix defaults to `kubepacs-e1` |
| EKS version | 1.33 |
| Bootstrap nodes | Bottlerocket x86_64, `t3.medium`, desired/min 1, max 2 |
| Network | Public subnets, public EKS endpoint |
| Controller | One replica, namespace/release `karpenter` |
| Test NodePool | Spot AMD64, default name `default` |
| Test workload | Disabled by default |
| ECR | Fixed name `karpenter-custom`; force deletion enabled |

The worker security group currently allows all inbound IPv4 traffic, and the
additional controller policy uses wildcard resources. These are permissive
experiment settings, not production defaults. Restrict them for your approved
test environment before applying. A unique prefix does not isolate the
fixed-name ECR repository. Review existing resources and naming conflicts.

Cloud provisioning and measured runtime/cost have not been validated for this
submission. Verify regional EKS version availability, service quotas, instance
availability, and a spending limit before use. EKS, EC2, storage, public IPv4,
and other services remain billable until removed. The controller's live input
dependency is described in [Karpenter](../../KubePACS_with_Karpenter/README.md);
successful Terraform apply alone is not KubePACS functional success.

## Configure And Review

Set your own profile, region, and unused prefix. Terraform does not load a
shell `.env` file automatically.

```sh
export TF_VAR_awscli_profile=default
export TF_VAR_region=us-east-1
export TF_VAR_prefix=kubepacs-artifact
aws sts get-caller-identity --profile "$TF_VAR_awscli_profile"
terraform -chdir=IaC/IaC_karpenter_kubepacs init
terraform -chdir=IaC/IaC_karpenter_kubepacs validate
terraform -chdir=IaC/IaC_karpenter_kubepacs plan -out=tfplan
```

Review the account identity and complete plan, including IAM, ingress,
instance counts, image, and AMI selection. Set
`TF_VAR_controller_image_digest` to the digest being evaluated; the default
tag and `al2023@latest` AMI selector are mutable. Use a fresh dedicated checkout
and state for a new environment, not an existing deployment's state.

Only after reviewing the plan, create resources:

```sh
terraform -chdir=IaC/IaC_karpenter_kubepacs apply tfplan
aws eks update-kubeconfig \
  --name "${TF_VAR_prefix}-k8s-cluster" \
  --region "$TF_VAR_region" --profile "$TF_VAR_awscli_profile"
kubectl config current-context
kubectl get nodes
kubectl get pods -n karpenter
kubectl get nodepools,ec2nodeclasses
```

If installation fails, inspect Terraform output, controller pod events, IAM,
and subnet discovery tags. Keep state even after partial failure so created
resources can be cleaned up.

## Exercise The Optimizer

Enable the Terraform-managed verification workload using a reviewed plan:

```sh
export TF_VAR_kubepacs_verification_enabled=true
terraform -chdir=IaC/IaC_karpenter_kubepacs plan -out=verify.tfplan
terraform -chdir=IaC/IaC_karpenter_kubepacs apply verify.tfplan
```

Apply the [functional acceptance criteria](../../KubePACS_with_Karpenter/README.md#functional-acceptance):
pending pods must trigger a successful solver invocation, new NodeClaims must
correspond to the allocation, and pods must become Ready without fallback.
Use that document's kubectl inspection commands, but do not manually upgrade
a Terraform-owned Helm release.

Retain source revision, provider versions, reviewed configuration, image
digest, logs, NodeClaims, and observed runtime/resource use. Redact account
details before sharing; never publish credentials or Terraform state.
This smoke workload does not rerun the paper's benchmarks or fault injection.

## Cleanup

First disable the test workload while the controller is still running:

```sh
export TF_VAR_kubepacs_verification_enabled=false
terraform -chdir=IaC/IaC_karpenter_kubepacs plan -out=stop.tfplan
terraform -chdir=IaC/IaC_karpenter_kubepacs apply stop.tfplan
```

In this dedicated test cluster, remove the test NodePool and wait for its
NodeClaims and EC2 instances to terminate before removing the controller.
Do not use this procedure on a shared NodePool. Check for workload-created
load balancers and volumes, which may not be in Terraform state.

Then review and apply the destruction plan:

```sh
terraform -chdir=IaC/IaC_karpenter_kubepacs plan -destroy -out=destroy.tfplan
terraform -chdir=IaC/IaC_karpenter_kubepacs apply destroy.tfplan
terraform -chdir=IaC/IaC_karpenter_kubepacs state list
```

ECR force deletion also removes its images. An empty state is necessary but
not sufficient: verify in AWS that the test cluster, instances, volumes,
load balancers, and other billable test resources are gone. Keep state and
logs until this check is complete.
