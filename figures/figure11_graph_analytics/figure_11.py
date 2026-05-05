#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import cloudpickle

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[2]:


font_size = 23
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False


# In[3]:


df_baseline = pd.read_csv("data/baseline-48-6xr4.2xlarge.csv")
df_kubecaps = pd.read_csv("data/kubecaps-48-12xr6a.xlarge.csv")

def extract_duration_values(df):
    duration_values = {}
    for index, stage in enumerate(["community_detection", "pagerank", "dijkstra"]):
        functions = 48
        chunk = df.iloc[index * functions:(index + 1) * functions]
        # get worker_func_end_tstamp - worker_func_start_tstamp
        durations = chunk['worker_func_end_tstamp'] - chunk['worker_func_start_tstamp']
        duration_values[stage] = durations.to_list()
    return duration_values


def calculate_prices(data_grouped):
    max_values = [max(data) for data in data_grouped]
    print(max_values)
    times_karpenter = [max_values[i] for i in range(0, len(max_values), 2)]
    times_kubecaps = [max_values[i] for i in range(1, len(max_values), 2)]
    print(f"Max times Karpenter: {times_karpenter}")
    print(f"Max times KubeCAPS: {times_kubecaps}")
    price_karpenter = 0.1267
    price_kubecaps = 0.1136
    total_price_karpenter = sum(times_karpenter) * 12 * price_karpenter / 3600
    total_price_kubecaps = sum(times_kubecaps) * 12 * price_kubecaps / 3600
    print(f"Total price Karpenter: {total_price_karpenter:.2f} EUR")
    print(f"Total price KubeCAPS: {total_price_kubecaps:.2f} EUR")

    price_difference = total_price_karpenter - total_price_kubecaps
    percentage_difference = (price_difference / total_price_karpenter) * 100
    print(f"KubeCAPS is {percentage_difference:.2f}% cheaper than Karpenter")



# boxplot
# x is latencu values
# y axis has 3 categories: community_detection, pagerank, dijkstra
# each category has 2 boxes: baseline and kubecaps
def plot_boxplot(values_baseline, values_kubecaps):
    stages = list(values_baseline.keys())
    n = len(stages)

    positions = []
    data_grouped = []
    width = 0.6  # 너비 키움

    for i, stage in enumerate(["community_detection", "pagerank", "dijkstra"]):
        base_pos = i * 2
        kube_pos = base_pos + 0.8
        positions.extend([base_pos, kube_pos])
        data_grouped.extend([values_baseline[stage], values_kubecaps[stage]])

    plt.figure(figsize=(10, 4))
    box = plt.boxplot(data_grouped, positions=positions, widths=width, patch_artist=True)

    colors = ['#87ceeb', '#ffa500'] * n
    hatches = ['\\', '/'] * n     # Karpenter: \\, KubeCAPS: //

    for patch, color, hatch in zip(box['boxes'], colors, hatches):
        patch.set_facecolor(color)
        patch.set_edgecolor('black')
        patch.set_hatch(hatch)

    for whisker in box['whiskers']:
        whisker.set_color('black')
    for cap in box['caps']:
        cap.set_color('black')
    for median in box['medians']:
        median.set_color('red')

    plt.xticks([i * 2 + 0.4 for i in range(n)], ["Community\nDetection", "Pagerank", "Dijkstra"])
    plt.ylabel('Execution time (s)')

    legend_handles = [
        mpatches.Patch(facecolor=colors[0], edgecolor='black', hatch='\\\\', label='Karpenter'),
        mpatches.Patch(facecolor=colors[1], edgecolor='black', hatch='//', label='KubeCAPS')
    ]
    plt.legend(legend_handles, ['Karpenter', 'KubePACS'], loc='upper center', edgecolor='black', handletextpad=0.4, borderpad=0.4)

    plt.tight_layout()
    plt.savefig("graph-analytics.pdf", format='pdf', bbox_inches='tight')

    calculate_prices(data_grouped)


