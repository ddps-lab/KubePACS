#!/usr/bin/env python
# coding: utf-8

# # FIS Experiment Analysis: Recovery Duration & Efficiency
# 
# This notebook analyzes FIS (Fault Injection Simulator) experiment results:
# 1. **Recovery Duration**: Time to recover from spot interruption
# 2. **Total Efficiency ($E_{Total}$)**: $E_{PerfCost} \times E_{OverPods}$
# 3. **Before/After Comparison**: E_Total before interrupt vs after recovery
# 
# ### Efficiency Metrics (from paper)
# - $E_{PerfCost} = \sum_{i}\frac{BS_i \cdot x_i}{SP_i}$ (Performance-Cost Efficiency)
# - $E_{OverPods} = \frac{Req_{pod}}{\sum_{i}Pod_i \cdot x_i}$ (Excess Pod Allocation Efficiency)
# - $E_{Total} = E_{PerfCost} \times E_{OverPods}$

# In[1]:


import os
import json
import ast
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import boto3

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

# Paths
BASE_DIR = os.path.dirname(os.path.abspath('__file__'))
FIS_RESULTS_CSV = os.path.join(BASE_DIR, 'data/fis_results.csv')
COREMARK_CSV = os.path.join(BASE_DIR, '../common/dataset/aws_coremark_singlecore.csv')

# Price data
PRICE_CSV = os.path.join(BASE_DIR, 'data/price.csv')

# AWS Session for CloudTrail
aws_session = boto3.Session(profile_name='default')

# Visualization settings
plt.rcParams['font.size'] = 11
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.spines.right'] = False

# Color palette
COLORS = {
    'kubepacs': '#2ecc71',   # Green
    'baseline': '#e74c3c'   # Red
}

print(f"Base directory: {BASE_DIR}")


# ## 1. Load Data

# In[2]:


# Load FIS results
df = pd.read_csv(FIS_RESULTS_CSV)

# Parse datetime columns
df['Timestamp'] = pd.to_datetime(df['Timestamp'])
df['InterruptTime'] = pd.to_datetime(df['InterruptTime'])
df['RecoveryTime'] = pd.to_datetime(df['RecoveryTime'])

# Parse JSON columns
def safe_parse_json(s):
    if pd.isna(s) or s == '[]':
        return []
    try:
        return json.loads(s.replace("'", '"'))
    except:
        try:
            return ast.literal_eval(s)
        except:
            return []

df['InitInstances_parsed'] = df['InitInstances'].apply(safe_parse_json)
df['InterruptedInstances_parsed'] = df['InterruptedInstances'].apply(safe_parse_json)
df['NewInstances_parsed'] = df['NewInstances'].apply(safe_parse_json)

print(f"Total experiments: {len(df)}")
print(f"Strategy distribution:")
print(df['Strategy'].value_counts())
print(f"\nExperiment period: {df['Timestamp'].min()} ~ {df['Timestamp'].max()}")
print(f"Region: {df['Region'].iloc[0]}")


# ## 2. Load Reference Data (Price CSV, CoreMark)

# In[3]:


# Load spot price data from price.csv
df_price = pd.read_csv(PRICE_CSV)

# Filter for the region used in experiments
region = df['Region'].iloc[0]
df_price_region = df_price[df_price['Region'] == region]
print(f"Price entries for {region}: {len(df_price_region)}")

# Create spot price dictionary (use min price across AZs)
spot_price_dict = {}
for _, entry in df_price_region.iterrows():
    inst_type = entry['InstanceType']
    price = entry['SpotPrice']
    if pd.notna(inst_type) and price > 0:
        if inst_type not in spot_price_dict or price < spot_price_dict[inst_type]:
            spot_price_dict[inst_type] = price

print(f"Unique instance types with prices: {len(spot_price_dict)}")

# Show some example prices
example_types = ['t3.medium', 't3a.medium', 't3.large', 't2.medium', 'm5.large']
print("\nExample spot prices:")
for t in example_types:
    if t in spot_price_dict:
        print(f"  {t}: ${spot_price_dict[t]:.4f}/hr")


# In[4]:


# Load CoreMark data
df_coremark = pd.read_csv(COREMARK_CSV)
coremark_dict = dict(zip(df_coremark['InstanceType'], df_coremark['CoreMark']))
vcpu_dict = dict(zip(df_coremark['InstanceType'], df_coremark['vCPU']))
memory_dict = dict(zip(df_coremark['InstanceType'], df_coremark['Memory']))

