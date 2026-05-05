# Regenerating KubePACS Figures

This directory contains the scripts and checked-in data used to regenerate the paper figures for KubePACS.

## Setup

Install dependencies with `uv`:

```sh
cd figures
uv sync
```

The scripts should be run from their own figure directories because many of them use relative paths for input data and output PDFs.

## Regenerate All Figures

```sh
cd figures
find . -name 'figure_*.py' -print0 | sort -z | while IFS= read -r -d '' script; do
  dir=$(dirname "$script")
  file=$(basename "$script")
  (cd "$dir" && uv run python "$file")
done
```

## Regenerate Individual Figures

```sh
cd figures/figure1_cmp_coremark_price
uv run python figure_01a.py
uv run python figure_01b.py
uv run python figure_01c.py
uv run python figure_01d.py
```

```sh
cd figures/figure2_cmp_single_multi_sps
uv run python figure_02.py
```

```sh
cd figures/figure5_cmp_baseline_simulation
uv run python figure_05a.py
uv run python figure_05b.py
uv run python figure_05c.py
```

```sh
cd figures/figure6_search_best_alpha/aws
uv run python figure_06.py
```

```sh
cd figures/figure6_search_best_alpha/azure
uv run python figure_06.py
```

```sh
cd figures/figure7_simulation_variousalpha
uv run python figure_07.py
```

```sh
cd figures/figure8_special_instance
uv run python figure_08.py
```

```sh
cd figures/figure9_ddd
uv run python figure_09.py
```

```sh
cd figures/figure10_exp_k8s_karpenter
uv run python figure_10.py
```

```sh
cd figures/figure11_graph_analytics
uv run python figure_11.py
```

```sh
cd figures/figure12_fis
uv run python figure_12.py
```

Generated PDFs are written next to each script. Some scripts fetch current cloud pricing data, so regenerated PDFs may not be byte-for-byte identical to the checked-in versions.
