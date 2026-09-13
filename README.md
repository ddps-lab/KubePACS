# KubePACS

KubePACS selects Kubernetes spot-instance node pools using performance,
availability, and cost, and integrates its optimizer into Karpenter.

Paper: [KubePACS: Kubernetes Cluster Using Performant, Highly Available, and
Cost Efficient Spot Instances](https://arxiv.org/abs/2604.24027).

## Artifact Evaluation

Start with figure regeneration: it reprocesses the supplied experimental data
without AWS credentials. API and EKS workflows are separate functional checks.

| Component | Purpose | Instructions |
| --- | --- | --- |
| `figures/` | Regenerate Figures 1, 2, and 5-12 | [Figures](figures/README.md) |
| `api/` | Run the optimizer with packaged input | [API](api/README.md) |
| `KubePACS_with_Karpenter/` | Build and deploy the modified autoscaler | [Karpenter](KubePACS_with_Karpenter/README.md) |
| `IaC/IaC_karpenter_kubepacs/` | Provision an AWS/EKS test environment | [Terraform](IaC/IaC_karpenter_kubepacs/README.md) |
| `charts/` | Packaged Helm distribution | [Charts](charts/README.md) |
| `frontend/` | Optional project website | [Website](frontend/README.md) |

Commands start at the repository root unless stated otherwise. Record
`git rev-parse HEAD` with evaluation results. When evaluating a working copy,
also retain any uncommitted artifact files.

## Quick Start: Figures

Requirements: Python 3.11, uv, and a Linux environment for the tested workflow.
Allow approximately 4 GiB free disk for dependencies, a temporary data copy,
and outputs; this is a planning allowance, not a measured minimum. Supplied
figure data occupy about 1.1 GiB. No GPU or cloud account is needed. Internet
access is required to install dependencies, not to generate the figures.

```sh
uv sync --locked --project figures
uv run --locked --project figures python figures/reproduce.py
```

Expected outcome: exit code 0 and `PASS: 16 scripts, 24 PDFs`. Generated PDFs,
per-script logs, and `summary.json` are placed under `artifact-results/figures/`.
Reference PDFs are not overwritten. Choose a fresh `--output` directory for
each subsequent run.

See [Figures](figures/README.md) for setup, output checks, individual
commands, input descriptions, and the paper-to-output mapping.

## Reproducing Results

Running experiments on AWS requires cloud resources, setup time, and usage
costs. To minimize this burden, the artifact includes stored experimental
results and scripts for regenerating the paper's figures locally. The figure
workflow reads these supplied results, processes the data, and generates PDFs
without an AWS account or a running Kubernetes cluster. Figures 3 and 4 are
architectural illustrations supplied as PPTX sources.

The API workflow checks an optimizer response. The EKS workflow checks
**KubePACS** node provisioning, with logs needed to distinguish KubePACS execution
from fallback to ordinary Karpenter. The website is not required for evaluation.

## Verification Status

Figure scripts have been executed with network access blocked. The documented
reproduction command also passed in a fresh locked Python 3.11 environment:
16 scripts generated all 24 expected PDFs.
The API has a local AWS-backed smoke test. Helm lint/render checks are
configuration checks, not proof of a working image or cluster deployment.
Terraform validation and the optional website lint/static build also passed.

AWS deployment is optional for figure generation. When using the deployment
workflow, cloud resources are billable until removed; the deployment READMEs
include cleanup instructions.

## Distribution And Citation

Source: [GitHub](https://github.com/ddps-lab/KubePACS).
The [website](https://kubepacs.ddps.cloud/) and hosted Helm repository are
conveniences; evaluate supplied source and data. Record an immutable submission
revision and archive URL in the final submission. Karpenter license files are
retained in both fork directories; they do not establish a license for all
other code and datasets.

```text
Taeyoon Kim, Kyumin Kim, Enrique Molina-Giménez, Pedro García-López,
and Kyungyong Lee. 2026. KubePACS: Kubernetes Cluster Using Performant,
Highly Available, and Cost Efficient Spot Instances.
Middleware '26, December 14-18, 2026, Tarragona, Spain. 14 pages.
https://doi.org/10.1145/3801927.3810468
```