print(f"Loaded CoreMark data for {len(coremark_dict)} instance types")

# Fallback spot prices (if not in SpotLake)
FALLBACK_PRICES = {
    't2.micro': 0.0035, 't2.small': 0.0069, 't2.medium': 0.0139, 't2.large': 0.0278,
    't3.micro': 0.0031, 't3.small': 0.0062, 't3.medium': 0.0125, 't3.large': 0.0250,
    't3a.micro': 0.0028, 't3a.small': 0.0056, 't3a.medium': 0.0113, 't3a.large': 0.0225,
    'default': 0.02
}

def get_spot_price(instance_type):
    if instance_type in spot_price_dict:
        return spot_price_dict[instance_type]
    return FALLBACK_PRICES.get(instance_type, FALLBACK_PRICES['default'])

def get_coremark(instance_type):
    return coremark_dict.get(instance_type, 15000)

def get_vcpu(instance_type):
    return vcpu_dict.get(instance_type, 2)

def get_memory(instance_type):
    return memory_dict.get(instance_type, 4)


# ## 3. Derive Before/After NodePools from Logs

# In[5]:


df


# In[6]:


def derive_nodepools_from_log(row):
    """
    CSV에 기록된 인스턴스 정보를 기반으로 Before/After 상태를 정확히 계산합니다.
    Before = InitInstances
    After = (InitInstances - InterruptedInstances) + NewInstances
    """
    init_list = row['InitInstances_parsed']
    intr_list = row['InterruptedInstances_parsed']
    new_list = row['NewInstances_parsed']

    # 1. 인스턴스 ID 세트 생성 (매칭용)
    interrupted_ids = set()
    # print(intr_list)
    for item in intr_list:
        if isinstance(item, dict) and 'instance_id' in item:
            interrupted_ids.add(item['instance_id'])

    # 2. Before NodePool 구성 (InitInstances 전체)
    before_types = []
    for item in init_list:
        if isinstance(item, dict) and 'instance_type' in item:
            before_types.append(item['instance_type'])

    # 3. After NodePool 구성
    # (Init - Interrupted) + New
    survived_items = [
        item for item in init_list 
        if isinstance(item, dict) and item.get('instance_id') not in interrupted_ids
    ]
    after_items = survived_items + new_list

    after_types = []
    for item in after_items:
        if isinstance(item, dict) and 'instance_type' in item:
            after_types.append(item['instance_type'])

    print(init_list)
    print("-->", before_types)
    print("XXX", interrupted_ids)
    return pd.Series({
        'BeforeInstances': before_types,
        'AfterInstances': after_types,
        'BeforeCount': len(before_types),
        'AfterCount': len(after_types),
        'InterruptedCount': len(intr_list),
        'SurvivedCount': len(survived_items),
        'NewCount': len(new_list)
    })

    # Derive node pools directly from logs
nodepool_info = df.apply(derive_nodepools_from_log, axis=1)

# Merge with original df
# Drop colliding columns from original df before merge
cols_to_drop = [c for c in nodepool_info.columns if c in df.columns]
df_matched = pd.concat([df.drop(columns=cols_to_drop), nodepool_info], axis=1)

print("Derived Before/After NodePools (from CSV):")
display_cols = ['Strategy', 'BeforeCount', 'InterruptedCount', 'NewCount', 'AfterCount']
print(df_matched[display_cols].head(10))


# In[7]:


# Derive node pools directly from logs
nodepool_info = df.apply(derive_nodepools_from_log, axis=1)

# Merge with original df
# Drop colliding columns from original df before merge
cols_to_drop = [c for c in nodepool_info.columns if c in df.columns]
df_matched = pd.concat([df.drop(columns=cols_to_drop), nodepool_info], axis=1)

print("Derived Before/After NodePools (from CSV):")
display_cols = ['Strategy', 'BeforeCount', 'InterruptedCount', 'NewCount', 'AfterCount']
print(df_matched[display_cols].head(30))


# ## 4. Calculate E_Total: Before Interrupt vs After Recovery

# In[8]:


def calculate_etotal_for_nodepool(instance_types, req_pod, req_cpu, req_mem):
    """
    Calculate E_Total for a given set of instances

    E_PerfCost = Σ(BS_i / SP_i)
    E_OverPods = Req_pod / Σ(Pod_i)
    E_Total = E_PerfCost * E_OverPods
    """
    if not instance_types:
        return 0, 0, 0, 0

    e_perf_cost = 0
    total_pods = 0
    total_cost = 0

    for inst_type in instance_types:
        bs = get_coremark(inst_type)
        sp = get_spot_price(inst_type)
        vcpu = get_vcpu(inst_type)
        mem = get_memory(inst_type)

        # Pod_i = min(vCPU/req_cpu, Mem/req_mem)
        pod_i = min(int(vcpu // req_cpu), int(mem // req_mem))

        e_perf_cost += (bs / sp)
        total_pods += pod_i
        total_cost += sp

    # E_OverPods (cap at 1.0)
    if total_pods > 0:
        e_over_pods = min(req_pod / total_pods, 1.0)
    else:
        e_over_pods = 0

    e_total = e_perf_cost * e_over_pods

    return e_total, e_perf_cost, e_over_pods, total_pods

def get_nodepool_metrics(instance_types):
    """
    Get CoreMark scores, spot prices, and instance types for all instances in the nodepool

    Returns:
        coremark_list: List of CoreMark scores for each instance
        price_list: List of spot prices for each instance
        type_list: List of instance types
    """
    if not instance_types:
        return [], [], []

    coremark_list = []
    price_list = []
    type_list = []

    for inst_type in instance_types:
        bs = get_coremark(inst_type)
        sp = get_spot_price(inst_type)

        coremark_list.append(bs)
        price_list.append(sp)
        type_list.append(inst_type)

    return coremark_list, price_list, type_list





def calculate_efficiency_metrics(df_exp, df_matched):
    """
    Calculate E_Total before and after for each scenario
    """
    results = []

    for idx, row in df_exp.iterrows():
        scenario = row['Scenario']
        strategy = row['Strategy']
        req_pod = row['Parallelism']
        req_cpu = row['CPU']
        req_mem = row['Mem']

        # print(scenario)
        # print(strategy)
        # print(req_pod)
        # print(req_cpu)
        # print(req_mem)

        # Get matched instances
        matched_row = df_matched[df_matched['Scenario'] == scenario].iloc[0]
        before_types = matched_row['BeforeInstances']
        after_types = matched_row['AfterInstances']

        # print(before_types)
        # print(after_types)

        # Calculate BEFORE
        e_total_before, e_perf_before, e_over_before, pods_before = calculate_etotal_for_nodepool(
            before_types, req_pod, req_cpu, req_mem
        )

        # Calculate AFTER
        e_total_after, e_perf_after, e_over_after, pods_after = calculate_etotal_for_nodepool(
            after_types, req_pod, req_cpu, req_mem
        )

        # Change percentage
        if e_total_before > 0:
            e_total_change_pct = (e_total_after - e_total_before) / e_total_before * 100
        else:
            e_total_change_pct = 0 if e_total_after == 0 else 100

        results.append({
            'Scenario': scenario,
            'Strategy': strategy,
            'RecoveryDurationSec': row['RecoveryDurationSec'],
            'Parallelism': req_pod,
            # Node counts
            'BeforeNodeCount': matched_row['BeforeCount'],
            'InterruptedCount': matched_row['InterruptedCount'],
            'SurvivedCount': matched_row['SurvivedCount'],
            'NewNodeCount': matched_row['NewCount'],
            'AfterNodeCount': matched_row['AfterCount'],
            # Instance types (for debugging)
            'BeforeTypes': before_types,
            'AfterTypes': after_types,
            # Before metrics
            'E_Total_Before': e_total_before,
            'E_PerfCost_Before': e_perf_before,
            'E_OverPods_Before': e_over_before,
            'TotalPods_Before': pods_before,
            # After metrics
            'E_Total_After': e_total_after,
            'E_PerfCost_After': e_perf_after,
            'E_OverPods_After': e_over_after,
            'TotalPods_After': pods_after,
            # Change
            'E_Total_Change%': e_total_change_pct
        })

    return pd.DataFrame(results)


def calculate_nodepool_details(df_exp, df_matched):
    """
    Calculate nodepool details (CoreMarks, Prices, Types, vCPUs) for before and after states
    """
    results = []

    for idx, row in df_exp.iterrows():
        req_pod = row['Parallelism']
        req_cpu = row['CPU']
        scenario = row['Scenario']
        strategy = row['Strategy']
        recovery_duration = row['RecoveryDurationSec']
        parallelism = row['Parallelism']

        # Get matched instances
        matched_row = df_matched[df_matched['Scenario'] == scenario].iloc[0]
        before_types = matched_row['BeforeInstances']
        after_types = matched_row['AfterInstances']

        # Get BEFORE metrics
        coremarks_before, prices_before, types_before = get_nodepool_metrics(before_types)

        # Get AFTER metrics
        coremarks_after, prices_after, types_after = get_nodepool_metrics(after_types)

        # Get vCPU counts for each instance type
        vcpus_before = [get_vcpu(t) for t in types_before]
        vcpus_after = [get_vcpu(t) for t in types_after]

        # Calculate weighted average score (sum of vcpu * coremark for each instance) / req_cpu
        avg_score_before = sum(v * c for v, c in zip(vcpus_before, coremarks_before)) / (req_cpu*req_pod)
        avg_score_after = sum(v * c for v, c in zip(vcpus_after, coremarks_after)) / (req_cpu*req_pod)

        results.append({
            'Scenario': scenario,
            'Strategy': strategy,
            'RecoveryDurationSec': recovery_duration,
            'Parallelism': parallelism,
            # Before
            'CoreMarks_Before': coremarks_before,
            'Prices_Before': prices_before,
            'Types_Before': types_before,
            'vCPUs_Before': vcpus_before,
            'AvgScore_Before': avg_score_before,
            # After
            'CoreMarks_After': coremarks_after,
            'Prices_After': prices_after,
            'Types_After': types_after,
            'vCPUs_After': vcpus_after,
            'AvgScore_After': avg_score_after,
        })

    return pd.DataFrame(results)


# Calculate efficiency
# df_efficiency = calculate_efficiency_metrics(df, df_matched)
# print("Before/After E_Total Summary:")
# print(df_efficiency.groupby('Strategy')[['E_Total_Before', 'E_Total_After', 'E_Total_Change%', 'RecoveryDurationSec']].agg(['mean', 'std']).round(2))

df_efficiency = calculate_nodepool_details(df, df_matched)
df_efficiency


# In[ ]:





# ## 5. Visualization: Before/After E_Total + Recovery Duration

# In[9]:


# Check unique baseline CoreMarks performance
baseline_df = df_efficiency[df_efficiency['Strategy'] == 'baseline']

print("Unique Baseline Instance Types and CoreMarks (Before):")
unique_before = set()
for idx, row in baseline_df.iterrows():
    for t, c in zip(row['Types_Before'], row['CoreMarks_Before']):
        unique_before.add((t, c))
for t, c in sorted(unique_before):
    print(f"  {t}: {c}")

print("\nUnique Baseline Instance Types and CoreMarks (After):")
unique_after = set()
for idx, row in baseline_df.iterrows():
    for t, c in zip(row['Types_After'], row['CoreMarks_After']):
        unique_after.add((t, c))
for t, c in sorted(unique_after):
    print(f"  {t}: {c}")



# In[10]:


# 1. Recovery Duration Box Plot
# Font settings
font_size = 19
font_family = 'Roboto'
plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(9, 2.4))

# Prepare data for horizontal boxplot
kubepacs_data = df_efficiency[df_efficiency['Strategy'] == 'kubepacs']['RecoveryDurationSec']
baseline_data = df_efficiency[df_efficiency['Strategy'] == 'baseline']['RecoveryDurationSec']

bp = ax.boxplot(
    [kubepacs_data, baseline_data],
    positions=[0, 1],
    widths=0.5,
    patch_artist=True,
    vert=False
)

# Apply colors and hatches like in file_context_0
colors = ['orange', 'skyblue']
hatches = ['/', '\\']
for i, patch in enumerate(bp['boxes']):
    patch.set_facecolor(colors[i])
    patch.set_hatch(hatches[i])
    patch.set_edgecolor('black')
    patch.set_linewidth(1.5)

for median in bp['medians']:
    median.set(color='red', linewidth=1.5)

for l_type in ['whiskers', 'caps', 'fliers']:
    for artist in bp[l_type]:
        artist.set_color('black')
        artist.set_linewidth(1.5)

ax.set_yticks([0, 1])
ax.set_xlim(45, 145)
# 그래프 영역 둘러싸는 박스 만들기
for spine in ax.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(1)
    spine.set_edgecolor('black')

ax.axhline(y=0.5, xmin=-2.0, xmax=1.0, color='gray', linestyle='--', linewidth=1)

ax.set_yticklabels(['KubePACS', 'Karpenter'], fontsize=font_size)
ax.tick_params(axis='x', labelsize=font_size)
# plt.title('Recovery Duration', fontsize=font_size)
plt.xlabel('Time (seconds)', fontsize=font_size)
plt.ylabel('')
plt.tight_layout()
plt.savefig('fis-recovery-comparison.pdf', bbox_inches='tight')
plt.show()


# In[11]:


# 2. CoreMarks Before/After Comparison
font_size = 17
font_family = 'Roboto'
plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(3.4, 3))

