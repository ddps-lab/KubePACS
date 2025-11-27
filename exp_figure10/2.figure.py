import os
from matplotlib.ticker import FuncFormatter, ScalarFormatter
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import ast
import numpy as np

# --- 설정 ---
result_dir = 'region/integrated'
font_label = 29
font_tick = 29
font_legend = 26
font_family = 'SUIT'
plt.rcParams['font.family'] = font_family

# --- 분류 함수 ---
def classify_load(row):
    pods, cpu, mem = row['pods'], row['cpu'], row['memory']
    total_cpu = pods * cpu
    total_mem = pods * mem
    if total_cpu <= 200 and total_mem <= 200:
        return 'Low Load'
    elif total_cpu <= 800 and total_mem <= 4000:
        return 'Medium Load'
    else:
        return 'High Load'

# --- Availability 계산 ---
def get_total_nodes(entry):
    nodepool = entry if isinstance(entry, list) else entry.get('nodepool') if isinstance(entry, dict) else None
    parsed = ast.literal_eval(nodepool) if isinstance(nodepool, str) else nodepool if isinstance(nodepool, list) else []
    # print(item.get('num_instances', 0) for item in parsed)
    # print(list(item.get('num_instances', 0) for item in parsed if isinstance(item, dict)))
    return list(item.get('num_instances', 0) for item in parsed if isinstance(item, dict))

# --- UsagePerT3 계산 ---
def get_usage_per_t3(entry):
    nodepool = entry if isinstance(entry, list) else entry.get('nodepool') if isinstance(entry, dict) else None
    parsed = ast.literal_eval(nodepool) if isinstance(nodepool, str) else nodepool if isinstance(nodepool, list) else []
    usage_sum, count = 0, 0
    for item in parsed:
        if isinstance(item, dict) and 'T3' in item and item['T3'] > 0:
            usage_sum += item.get('num_instances', 0) / item['T3']
            count += 1
    return usage_sum / count if count else np.nan

# --- 데이터 로딩 및 전처리 ---
all_dfs = []
for csv_file in os.listdir(result_dir):
    if csv_file.endswith('.csv'):
        df = pd.read_csv(os.path.join(result_dir, csv_file))
        all_dfs.append(df)
if not all_dfs:
    raise ValueError('No CSV files found in the directory.')
result_df = pd.concat(all_dfs, ignore_index=True)
print(result_df.head())

def safe_eval(s):
    if not isinstance(s, str):
        return s
    s = s.replace('nan', 'np.nan').replace('inf', 'np.inf').replace('-np.nan', 'np.nan').replace('-inf', '-np.inf')
    try:
        return eval(s, {"np": np, "__builtins__": {}})
    except:
        return {}

if isinstance(result_df['karpenter'].iloc[0], str):
    result_df['karpenter'] = result_df['karpenter'].apply(safe_eval)
    result_df['kubecaps'] = result_df['kubecaps'].apply(safe_eval)

karpenter_df = result_df['karpenter'].apply(pd.Series).add_prefix('karpenter_')
kubecaps_df = result_df['kubecaps'].apply(pd.Series).add_prefix('kubecaps_')
result_df = pd.concat([result_df, karpenter_df, kubecaps_df], axis=1)

result_df['load_category'] = result_df.apply(classify_load, axis=1)
filtered_df = result_df[result_df['karpenter_excess_pod'].fillna(0).astype(float) >= 0]

# --- 각 부하별 처리 ---
load_categories = {
    'Low': filtered_df[filtered_df['load_category'] == 'Low Load'],
    'Medium': filtered_df[filtered_df['load_category'] == 'Medium Load'],
    'High': filtered_df[filtered_df['load_category'] == 'High Load'],
}

def flatten(lst):
    result = []
    for item in lst:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result

