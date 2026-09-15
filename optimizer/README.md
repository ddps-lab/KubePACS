# Local Optimizer Evaluation

Run ten scenarios across Virginia (`us-east-1`), Oregon (`us-west-2`), Ireland
(`eu-west-1`), and Tokyo (`ap-northeast-1`) using stored inputs.

## Installation And Execution

Follow the [uv and Python setup](../README.md#install-uv-and-python).
Commands start at the repository root and use Python 3.11. Installation
instructions cover Linux, macOS, and Windows. Execution has been verified
on Linux x86-64. The independent locked environment includes PuLP and CBC.
Allow several minutes for the default suite. Dependency installation needs
internet access, while optimization reads local files.

```sh
uv sync --locked --project optimizer
uv run --locked --project optimizer python optimizer/check_optimizer.py
```

These single-line commands also use PowerShell-compatible syntax. Check CBC
availability after installation on a new platform:

```sh
uv run --locked --project optimizer python -c "import pulp; print(pulp.listSolvers(onlyAvailable=True))"
```

The list should include `PULP_CBC_CMD`. The scenario run then checks actual
solver execution. macOS and Windows runs have not yet been verified here.

Success is `PASS: 10 local optimizer scenarios`, ten `scenario-NN.json` files,
and `summary.json` under `artifact-results/optimizer/`. Each scenario is also
printed to the terminal. Choose a fresh `--output` directory for another run.

## Scenarios

The default inputs are defined in `scenarios.json`. CPU and memory are per pod.

| Scenario | Region | Pods | vCPU | GiB |
| --- | --- | ---: | ---: | ---: |
| 1 | us-east-1 | 10 | 1 | 2 |
| 2 | us-west-2 | 10 | 1 | 2 |
| 3 | eu-west-1 | 10 | 1 | 2 |
| 4 | ap-northeast-1 | 10 | 1 | 2 |
| 5 | us-east-1 | 50 | 2 | 4 |
| 6 | us-west-2 | 50 | 2 | 4 |
| 7 | eu-west-1 | 50 | 2 | 4 |
| 8 | ap-northeast-1 | 50 | 2 | 4 |
| 9 | us-east-1 | 100 | 4 | 2 |
| 10 | us-west-2 | 100 | 1 | 8 |

Supply repeated `--case REGION,PODS,VCPU,GIB` arguments to replace the suite:

```sh
uv run --locked --project optimizer python optimizer/check_optimizer.py \
  --case eu-west-1,20,0.5,1 --case ap-northeast-1,60,2,8 \
  --output artifact-results/optimizer-custom
```

PowerShell equivalent:

```powershell
uv run --locked --project optimizer python optimizer/check_optimizer.py --case eu-west-1,20,0.5,1 --case ap-northeast-1,60,2,8 --output artifact-results/optimizer-custom
```

## Inputs And Output

`data/` contains one merged CSV and one AZ mapping JSON for each supported
region. The CSVs preserve the existing cached optimizer inputs, including
instance types, AZ IDs, CPU, memory, prices, availability limits, and CoreMark.
The runner calls the unchanged `getGoldenNodepool` implementation in
`figures/common/library/alpha_ILP_library_v4.py`. No figure environment is used.

The original Virginia AZ mapping is preserved. The other three mappings were
captured from AWS metadata during artifact preparation. Zone names are
account-specific labels. The CSVs retain the original AZ IDs, prices, and
availability observations. The runner requires complete local mappings and
does not download missing inputs.

Each report records its request, input paths, elapsed time, and `pass` flag.
Successful reports include `nodepool_config` (instance types, AZ names, counts,
and `T3`), `cost` (estimated hourly cost), `performance` (aggregate score),
`alpha` (selected weight), and `actual_pods` (total pod capacity).

Validation checks recommendation membership in the regional input, unique
instance/AZ pairs, positive counts within stored availability limits, and
sufficient pod capacity. It independently recomputes capacity and cost from
the CSV and compares them with the optimizer output. Capacity follows the
optimizer's per-instance CPU and memory model.

Compare scenarios 1-4 and 5-8 to examine regional differences under the same
requirements. Scenarios 9-10 exercise CPU-heavy and memory-heavy requests.
Failed scenarios retain an `error` field. Remaining requests still run, and
the process exits with code 1 if any scenario fails. Invalid arguments or
missing input files stop execution before optimization.

```sh
uv run --locked --project optimizer python -m unittest discover -s optimizer -p 'test_*.py'
```