# Collect average CoreMarks per row for each Strategy and Phase
kubepacs_before = []
kubepacs_after = []
baseline_before = []
baseline_after = []

for idx, row in df_efficiency.iterrows():
    if row['Strategy'] == 'kubepacs':
        kubepacs_before.append(np.mean(row['CoreMarks_Before']))
        kubepacs_after.append(np.mean(row['CoreMarks_After']))
    else:  # baseline
        baseline_before.append(np.mean(row['CoreMarks_Before']))
        baseline_after.append(np.mean(row['CoreMarks_After']))

# Data for boxplot: [KubePACS Before, KubePACS After, Karpenter Before, Karpenter After]
# Reordered so Before is on top (higher y position)
data = [kubepacs_after, kubepacs_before, baseline_after, baseline_before]
positions = [0, 1, 2, 3]  # Reduced gap between strategies

bp = ax.boxplot(
    data,
    positions=positions,
    widths=0.6,
    patch_artist=True,
    vert=False
)

# Apply colors and hatches
colors = ['orange', 'orange', 'skyblue', 'skyblue']
hatches = ['\\', '/', '\\', '/']
alphas = [1, 1, 1, 1]  # After=lighter, Before=solid

for i, patch in enumerate(bp['boxes']):
    patch.set_facecolor(colors[i])
    patch.set_alpha(alphas[i])
    patch.set_hatch(hatches[i])
    patch.set_edgecolor('black')
    patch.set_linewidth(1.5)