for load_name, load_df in load_categories.items():
    fig, ax = plt.subplots(figsize=(10, 6))
    karpenter_cost = load_df['karpenter_cost']
    kubecaps_cost = load_df['kubecaps_cost']
    karpenter_performance = load_df['karpenter_performance'] / load_df['karpenter_assignable_pod']
    kubecaps_performance = load_df['kubecaps_performance'] / load_df['kubecaps_actual_pods']
    karpenter_eff = load_df['karpenter_efficiency'] * load_df['pods']
    kubecaps_eff = load_df['kubecaps_efficiency'] * load_df['pods']
    karp_avail = load_df['karpenter'].apply(get_total_nodes)
    kube_avail = load_df['kubecaps'].apply(get_total_nodes)

    karp_avail_flat = flatten(list(karp_avail))
    kube_avail_flat = flatten(list(kube_avail))

    # --- 첫 번째 축: Cost ---
    bp1 = ax.boxplot([karpenter_cost, kubecaps_cost], positions=[1, 2], widths=0.4, patch_artist=True)
    for median in bp1['medians']:
        median.set(color='red', linewidth=1.5)
    for patch, color in zip(bp1['boxes'], ['skyblue', 'orange']):
        patch.set_facecolor(color)

    ax.set_ylim(-0.5, 35)
    ax.set_yticks([0, 5, 10, 15, 20, 25, 30])
    ax.tick_params(axis='y', labelsize=font_tick)

    if load_name == 'Low':
        ax.set_ylabel('Cost ($)', fontsize=font_label)
        ax.set_yticklabels([0, 5, 10, 15, 20, 25, 30])
    else:
        ax.set_yticklabels([])
        ax.tick_params(axis='y', length=0)
    
    # --- 두 번째 축: Efficiency ---
    # ax2 = ax.twinx()
    # bp2 = ax2.boxplot([karpenter_eff, kubecaps_eff], positions=[3, 4], widths=0.4, patch_artist=True)
    # for patch, color in zip(bp2['boxes'], ['skyblue', 'orange']):
    #     patch.set_facecolor(color)
    # if load_name == 'High':    
    #     ax2.set_ylabel('Efficiency', fontsize=font_label)

    # ax2.set_ylim(0, 10e6)
    # ax2.set_yticks([0, 2e6, 4e6, 6e6, 8e6])
    # def millions_formatter(x, pos):
    #     return f"{int(x/1e6)}M" if x >= 1e6 else f"{int(x)}"

    # ax2.yaxis.set_major_formatter(FuncFormatter(millions_formatter))
    # ax2.tick_params(axis='y', labelsize=font_tick)
    # if load_name != 'High':
    #     ax2.set_yticklabels([])   

    # --- 두 번째 축: Performance ---
    ax2 = ax.twinx()
    bp2 = ax2.boxplot([karpenter_performance, kubecaps_performance], positions=[3, 4], widths=0.4, patch_artist=True)
    for median in bp2['medians']:
        median.set(color='red', linewidth=1.5)
    for patch, color in zip(bp2['boxes'], ['skyblue', 'orange']):
        patch.set_facecolor(color)
    if load_name == 'High':    
        ax2.set_ylabel('CoreMark per Pod', fontsize=font_label)

    ax2.set_ylim(-0.5, 42000)
    ax2.set_yticks([0, 10000, 20000, 30000, 40000])
    def kilo_formatter(x, pos):
        return f"{int(x/1e3)}K" if x >= 1e3 else f"{int(x)}"

    ax2.yaxis.set_major_formatter(FuncFormatter(kilo_formatter))
    ax2.tick_params(axis='y', labelsize=font_tick)
    if load_name != 'High':
        ax2.set_yticklabels([])
        ax2.tick_params(axis='y', length=0)

    # --- 세 번째 축: Availability + UsagePerT3 ---
    ax3 = ax.twinx()

    ax3.tick_params(axis='y', labelsize=font_tick)
    ax3.set_ylim(-0.5, 21)
    ax3.set_yticks([0, 5, 10, 15, 20])

    if load_name == 'High':
        ax3.spines['right'].set_position(('outward', 120))
    else:
        ax3.set_yticklabels([])
        ax3.tick_params(axis='y', length=0)
        ax3.spines['right'].set_visible(False)

    bp3 = ax3.boxplot([karp_avail_flat, kube_avail_flat], positions=[5, 6], widths=0.4, patch_artist=True)
    for median in bp3['medians']:
        median.set(color='red', linewidth=1.5)
    for patch, color in zip(bp3['boxes'], ['skyblue', 'orange']):
        patch.set_facecolor(color)
        patch.set_edgecolor('black')
        patch.set_linewidth(1.5)
        
    for l in ['whiskers', 'caps', 'fliers']:
        for artist in bp3[l]:
            artist.set_color('black')
            artist.set_linewidth(1.5)
    if load_name == 'High':
        ax3.set_ylabel('Number of Nodes', fontsize=font_label)

    # --- 별 마커 ---
    karp_mean = load_df['karpenter'].apply(get_usage_per_t3).mean()
    kube_mean = load_df['kubecaps'].apply(get_usage_per_t3).mean()

    offset = 1.8
    ax3.plot(5, karp_mean, marker='*', color='red', markersize=24,
         markeredgecolor='black', markeredgewidth=2, zorder=100)
    ax3.plot(6, kube_mean, marker='*', color='red', markersize=24,
            markeredgecolor='black', markeredgewidth=2, zorder=100)

    tx3_1 = ax3.text(
        5, karp_mean + offset, f"×{karp_mean:.2f}",
        fontsize=font_tick-3, va='center', ha='center',
        bbox=dict(boxstyle='round,pad=0.15', facecolor='white', alpha=0.3, edgecolor='gray')
    )
    bbox_patch = tx3_1.get_bbox_patch()
    bbox_patch.set_y(9)

    ax3.text(
        6, kube_mean + offset, f"×{kube_mean:.2f}",
        fontsize=font_tick-3, va='center', ha='center', linespacing=0.5,
        bbox=dict(boxstyle='round,pad=0.15', facecolor='white', alpha=0.3, edgecolor='gray')
    )

    # --- 중앙 점선 ---
    ax.axvline(x=2.5, color='gray', linestyle='--', linewidth=2, alpha=0.7)
    ax2.axvline(x=4.5, color='gray', linestyle='--', linewidth=2, alpha=0.7)

    # --- 라벨 ---
    ax.set_xticks([1, 2, 3, 4, 5, 6])
    ax.set_xticklabels([])
    ax.text(1.5, -0.05, 'Cost', fontsize=font_label, ha='center', va='top', transform=ax.get_xaxis_transform())
    ax.text(3.5, -0.05, 'Performance', fontsize=font_label, ha='center', va='top', transform=ax.get_xaxis_transform())
    ax.text(5.5, -0.05, 'Availability', fontsize=font_label, ha='center', va='top', transform=ax.get_xaxis_transform())

    # --- 범례 ---
    if load_name == 'Low':
        legend_elements = [
                            Line2D([0], [0], color='skyblue', lw=9, label='Karpenter'),
                            Line2D([0], [0], color='orange', lw=9, label='KubeCAPS'),
                            Line2D([0], [0], marker='*', color='red', label='Over T3 Ratio',
                                markerfacecolor='red', markersize=27, markeredgecolor='black',
                                markeredgewidth=2, linestyle='None')
                            ]

        ax.legend(handles=legend_elements, fontsize=font_legend, loc='upper left', handlelength=1)

    plt.tight_layout()
    plt.savefig(os.path.join(result_dir, f"karpenter_vs_kubecaps_{load_name.lower()}.pdf"), bbox_inches='tight')
    plt.close(fig)
