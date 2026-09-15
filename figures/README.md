# Paper Figures And Tables

This directory contains stored experimental results, plotting scripts, and
reference PDFs. To avoid the cost and setup effort of running AWS experiments,
the scripts regenerate the figures locally from the supplied data.
Tables 2 and 3 also have local generation commands described below.
All commands below start at the repository root.
The [local optimizer check](../optimizer/README.md)
also exercises instance selection with different pod requirements.

## Environment

Follow the [uv and Python installation](../README.md#install-uv-and-python)
instructions, then use Python 3.11 with the supplied `uv.lock`:

```sh
uv sync --locked --project figures --python 3.11
```

The root README provides Linux, macOS, and Windows installation commands.
In PowerShell, enter multi-line Bash examples as one line without the `\`.

The workflow has been checked on Linux. Allow about 4 GiB free disk for
dependencies and the temporary copy. No GPU or AWS credentials are needed.
Dependency installation needs internet access; execution uses local files.

## Run And Check All Figures

```sh
uv run --locked --project figures python figures/reproduce.py \
  --output artifact-results/figures
```

The output directory must not exist and must be outside `figures/`.
The runner executes 16 scripts in a temporary copy, captures stdout/stderr,
and collects 24 expected PDFs without modifying source/reference files.
Each script has a 180-second timeout. Allow several minutes on a workstation;
the actual durations are recorded in `summary.json`.

Success is exit code 0 and `PASS: 16 scripts, 24 PDFs`. Check:

- `summary.json`: each script has exit code 0 and each PDF has `pass: true`.
- Output subdirectories contain PDFs and one `.log` per executed script.

These checks verify execution and output presence, not numerical agreement
with the paper. Inspect plots and metric definitions alongside the paper.

## Table 2

```sh
uv run --locked --project figures python figures/table2_alpha/table_02.py --output artifact-results/table2
```

This command uses only the Python standard library. Choose a new output
directory outside `figures/`; no AWS access or experiment execution is needed.

Inputs are the 12 runs of 20 scenarios in `figure6_search_best_alpha/aws/data/`:
`golden_section_summary.csv`, `greedy_summary.csv`, and
`specific_result/result_<pods>_<cpu>_<mem>.csv`. The supplemental
`table2_alpha/data/alpha1.csv` contains the alpha=1 measurements extracted from
the original experiment's sweep CSVs. The existing Figure 6 inputs are unchanged.

For each run and scenario, the script computes
`E_Total = performance / (cost * actual_pods)`, divides each configuration's
value by the GSS value for that same run and scenario, and takes the arithmetic
mean of these 240 ratios. It does not take a ratio of aggregate means.

Success is exit code 0 and `PASS: Table 2, 240 samples per configuration`.
Missing or duplicate samples, invalid metrics, and disagreement with the
paper at four decimal places fail the command.

| Configuration | Normalized E_Total |
| --- | ---: |
| Greedy | 0.8616 |
| alpha=0 | 0.9563 |
| alpha=0.5 | 0.0006 |
| alpha=1 | 0.0001 |
| Ours (GSS) | 1.0000 |

GSS is the normalization reference. Lower values indicate lower efficiency
relative to GSS under the same input conditions.

Outputs: `table2.csv` (unrounded means and sample counts), `table2.md` and
`table2.tex` (four-decimal presentation), and `table2_details.csv` (1,200
per-configuration, per-run, per-scenario normalized values).

## Table 3

```sh
uv run --locked --project figures python figures/table3_compute/table_03.py --output artifact-results/table3
```

The script includes the recorded compilation and video-encoding throughput
and instance prices. It generates `table3.csv`, `table3.md`, and `table3.tex`,
including the Best Case row. Only the Python standard library is needed;
no AWS access is required. Choose a new output directory outside `figures/`.
Success is exit code 0 and `PASS: Table 3`.

## Individual Commands And Outputs

Direct invocations overwrite PDFs in their figure directory. Use the runner
to preserve references. The directory names below are relative to `figures/`.

| Figure | Directory | Script(s) | Expected PDFs |
| --- | --- | --- | --- |
| 1 | `figure1_cmp_coremark_price` | `figure_01a.py` through `figure_01d.py` | `m-family-gen-coremark-price.pdf`, `intel-coremark-price.pdf`, `m6-family-coremark-price.pdf`, `cpu-vendor-coremark-price.pdf`, `cmp-coremark-price-legend.pdf` |
| 2 | `figure2_cmp_single_multi_sps` | `figure_02.py` | `multiple-nodes-sps-real-availability.pdf` |
| 3-4 | `figure3_oveall_arch`, `figure4_kubepacs_k8s` | PPTX sources | Illustrations; open/export using presentation software |
| 5 | `figure5_cmp_baseline_simulation` | `figure_05a.py`, `figure_05b.py`, `figure_05c.py` | `comparison-related-work-benchmark-score.pdf`, `compare-type-usage.pdf`, `comparison-msa.pdf`, `comparison-legend.pdf` |
| 6 AWS | `figure6_search_best_alpha/aws` | `figure_06.py` | `distribution-of-alphas-to-workloads.pdf`, `distribution-of-alphas-to-workloads-short.pdf` |
| 6 Azure | `figure6_search_best_alpha/azure` | `figure_06.py` | `distribution-of-alphas-to-workloads-azure.pdf`, `distribution-of-alphas-to-workloads-azure-short.pdf` |
| 7 | `figure7_simulation_variousalpha` | `figure_07.py` | `impact-of-alpha-spacing.pdf` |
| 8 | `figure8_special_instance` | `figure_08.py` | `network-disk-intensive-workload-stack.pdf` |
| 9 | `figure9_ddd` | `figure_09.py` | `t3-values-to-successful-requests-count.pdf` |
| 10 | `figure10_exp_k8s_karpenter` | `figure_10.py` | `karpenter_vs_kubecaps_availability_cr.pdf`, `karpenter_vs_kubecaps_cost_cr.pdf`, `karpenter_vs_kubecaps_performance_cr.pdf` |
| 11 | `figure11_graph_analytics` | `figure_11.py` | `graph-analytics.pdf` |
| 12 | `figure12_fis` | `figure_12.py` | `fis-cost-comparison.pdf`, `fis-coremark-comparison.pdf`, `fis-recovery-comparison.pdf` |

For example, from the repository root:

```sh
(cd figures/figure10_exp_k8s_karpenter && MPLBACKEND=Agg uv run --locked python figure_10.py)
(cd figures/figure12_fis && MPLBACKEND=Agg uv run --locked python figure_12.py)
```

Use the same pattern for each directory and script in the table.

## Inputs And Interpretation

| Figure | Inputs | What to inspect |
| --- | --- | --- |
| 1 | Local compressed price CSVs and shared CoreMark CSV | Benchmark and price-per-core distributions |
| 2 | Provisioning CSV and cached AZ mapping | Fulfilled requests for single/multi-node SPS cohorts |
| 5 | Stored baseline simulation summaries | Efficiency and node allocation distributions |
| 6 | Stored GSS and alpha sweeps for AWS/Azure | Efficiency versus alpha |
| 7 | Stored tolerance experiment summaries | Solver time versus normalized efficiency |
| 8 | Stored workload-preference summaries | Selected instance categories |
| 9 | Targets and recorded spot requests | T3 versus request fulfillment |
| 10 | Simulation and real-world CSVs | Cluster cost, performance, and allocation metrics |
| 11 | Graph analytics timing CSVs | Execution-time distributions |
| 12 | FIS results, price CSV, shared CoreMark CSV | Before/after node metrics and recovery duration |

Figure 12 pools per-node hourly reference prices using the minimum across AZs
for each type; this is not actual billed cluster cost. Its performance plot
uses the mean lookup CoreMark per experiment, and recovery duration comes
from the experiment log. It does not inject faults or remeasure workloads.

Short/full Figure 6 variants and legends are included in the 24 outputs.
The [optimizer/profiling utilities](common/library/README.md) are not called
by the plotting workflow and have separate AWS/dependency requirements.

## Troubleshooting And Cleanup

- Missing CSV: preserve the repository layout rather than copying a script alone.
- Nonzero exit: inspect the corresponding log; missing PDFs fail the run.
- Existing output directory: choose a new path to retain earlier evidence.

Remove only the chosen output run directory after inspection to reclaim space.
Temporary input copies are removed automatically.