for median in bp['medians']:
    median.set(color='red', linewidth=1.5)

for l_type in ['whiskers', 'caps', 'fliers']:
    for artist in bp[l_type]:
        artist.set_color('black')
        artist.set_linewidth(1.5)

# Y-axis labels with sub-labels for Before/After (Before on top)
ax.set_yticks([])
ax.set_yticklabels([], fontsize=font_size)
# ax.set_yticklabels(['After', 'Before', 'After', 'Before'], fontsize=font_size)

# Set x-axis ticks and labels to show 'K' (thousands)
xticks = [20000, 24000, 28000, 32000]
ax.set_xticks(xticks)
ax.set_xlim(19000, 33000)
ax.set_xticklabels([f"{x//1000}K" for x in xticks], fontsize=font_size)

# # Add strategy group labels on the left (upright text)
# ax.text(-0.175, 0.275, 'KubePACS\n(Ours)', transform=ax.get_yaxis_transform(), 
#         ha='right', va='center', fontsize=font_size, fontweight='bold')
# ax.text(-0.175, 2.5, 'Karpenter', transform=ax.get_yaxis_transform(), 
#         ha='right', va='center', fontsize=font_size, fontweight='bold')

ax.tick_params(axis='x', labelsize=font_size)

# Set y-axis limits to reduce top/bottom margins
ax.set_ylim(-0.5, 3.5)


# 중간 라인 추가 (between Karpenter and KubePACS groups)
ax.axhline(y=1.5, xmin=-2.0, xmax=1.0, color='gray', linestyle='--', linewidth=1)


for spine in ax.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(1)
    spine.set_edgecolor('black')

# plt.title('CoreMark Score Comparison', fontsize=font_size)
plt.xlabel('Benchmark Score', fontsize=font_size)
plt.ylabel('')
plt.tight_layout()
plt.savefig('fis-coremark-comparison.pdf', bbox_inches='tight')
# plt.show()


# In[12]:


# 2. Cost Before/After Comparison
font_size = 17
font_family = 'Roboto'
plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(5.5, 3))

# Collect all Costs from lists for each Strategy and Phase
kubepacs_before = []
kubepacs_after = []
baseline_before = []
baseline_after = []

