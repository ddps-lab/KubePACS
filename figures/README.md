# Paper Figures

This directory contains stored experimental results, plotting scripts, and
reference PDFs. To avoid the cost and setup effort of running AWS experiments,
the scripts regenerate the figures locally from the supplied data.
All commands below start at the repository root.

## Environment

Use Python 3.11 and uv with the supplied `uv.lock`:

```sh
uv sync --locked --project figures
```

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
