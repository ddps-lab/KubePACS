# Optimizer And Profiling Utilities

The local optimizer check complements the [figure workflow](../../README.md).
It runs the optimizer on stored inputs with different pod requirements.

## Local Optimizer Check

Complete the [uv setup](../../../README.md#install-uv-and-python) first.
Run this command from the repository root. It uses the locked figure
environment with PuLP 2.9.0 (including CBC on Linux x86-64) and requests 2.32.5.
The first invocation installs these additional dependencies.

```sh
uv run --locked --project figures --with PuLP==2.9.0 --with requests==2.32.5 \
  python figures/common/library/check_optimizer.py
```

Success is exit code 0 and `PASS: 3 local optimizer scenarios`. The command
prints three recommendations and writes `scenario-01.json` through
`scenario-03.json` and `summary.json` under `artifact-results/optimizer/`.
For a subsequent run, choose a fresh `--output` directory. Allow several
minutes for the three default scenarios: 10 pods at 1 vCPU/2 GiB, 50 pods at
2 vCPU/4 GiB, and 100 pods at 1 vCPU/8 GiB per pod.

Supply repeated `--case PODS,VCPU,GIB` arguments to replace the defaults:

```sh
uv run --locked --project figures --with PuLP==2.9.0 --with requests==2.32.5 \
  python figures/common/library/check_optimizer.py \
  --case 20,0.5,1 --case 60,2,8 --case 120,4,16 \
  --output artifact-results/optimizer-custom
```

Each report contains the request and a `pass` flag. Failed scenarios contain
an `error` field, and the script continues with the remaining requests before
exiting with code 1. Invalid command arguments or missing input files stop
execution before optimization. `summary.json` collects all scenario reports
and identifies the input files.

`nodepool_config` lists
recommended instance types, cached availability-zone names, instance counts,
and the stored `T3` availability limit. `actual_pods` is the allocation's total
pod capacity under the optimizer's CPU and memory model. The checks require
enough capacity for the request and counts within the stored availability limits.
`cost` is the estimated hourly allocation cost from the supplied prices,
`performance` is the aggregate performance score, and `alpha` is the selected
cost-performance weight. Compare these fields across the three scenarios.

## Stored Inputs

`alpha_ILP_library_v4.py` provides optimizer functions. Its merged input CSVs
contain instance type, AZ ID, vCPU, memory, availability metrics, prices, and
CoreMark. Six preserved `merged_coremark_spotdata_260221_*.csv` files are
included for inspecting/reusing the historical optimizer inputs. They are not
the Figure 1 price inputs and do not contain all newer instance families.

`getGoldenNodepool(file_path, ...)` reads a merged CSV and loads
`us-east-1_az_mapping.json` from its working directory. The command above
changes to the library directory so both inputs are read locally. The cached
zone names reflect the original experiment account. Region must match the
supplied CSV and mapping. Both files are tracked in Git and included when
cloning the repository. The check script requires both files before invoking
the optimizer, so a missing cache produces an error instead of a live lookup.

## Profiling Utilities

`profile_runner.py` downloads live price/metadata inputs and performs repeated
optimizer runs across regions, writing timestamped merged inputs and profiling
reports into its working directory. It is not a replay command for the stored
profiling measurements. Do not run it to regenerate the figures, and do not
treat new timings as exact reproductions of historical timings.

The [API workflow](../../../api/README.md) documents the separate Lambda
handler interface. The local check above invokes the optimizer directly.