for idx, row in df_efficiency.iterrows():
    if row['Strategy'] == 'kubepacs':
        kubepacs_before.extend(row['Prices_Before'])
        kubepacs_after.extend(row['Prices_After'])
    else:  # baseline
        baseline_before.extend(row['Prices_Before'])
        baseline_after.extend(row['Prices_After'])

# Data for boxplot: [KubePACS Before, KubePACS After, Karpenter Before, Karpenter After]
# Reordered so Before is on top (higher y position)
data = [kubepacs_after, kubepacs_before, baseline_after, baseline_before]
positions = [0, 1, 2, 3]  # Reduced gap between strategies

bp = ax.boxplot(
    data,
    positions=positions,
    widths=0.6,
    patch_artist=True,
    vert=False
)

# Apply colors and hatches
colors = ['orange', 'orange', 'skyblue', 'skyblue']
hatches = ['/', '/', '\\', '\\']
alphas = [1.0, 1.0, 1.0, 1.0]  # After=lighter, Before=solid

for i, patch in enumerate(bp['boxes']):
    patch.set_facecolor(colors[i])
    patch.set_alpha(alphas[i])
    patch.set_hatch(hatches[i])
    patch.set_edgecolor('black')
    patch.set_linewidth(1.5)

for median in bp['medians']:
    median.set(color='red', linewidth=1.5)

for l_type in ['whiskers', 'caps', 'fliers']:
    for artist in bp[l_type]:
        artist.set_color('black')
        artist.set_linewidth(1.5)

for spine in ax.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(1)
    spine.set_edgecolor('black')

# Y-axis labels with sub-labels for Before/After (Before on top)
ax.set_yticks([0, 1, 2, 3])
ax.set_yticklabels(['After', 'Before', 'After', 'Before'], fontsize=font_size-1.5)

# 중간 라인 추가 (between Karpenter and KubePACS groups)
ax.axhline(y=1.5, xmin=-2.0, xmax=1.0, color='gray', linestyle='--', linewidth=1)

# --- 기존: 좌측 전략 그룹 라벨 (상단: Karpenter, 하단: KubePACS)
# 그룹 라벨
ax.text(-0.36, 2.5, 'Karpenter', transform=ax.get_yaxis_transform(), 
        ha='right', va='center', fontsize=font_size)
ax.text(-0.36, 0.45, 'KubePACS', transform=ax.get_yaxis_transform(), 
        ha='right', va='center', fontsize=font_size)

import matplotlib.transforms as transforms
trans = transforms.blended_transform_factory(ax.transAxes, ax.transData)
bx = -0.34      # 세로선 x 위치 (axes fraction)
tick_len = 0.03  # 가로 꺾임 길이

# KubePACS 브래킷 (y=0 ~ y=1)
ax.plot([bx, bx], [0, 1], transform=trans, color='black', lw=1, clip_on=False)
ax.plot([bx, bx + tick_len], [0, 0], transform=trans, color='black', lw=1, clip_on=False)
ax.plot([bx, bx + tick_len], [1, 1], transform=trans, color='black', lw=1, clip_on=False)

# Karpenter 브래킷 (y=2 ~ y=3)
ax.plot([bx, bx], [2, 3], transform=trans, color='black', lw=1, clip_on=False)
ax.plot([bx, bx + tick_len], [2, 2], transform=trans, color='black', lw=1, clip_on=False)
ax.plot([bx, bx + tick_len], [3, 3], transform=trans, color='black', lw=1, clip_on=False)

ax.tick_params(axis='x', labelsize=font_size)

# Set y-axis limits to reduce top/bottom margins
ax.set_ylim(-0.5, 3.5)
ax.set_xlim(-0.02, 0.32)
ax.set_xticks([0, 0.1, 0.2, 0.3])

# Legend for Before/After with matching colors
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='orange', alpha=1.0, hatch='/', edgecolor='black', label='KubePACS'),
    Patch(facecolor='skyblue', alpha=1.0, hatch='\\', edgecolor='black', label='Karpenter'),
]
# ax.legend(handles=legend_elements, loc='upper left', fontsize=font_size-6)

# plt.title('Cost Comparison', fontsize=font_size)
plt.xlabel('Cost ($/hour)', fontsize=font_size)
plt.ylabel('')
plt.tight_layout()
plt.savefig('fis-cost-comparison.pdf', bbox_inches='tight')
plt.show()


# 

# In[ ]:




