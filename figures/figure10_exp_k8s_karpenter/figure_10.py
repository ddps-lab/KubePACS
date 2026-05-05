#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import ast
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

# === Font settings ===
font_size = 35
font_family = 'Roboto'
plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# ## 1. Load Simulation Data (exp_figure10_24hx2_old)

# In[2]:


# --- Load Simulation data ---
sim_dir = './data/simulation'
all_dfs = []
for csv_file in os.listdir(sim_dir):
    if csv_file.endswith('.csv'):
        df = pd.read_csv(os.path.join(sim_dir, csv_file))
        all_dfs.append(df)
sim_df = pd.concat(all_dfs, ignore_index=True)

# Parse dict columns
def safe_eval(s):
    if not isinstance(s, str):
        return s
    s = s.replace('nan', 'np.nan').replace('inf', 'np.inf').replace('-np.nan', 'np.nan').replace('-inf', '-np.inf')
    try:
        return eval(s, {"np": np, "__builtins__": {}})
    except:
        return {}

sim_df['karpenter'] = sim_df['karpenter'].apply(safe_eval)
sim_df['kubecaps'] = sim_df['kubecaps'].apply(safe_eval)

karpenter_cols = sim_df['karpenter'].apply(pd.Series).add_prefix('karpenter_')
kubecaps_cols = sim_df['kubecaps'].apply(pd.Series).add_prefix('kubecaps_')
sim_df = pd.concat([sim_df, karpenter_cols, kubecaps_cols], axis=1)

# Load instance vCPU info
aws_coremark_df = pd.read_csv('./data/aws_coremark_singlecore.csv')
instance_vcpu_map = dict(zip(aws_coremark_df['InstanceType'], aws_coremark_df['vCPU']))

# Classify load
def classify_load_sim(row):
    pods, cpu, mem = row['pods'], row['cpu'], row['memory']
    total_cpu = pods * cpu
    total_mem = pods * mem
    if total_cpu <= 200 and total_mem <= 200:
        return 'Low'
    elif total_cpu <= 800 and total_mem <= 4000:
        return 'Medium'
    else:
        return 'High'

sim_df['load_category'] = sim_df.apply(classify_load_sim, axis=1)

# Filter valid rows
sim_df = sim_df[sim_df['karpenter_excess_pod'].fillna(0).astype(float) >= 0]

print(f"Simulation data: {len(sim_df)} rows")
print(sim_df['load_category'].value_counts())

# ## 2. Load Real-world Data (exp_rebuttal_realworld)

# In[3]:


# --- Load Real-world data ---
rw_df = pd.read_csv('./data/realworld/metrics_summary_ct.csv')
rw_df['load_category'] = rw_df['LoadCategory']

# Also load integrated results for vCPU calculation
rw_integrated = pd.read_csv('./data/realworld/integrated_results_ct.csv')

# Compute per-scenario average vCPU for each strategy
# Group by (BaseScenario, Strategy) and compute weighted average vCPU (weighted by Count)
rw_integrated['weighted_vcpu'] = rw_integrated['vCPU'] * rw_integrated['Count']
rw_vcpu_agg = rw_integrated.groupby(['BaseScenario', 'Strategy']).agg(
    total_weighted_vcpu=('weighted_vcpu', 'sum'),
    total_count=('Count', 'sum')
).reset_index()
rw_vcpu_agg['avg_vcpu'] = rw_vcpu_agg['total_weighted_vcpu'] / rw_vcpu_agg['total_count']

# Merge load_category from rw_df
scenario_load = rw_df[['BaseScenario', 'load_category']].drop_duplicates()
rw_vcpu_agg = rw_vcpu_agg.merge(scenario_load, on='BaseScenario', how='left')

print(f"Real-world data: {len(rw_df)} rows")
print(rw_df['load_category'].value_counts())
rw_df.head()

# ## 3. Extract per-metric data from both sources

# In[4]:


# --- Helper functions for Simulation availability ---
def get_total_type_count(entry):
    nodepool = entry if isinstance(entry, list) else entry.get('nodepool') if isinstance(entry, dict) else None
    parsed = ast.literal_eval(nodepool) if isinstance(nodepool, str) else nodepool if isinstance(nodepool, list) else []
    return len([item for item in parsed if isinstance(item, dict)])

def extract_vcpus_from_nodepool(entry):
    nodepool = entry if isinstance(entry, list) else entry.get('nodepool') if isinstance(entry, dict) else None
    parsed = ast.literal_eval(nodepool) if isinstance(nodepool, str) else nodepool if isinstance(nodepool, list) else []
    vcpus = []
    for node in parsed:
        if isinstance(node, dict) and 'instance_type' in node:
            vcpu = instance_vcpu_map.get(node['instance_type'], None)
            if vcpu is not None:
                vcpus.append(int(vcpu))
    return vcpus

def flatten(lst):
    result = []
    for item in lst:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result

# --- Build unified per-load data ---
load_order = ['Low', 'Medium', 'High']

combined_data = {}
for load_name in load_order:
    sim_load = sim_df[sim_df['load_category'] == load_name]
    rw_load = rw_df[rw_df['load_category'] == load_name]

    # === Cost ===
    sim_kubecaps_cost = sim_load['kubecaps_cost'].dropna()
    sim_karpenter_cost = sim_load['karpenter_cost'].dropna()
    rw_kubecaps_cost = rw_load['Cost_KubePACS'].dropna()
    rw_karpenter_cost = rw_load['Cost_Baseline'].dropna()
    kubecaps_cost = pd.concat([sim_kubecaps_cost, rw_kubecaps_cost], ignore_index=True)
    karpenter_cost = pd.concat([sim_karpenter_cost, rw_karpenter_cost], ignore_index=True)

    # === Performance (per-pod) ===
    sim_kubecaps_perf = (sim_load['kubecaps_performance'] / sim_load['kubecaps_actual_pods']).dropna()
    sim_karpenter_perf = (sim_load['karpenter_performance'] / sim_load['karpenter_assignable_pod']).dropna()
    rw_kubecaps_perf = (rw_load['Perf_KubePACS'] / rw_load['Parallelism']).dropna()
    rw_karpenter_perf = (rw_load['Perf_Baseline'] / rw_load['Parallelism']).dropna()
    kubecaps_perf = pd.concat([sim_kubecaps_perf, rw_kubecaps_perf], ignore_index=True)
    karpenter_perf = pd.concat([sim_karpenter_perf, rw_karpenter_perf], ignore_index=True)

    # === Availability (# of instance types) ===
    sim_kubecaps_avail = sim_load['kubecaps'].apply(get_total_type_count)
    sim_karpenter_avail = sim_load['karpenter'].apply(get_total_type_count)
    rw_kubecaps_avail = rw_load['Nodes_KubePACS']
    rw_karpenter_avail = rw_load['Nodes_Baseline']
    kubecaps_avail = pd.concat([sim_kubecaps_avail, rw_kubecaps_avail], ignore_index=True)
    karpenter_avail = pd.concat([sim_karpenter_avail, rw_karpenter_avail], ignore_index=True)

    # === Average vCPU per instance (combined from both sources) ===
    # Simulation: per-row average vCPU from nodepool
    sim_kubecaps_vcpu_series = sim_load['kubecaps'].apply(extract_vcpus_from_nodepool).apply(
        lambda x: np.mean(x) if x else np.nan)
    sim_karpenter_vcpu_series = sim_load['karpenter'].apply(extract_vcpus_from_nodepool).apply(
        lambda x: np.mean(x) if x else np.nan)

    # Real-world: per-scenario average vCPU from integrated_results_ct
    rw_vcpu_load = rw_vcpu_agg[rw_vcpu_agg['load_category'] == load_name]
    rw_kubecaps_vcpu_series = rw_vcpu_load[rw_vcpu_load['Strategy'] == 'kubepacs']['avg_vcpu']
    rw_karpenter_vcpu_series = rw_vcpu_load[rw_vcpu_load['Strategy'] == 'baseline']['avg_vcpu']

    # Combine and take overall mean
    kubecaps_vcpu_all = pd.concat([sim_kubecaps_vcpu_series, rw_kubecaps_vcpu_series], ignore_index=True)
    karpenter_vcpu_all = pd.concat([sim_karpenter_vcpu_series, rw_karpenter_vcpu_series], ignore_index=True)
    kubecaps_vcpu_mean = kubecaps_vcpu_all.mean()
    karpenter_vcpu_mean = karpenter_vcpu_all.mean()

    combined_data[load_name] = {
        'kubecaps_cost': kubecaps_cost,
        'karpenter_cost': karpenter_cost,
        'kubecaps_perf': kubecaps_perf,
        'karpenter_perf': karpenter_perf,
        'kubecaps_avail': kubecaps_avail,
        'karpenter_avail': karpenter_avail,
        'kubecaps_vcpu_mean': kubecaps_vcpu_mean,
        'karpenter_vcpu_mean': karpenter_vcpu_mean,
    }

