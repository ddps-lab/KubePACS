# KubePACS

KubePACS is a Kubernetes-native spot instance provisioning system for building node pools that balance performance, availability, and cost. It uses cloud market signals such as spot price, benchmark performance, and availability scores to choose instance types, then integrates the decision into Karpenter so Kubernetes can provision those nodes through the normal autoscaling workflow.

The project is described in the paper [KubePACS: Kubernetes Cluster Using Performant, Highly Available, and Cost Efficient Spot Instances](https://arxiv.org/abs/2604.24027). A hosted project page is available at [kubepacs.ddps.cloud](https://kubepacs.ddps.cloud/).

## What Is In This Repository

- `KubePACS_with_Karpenter/`: Karpenter fork with the KubePACS scheduler path and Helm chart.
- `charts/`: static Helm repository output, including `index.yaml` and packaged chart archives.
- `IaC/IaC_karpenter_kubepacs/`: Terraform for deploying the EKS/Karpenter/KubePACS environment.
- `figures/`: scripts and data used to regenerate paper figures.
- `api/`: API wrapper for the KubePACS optimizer.
- `frontend/`: project website frontend.

## Install With Helm

This repository is published as a Helm repository at `https://helm.kubepacs.ddps.cloud/charts`. Users can install the chart with:

```sh
helm repo add kubepacs https://helm.kubepacs.ddps.cloud/charts
helm repo update
helm upgrade --install karpenter kubepacs/karpenter \
  --namespace karpenter \
  --create-namespace \
  -f KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter/examples/kubepacs-values.yaml
```

The chart installs Kubernetes resources into an existing EKS cluster. AWS prerequisites still need to exist: an EKS cluster, controller IAM role, node IAM role, tagged subnets/security groups, and an interruption queue if configured.

The default controller image is:

```text
ghcr.io/ddps-lab/kubepacs-karpenter-controller:1.8.1-kubepacs
```

That image is built from `KubePACS_with_Karpenter/karpenter-provider-aws/Dockerfile` and includes:

- the KubePACS-enabled Karpenter controller binary
- `kubepacs_cli.py`
- `aws_coremark_singlecore.csv`
- Python runtime dependencies used by the optimizer

If `settings.kubepacs.enabled=true`, the chart refuses to render with the upstream Karpenter image because that image does not contain KubePACS.

## Publish The Helm Repository

Publishing is handled by `.github/workflows/publish-kubepacs-helm.yaml`.

For public installs, configure GitHub like this:

1. Enable GitHub Pages with deployment from GitHub Actions.
2. Run the `Publish KubePACS Helm Chart` workflow.
3. Make the GHCR package `kubepacs-karpenter-controller` public.

To update the packaged Helm repository locally:

```sh
helm package KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter --destination charts
helm repo index charts --url https://helm.kubepacs.ddps.cloud/charts
```

## Deploy A Full AWS Environment

The Terraform environment under `IaC/IaC_karpenter_kubepacs/` creates the supporting AWS/EKS pieces and installs the local Helm chart.

```sh
cd IaC/IaC_karpenter_kubepacs
terraform init
terraform apply
```

The IaC defaults to the public KubePACS controller image, but the image can be overridden with:

```hcl
controller_image_repository = "ghcr.io/ddps-lab/kubepacs-karpenter-controller"
controller_image_tag        = "1.8.1-kubepacs"
controller_image_digest     = ""
```

## Deploy The Project Website

The frontend under `frontend/` is a static Next.js export deployed to S3 and CloudFront by `.github/workflows/deploy-frontend.yaml`.

On pushes to `main` that change `frontend/**` or the workflow file, GitHub Actions runs:

```sh
npm ci
npm run lint
npm run build
aws s3 sync frontend/out/_next/static s3://kubepacs.ddps.cloud/_next/static --delete
aws s3 sync frontend/out s3://kubepacs.ddps.cloud --delete
aws cloudfront create-invalidation --distribution-id E33W0BVG8FRMS2 --paths "/*"
```

The workflow expects organization-level AWS secrets named `HYU_DDPS_AWS_ID` and `HYU_DDPS_AWS_SECRET`. S3 sets `Content-Type` from file extensions during `aws s3 sync`; the workflow verifies the uploaded HTML, CSS, and JavaScript object metadata before invalidating CloudFront.

## Regenerate Paper Figures

Figure scripts live in `figures/`. They use Python 3.11+ and `uv`.

Install dependencies:

```sh
cd figures
uv sync
```

Regenerate every figure script:

```sh
cd figures
find . -name 'figure_*.py' -print0 | sort -z | while IFS= read -r -d '' script; do
  dir=$(dirname "$script")
  file=$(basename "$script")
  (cd "$dir" && uv run python "$file")
done
```

Regenerate one figure:

```sh
cd figures/figure10_exp_k8s_karpenter
uv run python figure_10.py
```

The scripts overwrite the generated PDFs in each figure directory. Most figures use checked-in result data.

See [figures/README.md](figures/README.md) for the full figure command list.

## Paper

- Project page: [https://kubepacs.ddps.cloud/](https://kubepacs.ddps.cloud/)
- Paper: [https://arxiv.org/abs/2604.24027](https://arxiv.org/abs/2604.24027)
- DOI: [https://doi.org/10.1145/3801927.3810468](https://doi.org/10.1145/3801927.3810468)

Please cite KubePACS as:

```text
Taeyoon Kim, Kyumin Kim, Enrique Molina-Giménez, Pedro García-López,
and Kyungyong Lee. 2026. KubePACS: Kubernetes Cluster Using Performant,
Highly Available, and Cost Efficient Spot Instances. In 27th International
Middleware Conference (Middleware ’26), December 14–18, 2026, Tarragona,
Spain. ACM, New York, NY, USA, 14 pages.
https://doi.org/10.1145/3801927.3810468
```
