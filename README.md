# KubePACS

KubePACS selects Kubernetes spot-instance node pools using performance,
availability, and cost, and integrates its optimizer into Karpenter.

Paper: [KubePACS: Kubernetes Cluster Using Performant, Highly Available, and
Cost Efficient Spot Instances](https://arxiv.org/abs/2604.24027).

## Artifact Evaluation

Requested Middleware 2026 badges: **Artifacts Available**, **Artifacts
Functional**, and **Results Reproduced**. These are evaluation requests, not
awarded badges. The submission abstract must request the same badges, following
the [call for artifacts](https://middleware-conf.github.io/2026/calls/call-for-artifacts/).

Start with figure regeneration: it reprocesses the supplied experimental data
without AWS credentials. API and EKS workflows are separate functional checks.

| Component | Purpose | Instructions |
| --- | --- | --- |
| `figures/` | Regenerate Figures 1, 2, and 5-12; compare reference PDFs | [Figures](figures/README.md) |
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

For reference-image comparison, install Roboto and Poppler (`pdftoppm`):

```sh
uv run --locked --project figures python figures/reproduce.py \
  --compare --output artifact-results/figures-comparison
```

See [Figures](figures/README.md) for setup, comparison criteria, individual
commands, input descriptions, and the paper-to-output mapping.

## Evaluation Scope

The figure workflow verifies that supplied data and processing scripts produce
the reported visual results. It does not rerun the historical cloud experiments
that produced the CSVs. Figures 3 and 4 are architectural illustrations supplied
as PPTX sources.

The API workflow checks an optimizer response. The EKS workflow checks node
provisioning integration, with logs needed to distinguish KubePACS execution
from fallback to ordinary Karpenter. The website is not required for evaluation.

A complete, verified end-to-end rerun recipe for every historical simulation,
graph analytics, I/O, and fault injection experiment is not yet included.
Table 2 and numerical claims outside the generated figures do not yet have
dedicated automated acceptance checks. These limits apply to the requested
Results Reproduced evaluation; plotting stored results must not be reported
as freshly reproducing every experiment.

## Verification Status

Figure scripts have been executed with network access blocked. The documented
reproduction command also passed in a fresh locked Python 3.11 environment:
16 scripts and 24 reference comparisons, with 20 PDFs pixel-identical and
four within the documented rasterization tolerance.
The API has a local AWS-backed smoke test. Helm lint/render checks are
configuration checks, not proof of a working image or cluster deployment.
Terraform validation and the optional website lint/static build also passed.

Full EKS deployment, fault injection, and end-to-end experiment resource,
runtime, and cost measurements still require a deployment validation run.
Cloud resources are billable until removed; deployment READMEs include cleanup.
No cloud deployment is necessary for plotting.

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