for load_name in load_order:
    d = combined_data[load_name]
    print(f"\n{load_name}:")
    print(f"  KubePACS cost={len(d['kubecaps_cost'])}, Karpenter cost={len(d['karpenter_cost'])}")
    print(f"  KubePACS avg vCPU={d['kubecaps_vcpu_mean']:.1f}, Karpenter avg vCPU={d['karpenter_vcpu_mean']:.1f}")

# ## 4. Plot: Cost, Performance, Availability (Combined)

# In[13]:


# === K formatter ===
def kilo_formatter(x, pos):
    return f"{int(x/1e3)}K" if x >= 1e3 else f"{int(x)}"

# === Spacing ===
base_gap = 1.9
intra_gap = 0.85

metrics = ['Cost', 'Performance', 'Availability']
output_dir = './'

for metric_name in metrics:
    fig, ax = plt.subplots(figsize=(10, 5))

    all_kubecaps_data = []
    all_karpenter_data = []
    all_kubecaps_vcpu_means = []
    all_karpenter_vcpu_means = []

    for i, load_name in enumerate(load_order):
        d = combined_data[load_name]

        if metric_name == 'Cost':
            kubecaps_data = d['kubecaps_cost']
            karpenter_data = d['karpenter_cost']
            ax.set_ylim(0, 42.5)
            # ax.set_yticks([0, 5, 10, 15, 20, 25, 30, 35, 40])
            ax.set_yticks([0, 10, 20, 30, 40])
            ax.set_ylabel('Cost ($)', fontsize=font_size, labelpad=5)

        elif metric_name == 'Performance':
            kubecaps_data = d['kubecaps_perf']
            karpenter_data = d['karpenter_perf']
            ax.set_ylim(5000, 45000)
            ax.set_yticks([10000, 20000, 30000, 40000])
            ax.yaxis.set_major_formatter(FuncFormatter(kilo_formatter))
            ax.set_ylabel('Benchmark Score', fontsize=font_size, labelpad=5)

        elif metric_name == 'Availability':
            kubecaps_data = d['kubecaps_avail']
            karpenter_data = d['karpenter_avail']
            all_kubecaps_vcpu_means.append(d['kubecaps_vcpu_mean'])
            all_karpenter_vcpu_means.append(d['karpenter_vcpu_mean'])
            ax.set_ylim(-0.5, 50.5)
            # ax.set_yticks([0, 5, 10, 15, 20, 25, 30, 35, 40, 45])
            ax.set_yticks([0, 10, 20, 30, 40, 50])
            ax.set_ylabel('# of Instance Types', fontsize=font_size, labelpad=5)

        all_kubecaps_data.append(kubecaps_data)
        all_karpenter_data.append(karpenter_data)

    # Print summary
    mean_kube = np.mean([np.mean(d) for d in all_kubecaps_data])
    mean_karp = np.mean([np.mean(d) for d in all_karpenter_data])
    print(f"\n[{metric_name}] KubePACS mean: {mean_kube:.4f}, Karpenter mean: {mean_karp:.4f}")
    if metric_name == 'Cost':
        print(f"  Cost reduction: {((mean_karp - mean_kube) / mean_karp) * 100:.2f}%")
    else:
        print(f"  Improvement: {((mean_kube - mean_karp) / mean_karp) * 100:.2f}%")

    # Positions
    positions_kubecaps = [i * base_gap for i in range(len(load_order))]
    positions_karpenter = [i * base_gap + intra_gap for i in range(len(load_order))]
    xtick_positions = [i * base_gap + intra_gap / 2 for i in range(len(load_order))]

    # Boxplot
    bp1 = ax.boxplot(
        [d for pair in zip(all_kubecaps_data, all_karpenter_data) for d in pair],
        positions=sorted(positions_kubecaps + positions_karpenter),
        widths=0.7,
        patch_artist=True,
        manage_ticks=False
    )

    # Colors and hatching
    for i, patch in enumerate(bp1['boxes']):
        if i % 2 == 0:
            patch.set_facecolor('orange')
            patch.set_hatch('/')
        else:
            patch.set_facecolor('skyblue')
            patch.set_hatch('\\')
        patch.set_edgecolor('black')
        patch.set_linewidth(1.5)

    for median in bp1['medians']:
        median.set(color='red', linewidth=1.5)

    for l_type in ['whiskers', 'caps', 'fliers']:
        for artist in bp1[l_type]:
            artist.set_color('black')
            artist.set_linewidth(1.5)

    # X-axis
    ax.tick_params(axis='y', labelsize=font_size)
    ax.set_xticks(xtick_positions)
    ax.set_xticklabels(load_order, fontsize=font_size)

    # Availability: vCPU star markers
    if metric_name == 'Availability':
        offset = 1.2
        compensate = 3.5
        for i in range(len(load_order)):
            ax.plot(positions_kubecaps[i], all_kubecaps_vcpu_means[i] / compensate,
                    marker='*', color='red', markersize=25,
                    markeredgecolor='black', markeredgewidth=1.5, zorder=100)
            ax.plot(positions_karpenter[i], all_karpenter_vcpu_means[i] / compensate,
                    marker='*', color='red', markersize=25,
                    markeredgecolor='black', markeredgewidth=1.5, zorder=100)

            ax.text(positions_kubecaps[i], all_kubecaps_vcpu_means[i] / compensate + offset,
                    f"{all_kubecaps_vcpu_means[i]:.1f}", fontsize=font_size - 4,
                    va='bottom', ha='center',
                    bbox=dict(boxstyle='round,pad=0.1', facecolor='white', alpha=0.5, edgecolor='gray'))
            ax.text(positions_karpenter[i], all_karpenter_vcpu_means[i] / compensate + offset,
                    f"{all_karpenter_vcpu_means[i]:.1f}", fontsize=font_size - 4,
                    va='bottom', ha='center',
                    bbox=dict(boxstyle='round,pad=0.1', facecolor='white', alpha=0.5, edgecolor='gray'))
            ax.set_ylim([0, 52])

    # Legend
    legend_elements = [
        Patch(facecolor='orange', edgecolor='black', label='KubePACS', hatch='/'),
        Patch(facecolor='skyblue', edgecolor='black', label='Karpenter', hatch='\\')
    ]
    if metric_name == 'Availability':
        legend_elements.append(Line2D([0], [0], marker='*', color='w', label='Average number\nof vCPUs per\nInstance',
                                      markerfacecolor='red', markersize=25,
                                      markeredgecolor='black', markeredgewidth=1.5, linestyle='None'))
    if metric_name == 'Cost':
        ax.legend(handles=legend_elements, fontsize=font_size - 3, loc='upper left',
                  handlelength=1.5, handletextpad=0.2, edgecolor='black', ncol=1)
    elif metric_name == 'Availability':
        ax.legend(handles=[legend_elements[-1]], fontsize=font_size - 10, loc='upper left',
                  handlelength=1, handletextpad=0.2, edgecolor='black', ncol=1)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"karpenter_vs_kubecaps_{metric_name.lower()}_cr.pdf"), bbox_inches='tight')
    plt.show()
    plt.close(fig)

print("\nAll figures saved.")

# In[ ]:



