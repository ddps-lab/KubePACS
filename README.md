# KubePACS

KubePACS selects Kubernetes spot-instance node pools using performance,
availability, and cost, and integrates its optimizer into Karpenter.

Paper: [KubePACS: Kubernetes Cluster Using Performant, Highly Available, and
Cost Efficient Spot Instances](https://arxiv.org/abs/2604.24027).

## Artifact Evaluation

See the [Artifact Appendix](docs/artifact_appendix.pdf) for an overview of the
artifact, requirements, and evaluation workflows.

The evaluation workflow runs the optimizer with stored inputs and regenerates
Figures 1, 2, and 5-12 and Tables 2-3 on a local machine. It requires no AWS
account, Kubernetes cluster, or cloud deployment.

Requested badges: **Artifacts Available**, **Artifacts Functional**, and
**Results Reproduced**.

The optimizer check varies pod requirements and reports instance recommendations.
The figure and table workflows process the supplied experimental results.

| Component | Purpose | Instructions |
| --- | --- | --- |
| `figures/` | Regenerate Figures 1, 2, and 5-12 and Tables 2-3 | [Figures and Tables](figures/README.md) |
| `optimizer/` | Run ten scenarios across four regions | [Local Optimizer Check](optimizer/README.md) |
| `api/` | Run the optimizer with packaged input | [API](api/README.md) |
| `KubePACS_with_Karpenter/` | Build and deploy the modified autoscaler | [Karpenter](KubePACS_with_Karpenter/README.md) |
| `IaC/IaC_karpenter_kubepacs/` | Provision an AWS/EKS test environment | [Terraform](IaC/IaC_karpenter_kubepacs/README.md) |
| `charts/` | Packaged Helm distribution | [Charts](charts/README.md) |
| `frontend/` | Optional project website | [Website](frontend/README.md) |

Commands start at the repository root unless stated otherwise. Record
`git rev-parse HEAD` with evaluation results. When evaluating a working copy,
also retain any uncommitted artifact files.

## Install uv And Python

Choose the instructions for your operating system. Python is managed by uv
without changing system Python. The commands below follow the
[official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

### Linux

Use Bash or Zsh with Git and curl installed. On Ubuntu or Debian:

```sh
sudo apt-get update
sudo apt-get install -y git curl ca-certificates
```

For other Linux distributions, install Git, curl, and CA certificates with
your distribution's package manager. Then install uv and Python:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.11
```

### macOS

Open Terminal. Run `git --version` first. If macOS prompts you to install
Command Line Tools, complete that installation before continuing.

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.11
```

If you already use Homebrew, `brew install uv` is an alternative to the
installer above. Then run `uv python install 3.11`.

### Windows

Open PowerShell. Install Git using the [Git for Windows installer](https://git-scm.com/downloads/win)
if `git --version` is not available, then reopen PowerShell. Install uv and Python:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$HOME\.local\bin;$env:Path"
uv --version
uv python install 3.11
```

With WinGet, `winget install --id=astral-sh.uv -e` is an alternative to the
uv installer. Reopen PowerShell after installation before running uv.

### Common Commands

If `uv` is not found in a later terminal, reopen it or repeat the PATH command
for your shell. The single-line `git`, `uv sync`, and `uv run` commands below
work with Bash, Zsh, and PowerShell. Use single-line commands in PowerShell
instead of the Bash `\` line continuations shown in some component READMEs.

Installation instructions cover all three operating systems. End-to-end
artifact execution has been verified on Linux x86-64. macOS and native
Windows execution still need platform-specific verification.

## Quick Start: Figures And Tables

Requirements: Python 3.11 and uv. Linux x86-64 is the verified execution platform.
Allow approximately 4 GiB free disk for dependencies, a temporary data copy,
and outputs; this is a planning allowance, not a measured minimum. Supplied
figure data occupy about 1.1 GiB. No GPU or cloud account is needed. Internet
access is required to obtain the repository and install dependencies, not to
generate the results. After the setup above, obtain the repository:

```sh
git clone https://github.com/ddps-lab/KubePACS.git
cd KubePACS
```

```sh
uv sync --locked --project figures --python 3.11
uv run --locked --project figures python figures/reproduce.py
```

Expected outcome: exit code 0 and `PASS: 16 scripts, 24 PDFs`. Generated PDFs,
per-script logs, and `summary.json` are placed under `artifact-results/figures/`.
Reference PDFs are not overwritten. Choose a fresh `--output` directory for
each subsequent run.

See [Figures](figures/README.md) for setup, output checks, individual
commands, input descriptions, and the paper-to-output mapping.

Regenerate Table 2 from stored results with no additional dependencies:

```sh
uv run --locked --project figures python figures/table2_alpha/table_02.py
```

Success is `PASS: Table 2, 240 samples per configuration`. CSV, Markdown,
and LaTeX outputs are written to `artifact-results/table2/`. The command checks
all five values against the paper at four decimal places. See
[Table 2](figures/README.md#table-2) for the inputs and aggregation method.

Generate Table 3 from the recorded workload measurements and prices:

```sh
uv run --locked --project figures python figures/table3_compute/table_03.py
```

Success is `PASS: Table 3`. CSV, Markdown, and LaTeX outputs are written to
`artifact-results/table3/`. See [Table 3](figures/README.md#table-3).

## Local Optimizer Check

Follow the [local optimizer command](optimizer/README.md)
to run the existing optimizer on the supplied price, availability, hardware,
and benchmark inputs. Ten scenarios vary region, pod count, CPU, and memory
across Virginia, Oregon, Ireland, and Tokyo.

```sh
uv sync --locked --project optimizer
uv run --locked --project optimizer python optimizer/check_optimizer.py
```

The script accepts repeated `--case REGION,PODS,VCPU,GIB` arguments for custom
requests and a fresh `--output` directory for each run. Regional CSVs and AZ
mappings are included in `optimizer/data/`.

Success is `PASS: 10 local optimizer scenarios`, ten scenario JSON reports,
and `summary.json` in `artifact-results/optimizer/`. Inspect the selected instance types, zone names,
instance counts, estimated hourly cost, performance score, and pod capacity.
The command checks that each allocation covers the requested pod count and
respects the stored per-candidate availability limits. It also recomputes cost
and capacity from the regional CSV. It reads both the CSV and AZ mapping locally.

## Reproducing Results

Running experiments on AWS requires cloud resources, setup time, and usage
costs. To minimize this burden, the artifact includes stored experimental
results and scripts for regenerating the paper's figures locally. The figure
workflow reads these supplied results, processes the data, and generates PDFs
without an AWS account or a running Kubernetes cluster. Figures 3 and 4 are
architectural illustrations supplied as PPTX sources.
Table 2 is regenerated locally from stored allocation and alpha-sweep results.
Table 3 summarizes recorded workload throughput and instance prices.

Collect the generated PDFs, table files, and figure runner's `summary.json`
from `artifact-results/`. Compare them with the paper and supplied reference
PDFs using the metric definitions in [Figures and Tables](figures/README.md#inputs-and-interpretation).
The figure runner checks successful execution and output presence. Table 2
also checks the reported values at four decimal places.

Inspect the optimizer JSON reports alongside the regenerated figures and tables.

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