if __name__ == "__main__":
    values_baseline = extract_duration_values(df_baseline)
    values_kubecaps = extract_duration_values(df_kubecaps)
    plot_boxplot(values_baseline, values_kubecaps)


# In[4]:


import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

df_baseline = pd.read_csv("data/baseline-48-6xr4.2xlarge.csv")
df_kubecaps = pd.read_csv("data/kubecaps-48-12xr6a.xlarge.csv")

def extract_duration_values(df):
    duration_values = {}
    for index, stage in enumerate(["community_detection", "pagerank", "dijkstra"]):
        functions = 48
        chunk = df.iloc[index * functions:(index + 1) * functions]
        durations = chunk['worker_func_end_tstamp'] - chunk['worker_func_start_tstamp']
        duration_values[stage] = durations.to_list()
    return duration_values


def calculate_prices(data_grouped):
    max_values = [max(data) for data in data_grouped]
    print(max_values)
    times_kubecaps = [max_values[i] for i in range(0, len(max_values), 2)]
    times_karpenter = [max_values[i] for i in range(1, len(max_values), 2)]
    print(f"Max times KubeCAPS: {times_kubecaps}")
    print(f"Max times Karpenter: {times_karpenter}")
    price_kubecaps = 0.1136
    price_karpenter = 0.1267
    total_price_kubecaps = sum(times_kubecaps) * 12 * price_kubecaps / 3600
    total_price_karpenter = sum(times_karpenter) * 12 * price_karpenter / 3600
    print(f"Total price KubeCAPS: {total_price_kubecaps:.2f} EUR")
    print(f"Total price Karpenter: {total_price_karpenter:.2f} EUR")

    price_difference = total_price_karpenter - total_price_kubecaps
    percentage_difference = (price_difference / total_price_karpenter) * 100
    print(f"KubeCAPS is {percentage_difference:.2f}% cheaper than Karpenter")


def plot_boxplot(values_baseline, values_kubecaps):
    stages = list(values_baseline.keys())
    n = len(stages)

    positions = []
    data_grouped = []
    width = 0.6

    for i, stage in enumerate(stages):
        kube_pos = i * 2
        karp_pos = kube_pos + 0.8  # KubeCAPS 먼저

        positions.extend([kube_pos, karp_pos])
        data_grouped.extend([values_kubecaps[stage], values_baseline[stage]])

    plt.figure(figsize=(10, 4))
    box = plt.boxplot(data_grouped, positions=positions, widths=width, patch_artist=True)

    colors = ['#ffa500', '#87ceeb'] * n  # KubeCAPS, Karpenter
    hatches = ['/', '\\'] * n

    for patch, color, hatch in zip(box['boxes'], colors, hatches):
        patch.set_facecolor(color)
        patch.set_edgecolor('black')
        patch.set_hatch(hatch)

    for whisker in box['whiskers']:
        whisker.set_color('black')
    for cap in box['caps']:
        cap.set_color('black')
    for median in box['medians']:
        median.set_color('red')

    plt.xticks([i * 2 + 0.4 for i in range(n)], ["Community\nDetection", "Pagerank", "Dijkstra"])
    plt.ylabel('Execution time (s)')

    legend_handles = [
        mpatches.Patch(facecolor='#ffa500', edgecolor='black', hatch='/', label='KubeCAPS'),
        mpatches.Patch(facecolor='#87ceeb', edgecolor='black', hatch='\\', label='Karpenter')
    ]
    plt.legend(legend_handles, ['KubePACS', 'Karpenter'], loc='upper center', edgecolor='black', handletextpad=0.4, borderpad=0.4)

    plt.tight_layout()
    plt.savefig("graph-analytics.pdf", format='pdf', bbox_inches='tight')

    calculate_prices(data_grouped)


if __name__ == "__main__":
    values_baseline = extract_duration_values(df_baseline)
    values_kubecaps = extract_duration_values(df_kubecaps)
    plot_boxplot(values_baseline, values_kubecaps)


# In[ ]:





# In[ ]:




